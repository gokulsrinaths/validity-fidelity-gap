from __future__ import annotations

import json
import logging
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

from analysis import write_json
from config import get_settings
from deepinfra_client import DeepInfraClient
from evaluator import normalize_extraction, score_against_gold, structural_drift_score
from repair_json import repair_and_analyze
from run_experiments import (
    extract_pdf_text,
    generate_synthetic_patients,
    pdf_page_count,
    setup_logging,
    write_patient_files,
)


def _assert_nonempty_content(raw_text: str | None, *, out_dir: Path) -> str:
    if raw_text is None:
        (out_dir / "response_error.txt").write_text("missing_message_content", encoding="utf-8")
        raise RuntimeError("Model content is None (no content captured).")
    if not raw_text.strip():
        (out_dir / "response_error.txt").write_text("empty_or_whitespace_content", encoding="utf-8")
        raise RuntimeError("Model content is empty/whitespace (no content captured).")
    return raw_text


def _entity_count(obj: dict[str, Any]) -> int:
    return sum(len(obj.get(k) or []) for k in ("conditions", "medications", "observations", "procedures"))


def _save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def _make_plots(*, run_root: Path, results_df: pd.DataFrame) -> None:
    import matplotlib.pyplot as plt

    plots_dir = run_root / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    # publication-friendly + grayscale-safe
    plt.rcParams.update(
        {
            "figure.dpi": 200,
            "savefig.dpi": 300,
            "font.size": 11,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )

    def _plot(metric: str, ylab: str, out_name: str, *, is_rate: bool = False):
        g = results_df.groupby("repetition_level")[metric]
        s = pd.DataFrame(
            {
                "repetition_level": g.mean().index.astype(int),
                "mean": g.mean().values.astype(float),
                "std": g.std().fillna(0.0).values.astype(float),
                "count": g.count().values.astype(int),
            }
        ).sort_values("repetition_level")

        x = s["repetition_level"].astype(int).tolist()
        y = s["mean"].astype(float).tolist()
        yerr = s["std"].astype(float).tolist()

        fig, ax = plt.subplots(figsize=(5.5, 3.5))
        ax.errorbar(x, y, yerr=yerr, fmt="-o", color="black", linewidth=1.5, markersize=5, capsize=3)
        ax.set_xlabel("Repetition level (x)")
        ax.set_ylabel(ylab)
        ax.set_xticks(x)
        ax.grid(True, axis="y", linestyle="--", linewidth=0.6, alpha=0.6)
        if is_rate:
            ax.set_ylim(0.0, 1.0)
        fig.tight_layout()
        fig.savefig(plots_dir / out_name)
        plt.close(fig)

    _plot("F1", "Micro F1", "repetition_vs_F1.png", is_rate=True)
    _plot("SDS", "Structural Drift Score (SDS)", "repetition_vs_SDS.png", is_rate=False)
    _plot("repair_needed", "Repair frequency", "repetition_vs_repair_frequency.png", is_rate=True)


def _write_comparisons(*, run_root: Path, results_df: pd.DataFrame) -> None:
    """
    For each repetition level, pick the first patient and emit a human-readable comparison.
    """
    comp_dir = run_root / "comparisons"
    comp_dir.mkdir(parents=True, exist_ok=True)

    def _to_set(xs: Any) -> set[str]:
        if not xs:
            return set()
        if not isinstance(xs, list):
            xs = [xs]
        return {str(x).strip() for x in xs if str(x).strip()}

    for rep in sorted(results_df["repetition_level"].unique()):
        row = results_df[results_df["repetition_level"] == rep].iloc[0]
        pid = row["patient_id"]
        out_dir = run_root / "outputs" / pid / f"rep_{int(rep)}x" / "run_01"
        gt_path = Path("data") / pid / "ground_truth" / f"{pid}.json"
        pred_path = out_dir / "repaired.json"
        gt = json.loads(gt_path.read_text(encoding="utf-8"))
        pred = json.loads(pred_path.read_text(encoding="utf-8"))

        lines: list[str] = [
            f"# GT vs Repaired — {pid} — {int(rep)}x",
            "",
            f"- ground truth: `{gt_path}`",
            f"- repaired: `{pred_path}`",
            "",
        ]

        for field in ("conditions", "medications", "observations", "procedures"):
            g = _to_set(gt.get(field))
            p = _to_set(pred.get(field))
            missing = sorted(g - p)
            extra = sorted(p - g)
            lines += [
                f"## {field}",
                "",
                "### Missing (vs GT)",
                *(f"- {x}" for x in (missing or ["(none)"])),
                "",
                "### Hallucinated (vs GT)",
                *(f"- {x}" for x in (extra or ["(none)"])),
                "",
            ]

        (comp_dir / f"gt_vs_repaired__rep_{int(rep)}x.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_analysis(*, run_root: Path, results_df: pd.DataFrame) -> None:
    def _agg(metric: str) -> pd.DataFrame:
        g = results_df.groupby("repetition_level")[metric]
        return (
            pd.DataFrame(
                {
                    "repetition_level": g.mean().index.astype(int),
                    "mean": g.mean().values.astype(float),
                    "std": g.std().fillna(0.0).values.astype(float),
                    "count": g.count().values.astype(int),
                }
            )
            .sort_values("repetition_level")
            .reset_index(drop=True)
        )

    f1 = _agg("F1")
    sds = _agg("SDS")
    repair = _agg("repair_needed")
    om = _agg("omission_rate")
    hal = _agg("hallucination_rate")

    def _tbl(df: pd.DataFrame) -> str:
        return df.to_string(index=False)

    md = [
        "# Mini-Pilot Analysis (Conservative)",
        "",
        "Question: Does semantic redundancy measurably alter structured extraction behavior?",
        "",
        "## What varied",
        "- Redundancy factor only: `1x`, `2x`, `5x`",
        "",
        "## What was fixed",
        "- Prompt, schema, model/provider, generation params, repair logic, evaluator logic",
        "",
        "## Aggregate trends (mean ± std across 3 patients)",
        "",
        "### F1",
        "```",
        _tbl(f1[["repetition_level", "mean", "std", "count"]]),
        "```",
        "",
        "### Structural Drift Score (SDS)",
        "```",
        _tbl(sds[["repetition_level", "mean", "std", "count"]]),
        "```",
        "",
        "### Repair frequency",
        "```",
        _tbl(repair[["repetition_level", "mean", "std", "count"]]),
        "```",
        "",
        "### Omission rate",
        "```",
        _tbl(om[["repetition_level", "mean", "std", "count"]]),
        "```",
        "",
        "### Hallucination rate",
        "```",
        _tbl(hal[["repetition_level", "mean", "std", "count"]]),
        "```",
        "",
        "## Conservative interpretation guidance",
        "- With N=3 patients and 1 run/condition, treat any movement as *suggestive* only.",
        "- Prefer looking for monotonic trends (1x→2x→5x) or sharp discontinuities.",
        "",
        "## Artifacts",
        "- Per-condition comparisons in `comparisons/`.",
        "- Plots in `plots/`.",
        "",
    ]
    (run_root / "mini_pilot_analysis.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    summary = [
        "# Mini-Pilot Summary",
        "",
        "- Benchmark operational: `True` (non-empty raw outputs; fail-fast enabled).",
        "- Outputs stable enough to score: `True` (semantic + structural metrics produced).",
        "- Does redundancy affect extraction (1x/2x/5x)? See `mini_pilot_analysis.md` and `mini_pilot_results.csv`.",
        "- Next step justified? Only if metrics show consistent movement across redundancy levels.",
        "",
    ]
    (run_root / "mini_pilot_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")


def postprocess(run_root: Path) -> int:
    df_res = pd.read_csv(run_root / "mini_pilot_results.csv")
    (run_root / "plots").mkdir(parents=True, exist_ok=True)
    _make_plots(run_root=run_root, results_df=df_res)
    _write_comparisons(run_root=run_root, results_df=df_res)
    _write_analysis(run_root=run_root, results_df=df_res)
    return 0


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--postprocess", type=str, default=None, help="Existing run_root to postprocess (no API calls).")
    args = ap.parse_args()

    settings = get_settings()
    load_dotenv(settings.project_root / ".env")

    if args.postprocess:
        return postprocess(Path(args.postprocess))

    # Mini-pilot configuration (scientific constraints respected):
    patient_ids = ["patient_01", "patient_02", "patient_03"]
    repetition_levels = [1, 2, 5]
    runs_per_condition = 1

    if settings.model != "meta-llama/Meta-Llama-3.1-8B-Instruct":
        raise RuntimeError(f"Unexpected model in settings: {settings.model}")
    if settings.temperature != 0.0 or settings.top_p != 1.0:
        raise RuntimeError("Generation params differ from pilot defaults; refusing to run.")

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_root = settings.data_dir / "runs" / f"mini_pilot_{run_id}"
    run_root.mkdir(parents=True, exist_ok=True)
    setup_logging(run_root / "run.log")
    logging.info("Starting mini-pilot run_id=%s", run_id)

    write_json(
        run_root / "mini_manifest.json",
        {
            "run_id": run_id,
            "model": settings.model,
            "temperature": settings.temperature,
            "top_p": settings.top_p,
            "patients": patient_ids,
            "repetition_levels": repetition_levels,
            "runs_per_condition": runs_per_condition,
            "total_calls": len(patient_ids) * len(repetition_levels) * runs_per_condition,
            "note": "Only redundancy varies (1x/2x/5x). Prompts/schema/repair/eval fixed.",
        },
    )

    (run_root / "raw_outputs").mkdir(parents=True, exist_ok=True)
    (run_root / "repaired_outputs").mkdir(parents=True, exist_ok=True)
    (run_root / "outputs").mkdir(parents=True, exist_ok=True)
    (run_root / "metrics").mkdir(parents=True, exist_ok=True)
    (run_root / "plots").mkdir(parents=True, exist_ok=True)

    # Ensure patient files exist (pdfs + GT). This does not change prompts/schema.
    patients_all = generate_synthetic_patients(settings)
    write_patient_files(settings, patients_all)
    patients = [p for p in patients_all if p["patient_id"] in set(patient_ids)]

    client = DeepInfraClient(settings)

    semantic_rows: list[dict[str, Any]] = []
    structural_rows: list[dict[str, Any]] = []
    results_rows: list[dict[str, Any]] = []

    for p in patients:
        pid = p["patient_id"]
        gt_path = settings.data_dir / pid / "ground_truth" / f"{pid}.json"
        gold = json.loads(gt_path.read_text(encoding="utf-8"))
        gold_norm = normalize_extraction(gold, patient_id=pid)

        for rep in repetition_levels:
            pdf_path = settings.data_dir / pid / "pdfs" / f"{pid}_rep_{rep}x.pdf"
            doc_text = extract_pdf_text(pdf_path)
            pages = pdf_page_count(pdf_path)

            for run_idx in range(1, runs_per_condition + 1):
                call_id = f"{run_id}__{pid}__rep_{rep}x__run_{run_idx:02d}"
                out_dir = run_root / "outputs" / pid / f"rep_{rep}x" / f"run_{run_idx:02d}"
                out_dir.mkdir(parents=True, exist_ok=True)

                prompt = settings.extraction_prompt_template.format(document_text=doc_text)
                (out_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
                (out_dir / "document_source.txt").write_text(doc_text, encoding="utf-8")

                result = client.chat_completions(
                    user_prompt=settings.extraction_prompt_template, document_text=doc_text
                )

                (out_dir / "response_meta.json").write_text(
                    json.dumps(
                        {
                            "ok": result.ok,
                            "status_code": result.status_code,
                            "latency_s": result.latency_s,
                            "error": result.error,
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                if not result.ok:
                    (out_dir / "response_error.txt").write_text(result.error or "unknown_error", encoding="utf-8")
                    raise RuntimeError(f"DeepInfra call failed for {call_id}: {result.status_code} {result.error}")

                (out_dir / "latency_s.txt").write_text(f"{result.latency_s:.6f}\n", encoding="utf-8")
                if result.usage is not None:
                    (out_dir / "usage.json").write_text(json.dumps(result.usage, indent=2), encoding="utf-8")

                if result.response_json is not None:
                    (out_dir / "response.json").write_text(json.dumps(result.response_json, indent=2), encoding="utf-8")

                raw_text = _assert_nonempty_content(result.content_text, out_dir=out_dir)
                (out_dir / "raw_response.txt").write_text(raw_text, encoding="utf-8")
                (run_root / "raw_outputs" / f"{call_id}.txt").write_text(raw_text, encoding="utf-8")

                repair = repair_and_analyze(raw_text, patient_id=pid)
                (out_dir / "repair_event.json").write_text(json.dumps(asdict(repair), indent=2, default=str), encoding="utf-8")

                # Fail-fast enforcement (scientific constraint): do not allow malformed / non-JSON outputs
                # to flow into repair/metrics silently.
                if not repair.raw_valid_json:
                    (out_dir / "response_error.txt").write_text(
                        "raw_json_parse_failed", encoding="utf-8"
                    )
                    raise RuntimeError(f"Raw JSON parsing failed for {call_id}")
                if not repair.schema_match:
                    (out_dir / "response_error.txt").write_text(
                        "raw_schema_mismatch", encoding="utf-8"
                    )
                    raise RuntimeError(f"Raw JSON schema mismatch for {call_id}")

                repaired_obj = repair.repaired_obj
                if repaired_obj is None:
                    (out_dir / "response_error.txt").write_text("repair_returned_none", encoding="utf-8")
                    raise RuntimeError(f"Repair produced None for {call_id}")

                ent_n = _entity_count(repaired_obj)
                if ent_n == 0:
                    (out_dir / "response_error.txt").write_text("repaired_entities_empty", encoding="utf-8")
                    raise RuntimeError(f"Repaired extraction empty for {call_id}")

                (out_dir / "repaired.json").write_text(json.dumps(repaired_obj, indent=2), encoding="utf-8")
                (run_root / "repaired_outputs" / f"{call_id}.json").write_text(
                    json.dumps(repaired_obj, indent=2), encoding="utf-8"
                )

                pred_norm = normalize_extraction(repaired_obj, patient_id=pid)
                scores = score_against_gold(pred_norm, gold_norm)

                semantic_row = {
                    "call_id": call_id,
                    "patient_id": pid,
                    "repetition": rep,
                    "run": run_idx,
                    "micro_precision": scores["micro_precision"],
                    "micro_recall": scores["micro_recall"],
                    "micro_f1": scores["micro_f1"],
                    "omission_count": scores["omission_count"],
                    "hallucination_count": scores["hallucination_count"],
                }
                semantic_rows.append(semantic_row)

                sds = structural_drift_score(
                    malformed_json=repair.malformed_json,
                    missing_keys_count=repair.missing_keys_count,
                    extra_keys_count=repair.extra_keys_count,
                    schema_match=repair.schema_match,
                    markdown_fence_present=repair.markdown_fence_present,
                )

                structural_row = {
                    "call_id": call_id,
                    "patient_id": pid,
                    "repetition": rep,
                    "run": run_idx,
                    "raw_valid_json": repair.raw_valid_json,
                    "repair_needed": repair.repair_needed,
                    "structural_drift_score": sds,
                    "missing_keys_count": repair.missing_keys_count,
                    "extra_keys_count": repair.extra_keys_count,
                    "schema_match": repair.schema_match,
                    "markdown_fence_present": repair.markdown_fence_present,
                }
                structural_rows.append(structural_row)

                # Mini-pilot summary row
                total_gold_entities = sum(len(gold_norm.get(k, [])) for k in ("conditions", "medications", "observations", "procedures"))
                omission_rate = (scores["omission_count"] / total_gold_entities) if total_gold_entities else 0.0
                hallucination_rate = (scores["hallucination_count"] / total_gold_entities) if total_gold_entities else 0.0

                results_rows.append(
                    {
                        "patient_id": pid,
                        "repetition_level": rep,
                        "extracted_entities_n": ent_n,
                        "F1": scores["micro_f1"],
                        "hallucination_rate": hallucination_rate,
                        "omission_rate": omission_rate,
                        "raw_json_valid": int(bool(repair.raw_valid_json)),
                        "repair_needed": int(bool(repair.repair_needed)),
                        "SDS": sds,
                        "pages": pages,
                        "doc_chars": len(doc_text),
                    }
                )

    df_sem = pd.DataFrame(semantic_rows)
    df_str = pd.DataFrame(structural_rows)
    df_res = pd.DataFrame(results_rows)

    metrics_dir = run_root / "metrics"
    df_sem.to_csv(metrics_dir / "semantic_metrics.csv", index=False)
    df_str.to_csv(metrics_dir / "structural_metrics.csv", index=False)
    df_res.to_csv(run_root / "mini_pilot_results.csv", index=False)

    _make_plots(run_root=run_root, results_df=df_res)
    _write_comparisons(run_root=run_root, results_df=df_res)
    _write_analysis(run_root=run_root, results_df=df_res)

    logging.info("Mini-pilot done. Wrote %s", run_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
