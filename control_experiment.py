from __future__ import annotations

import argparse
import json
import logging
import random
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

from analysis import estimate_tokens, summarize_by_repetition, write_json
from config import get_settings
from deepinfra_client import DeepInfraClient
from evaluator import divergence_score, normalize_extraction, score_against_gold, structural_drift_score
from plotting import generate_structural_plots, generate_variance_plots
from repair_json import repair_and_analyze
from run_experiments import (
    FILLER_PARAGRAPHS,
    compute_variance_metrics,
    detect_early_collapse,
    extract_pdf_text,
    generate_synthetic_patients,
    pdf_page_count,
    render_pdf,
    write_patient_files,
)


ENTITY_FIELDS = ("conditions", "medications", "observations", "procedures")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def _entity_count(obj: dict[str, Any]) -> int:
    return sum(len(obj.get(k) or []) for k in ENTITY_FIELDS)


def build_constant_length_control(
    *,
    base_text: str,
    target_est_tokens: int,
    settings,
    rng: random.Random,
) -> str:
    """
    Builds a control doc that contains the medical page ONCE plus unrelated filler
    paragraphs until estimated token length matches target.
    """
    text = base_text.rstrip() + "\n"
    while estimate_tokens(len(text), settings.est_chars_per_token) < target_est_tokens:
        text += "\n" + rng.choice(FILLER_PARAGRAPHS) + "\n"
    return text.strip() + "\n"


def run_control(*, run_root: Path) -> int:
    """
    Constant-length filler control:
    - For each patient + repetition level, match the estimated token length of the redundancy doc (base*rep)
      by appending unrelated filler to base (base once).
    - Keep prompts/schema/evaluator/repair/generation settings fixed.
    """
    settings = get_settings()
    load_dotenv(settings.project_root / ".env")

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "outputs").mkdir(parents=True, exist_ok=True)
    (run_root / "raw_outputs").mkdir(parents=True, exist_ok=True)
    (run_root / "repaired_outputs").mkdir(parents=True, exist_ok=True)
    (run_root / "metrics").mkdir(parents=True, exist_ok=True)
    (run_root / "plots").mkdir(parents=True, exist_ok=True)
    (run_root / "control_docs").mkdir(parents=True, exist_ok=True)
    (run_root / "filler_sources").mkdir(parents=True, exist_ok=True)
    (run_root / "token_stats").mkdir(parents=True, exist_ok=True)

    # Save filler sources (transparency)
    _write_text(run_root / "filler_sources" / "filler_paragraphs.txt", "\n\n".join(FILLER_PARAGRAPHS) + "\n")

    write_json(
        run_root / "control_manifest.json",
        {
            "run_id": run_id,
            "condition": "constant_length_filler_control",
            "model": settings.model,
            "temperature": settings.temperature,
            "top_p": settings.top_p,
            "max_tokens": getattr(settings, "max_tokens", None),
            "num_patients": settings.num_patients,
            "repetition_levels": list(settings.repetition_levels),
            "runs_per_condition": settings.runs_per_condition,
            "token_tolerance": 0.05,
            "note": "Medical content appears once; unrelated filler is appended to match redundancy length.",
        },
    )

    # Ensure patient PDFs + ground truth exist (same as redundancy pilot).
    patients = generate_synthetic_patients(settings)
    write_patient_files(settings, patients)

    client = DeepInfraClient(settings)
    rng = random.Random(settings.random_seed)

    semantic_rows: list[dict[str, Any]] = []
    structural_rows: list[dict[str, Any]] = []
    context_rows: list[dict[str, Any]] = []
    token_rows: list[dict[str, Any]] = []

    logging.info("Starting constant-length control run_id=%s", run_id)

    for p in patients:
        pid = p["patient_id"]
        base_text = p["text"].strip() + "\n"
        gt_path = settings.data_dir / pid / "ground_truth" / f"{pid}.json"
        gold = json.loads(gt_path.read_text(encoding="utf-8"))

        one_x_norm: dict[str, Any] | None = None

        for rep in settings.repetition_levels:
            # Target length: redundancy doc estimated tokens = estimate_tokens(len(base_text * rep))
            redundancy_text = (base_text * int(rep)).strip() + "\n"
            target_tokens = estimate_tokens(len(redundancy_text), settings.est_chars_per_token)

            # Control doc: base once + filler until target
            control_text = build_constant_length_control(
                base_text=base_text,
                target_est_tokens=target_tokens,
                settings=settings,
                rng=rng,
            )
            achieved_tokens = estimate_tokens(len(control_text), settings.est_chars_per_token)

            token_rows.append(
                {
                    "patient_id": pid,
                    "repetition": int(rep),
                    "target_est_tokens": target_tokens,
                    "achieved_est_tokens": achieved_tokens,
                    "delta_tokens": achieved_tokens - target_tokens,
                    "delta_frac": (achieved_tokens - target_tokens) / max(target_tokens, 1),
                    "control_chars": len(control_text),
                    "redundancy_chars": len(redundancy_text),
                }
            )

            # Save control docs for auditability
            doc_dir = run_root / "control_docs" / pid / f"rep_{rep}x"
            doc_dir.mkdir(parents=True, exist_ok=True)
            (doc_dir / "control_document.txt").write_text(control_text, encoding="utf-8")
            (doc_dir / "redundancy_target_document.txt").write_text(redundancy_text, encoding="utf-8")

            # Render a PDF from the control text (so the pipeline remains identical: pdf->extract text)
            control_pdf = doc_dir / "control_document.pdf"
            render_pdf(control_text, control_pdf)

            doc_text = extract_pdf_text(control_pdf)
            pages = pdf_page_count(control_pdf)
            char_count = len(doc_text)
            est_toks = estimate_tokens(char_count, settings.est_chars_per_token)

            for run_idx in range(1, settings.runs_per_condition + 1):
                ts = datetime.now().isoformat()
                call_id = f"{run_id}__{pid}__rep_{rep}x__run_{run_idx:02d}"
                out_dir = run_root / "outputs" / pid / f"rep_{rep}x" / f"run_{run_idx:02d}"
                out_dir.mkdir(parents=True, exist_ok=True)

                prompt = settings.extraction_prompt_template.format(document_text=doc_text)
                (out_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
                (out_dir / "document_source.txt").write_text(doc_text, encoding="utf-8")

                result = client.chat_completions(user_prompt=settings.extraction_prompt_template, document_text=doc_text)
                _write_json(
                    out_dir / "response_meta.json",
                    {"ok": result.ok, "status_code": result.status_code, "latency_s": result.latency_s, "error": result.error},
                )
                if not result.ok:
                    _write_text(out_dir / "response_error.txt", result.error or "unknown_error")
                    raise RuntimeError(f"DeepInfra call failed for {call_id}: {result.status_code} {result.error}")

                (out_dir / "latency_s.txt").write_text(f"{result.latency_s:.6f}\n", encoding="utf-8")
                if result.usage is not None:
                    _write_json(out_dir / "usage.json", result.usage)
                if result.response_json is not None:
                    _write_json(out_dir / "response.json", result.response_json)

                raw_text = result.content_text
                if raw_text is None or not raw_text.strip():
                    _write_text(out_dir / "response_error.txt", "empty_or_missing_message_content")
                    raise RuntimeError(f"Empty model content for {call_id}")
                (out_dir / "raw_response.txt").write_text(raw_text, encoding="utf-8")
                (run_root / "raw_outputs" / f"{call_id}.txt").write_text(raw_text, encoding="utf-8")

                repair = repair_and_analyze(raw_text, patient_id=pid)
                _write_json(out_dir / "repair_event.json", asdict(repair))

                # NOTE: For this control, we record structural failures (malformed JSON / schema mismatch / empty extraction)
                # as outcomes instead of aborting the entire run. These failures are part of the comparison against redundancy.
                if not repair.raw_valid_json:
                    _write_text(out_dir / "response_error.txt", "raw_json_parse_failed")
                if not repair.schema_match:
                    _write_text(out_dir / "response_error.txt", "raw_schema_mismatch")

                repaired_obj = repair.repaired_obj
                if repaired_obj is None:
                    _write_text(out_dir / "response_error.txt", "repair_returned_none")
                    raise RuntimeError(f"Repair produced None for {call_id}")

                ent_n = _entity_count(repaired_obj)
                if ent_n == 0:
                    # Record but do not hard-stop: empty extraction is a meaningful failure mode under this control.
                    _write_text(out_dir / "response_error.txt", "repaired_entities_empty")

                (out_dir / "repaired.json").write_text(json.dumps(repaired_obj, indent=2), encoding="utf-8")
                (run_root / "repaired_outputs" / f"{call_id}.json").write_text(
                    json.dumps(repaired_obj, indent=2), encoding="utf-8"
                )

                norm_pred = normalize_extraction(repaired_obj, patient_id=pid)
                norm_gold = normalize_extraction(gold, patient_id=pid)
                gold_scores = score_against_gold(norm_pred, norm_gold)

                if rep == 1 and run_idx == 1:
                    one_x_norm = norm_pred

                drift_vs_1x = divergence_score(norm_pred, one_x_norm) if one_x_norm is not None else {"jaccard_distance": 0.0}
                drift_vs_gold = divergence_score(norm_pred, norm_gold)
                drift_score = 0.5 * float(drift_vs_1x["jaccard_distance"]) + 0.5 * float(drift_vs_gold["jaccard_distance"])

                sds = structural_drift_score(
                    malformed_json=repair.malformed_json,
                    missing_keys_count=repair.missing_keys_count,
                    extra_keys_count=repair.extra_keys_count,
                    schema_match=repair.schema_match,
                    markdown_fence_present=repair.markdown_fence_present,
                )

                semantic_row = {
                    "run_id": run_id,
                    "patient_id": pid,
                    "repetition": int(rep),
                    "run": run_idx,
                    "model": settings.model,
                    "timestamp": ts,
                    "ok": 1,
                    "status_code": result.status_code if result.status_code is not None else "",
                    "latency_s": result.latency_s,
                    "micro_precision": gold_scores["micro_precision"],
                    "micro_recall": gold_scores["micro_recall"],
                    "micro_f1": gold_scores["micro_f1"],
                    "omission_count": gold_scores["omission_count"],
                    "hallucination_count": gold_scores["hallucination_count"],
                    "drift_vs_1x": drift_vs_1x["jaccard_distance"],
                    "drift_vs_gold": drift_vs_gold["jaccard_distance"],
                    "drift_score": drift_score,
                    "extracted_entities_n": ent_n,
                }
                structural_row = {
                    "run_id": run_id,
                    "patient_id": pid,
                    "repetition": int(rep),
                    "run": run_idx,
                    "model": settings.model,
                    "timestamp": ts,
                    "ok": 1,
                    "status_code": result.status_code if result.status_code is not None else "",
                    "latency_s": result.latency_s,
                    "raw_valid_json": int(repair.raw_valid_json),
                    "schema_match": int(repair.schema_match),
                    "repair_needed": int(repair.repair_needed),
                    "extra_keys_count": repair.extra_keys_count,
                    "missing_keys_count": repair.missing_keys_count,
                    "malformed_json": int(repair.malformed_json),
                    "markdown_fence_present": int(repair.markdown_fence_present),
                    "structural_drift_score": sds,
                    "extracted_entities_n": ent_n,
                }

                semantic_rows.append(semantic_row)
                structural_rows.append(structural_row)

                _write_json(out_dir / "semantic_metrics.json", semantic_row)
                _write_json(out_dir / "structural_metrics.json", structural_row)

                context_rows.append(
                    {
                        "run_id": run_id,
                        "patient_id": pid,
                        "repetition": int(rep),
                        "run": run_idx,
                        "model": settings.model,
                        "timestamp": ts,
                        "pdf_pages": pages,
                        "character_count": char_count,
                        "estimated_tokens": est_toks,
                        "repetition_factor": int(rep),
                        "mode": "constant_length_control",
                    }
                )

    # Save token matching stats
    tok_df = pd.DataFrame(token_rows)
    tok_df.to_csv(run_root / "token_length_matching.csv", index=False)

    # Save metrics CSVs
    metrics_dir = run_root / "metrics"
    sem_csv = metrics_dir / "semantic_metrics.csv"
    st_csv = metrics_dir / "structural_metrics.csv"
    ctx_csv = metrics_dir / "context_metrics.csv"
    pd.DataFrame(semantic_rows).to_csv(sem_csv, index=False)
    pd.DataFrame(structural_rows).to_csv(st_csv, index=False)
    pd.DataFrame(context_rows).to_csv(ctx_csv, index=False)

    # Variance + scaling stats
    sem = pd.read_csv(sem_csv)
    st = pd.read_csv(st_csv)
    var_df = compute_variance_metrics(sem, st)
    var_csv = metrics_dir / "variance_metrics.csv"
    var_df.to_csv(var_csv, index=False)

    by_rep = summarize_by_repetition(sem, st, var_df)
    by_rep.to_csv(metrics_dir / "redundancy_scaling_statistics.csv", index=False)

    # Collapse detection summary
    by_rep_sem = (
        sem.groupby("repetition", as_index=False)
        .agg(micro_f1_mean=("micro_f1", "mean"), hallucination_mean=("hallucination_count", "mean"), omission_mean=("omission_count", "mean"))
        .sort_values("repetition")
    )
    by_rep_str = (
        st.groupby("repetition", as_index=False)
        .agg(raw_json_valid_rate=("raw_valid_json", "mean"), repair_rate=("repair_needed", "mean"), sds_mean=("structural_drift_score", "mean"))
        .sort_values("repetition")
    )
    flags = detect_early_collapse(by_rep_sem, by_rep_str)
    (run_root / "collapse_flags.txt").write_text("\n".join(flags) + "\n" if flags else "", encoding="utf-8")

    # Plots
    plots_dir = run_root / "plots"
    generate_structural_plots(st_csv, plots_dir)
    if not var_df.empty:
        generate_variance_plots(var_csv, plots_dir)

    return 0


def compare_against_redundancy(*, control_root: Path, redundancy_root: Path) -> int:
    """
    Postprocess-only comparator: reads on-disk metrics from both runs and writes
    comparison CSVs/plots into control_root.
    """
    c_by = pd.read_csv(control_root / "metrics" / "redundancy_scaling_statistics.csv")
    r_by = pd.read_csv(redundancy_root / "metrics" / "redundancy_scaling_statistics.csv")

    # Harmonize column names for join
    keep = {
        "f1_mean",
        "omission_mean",
        "halluc_mean",
        "sds_mean",
        "repair_rate",
        "raw_json_valid_rate",
        "output_variance_mean",
    }
    c = c_by[["repetition", *[c for c in c_by.columns if c in keep]]].copy()
    r = r_by[["repetition", *[c for c in r_by.columns if c in keep]]].copy()
    c = c.add_prefix("control_").rename(columns={"control_repetition": "repetition"})
    r = r.add_prefix("redundancy_").rename(columns={"redundancy_repetition": "repetition"})
    merged = r.merge(c, on="repetition", how="inner").sort_values("repetition")
    merged.to_csv(control_root / "control_vs_redundancy.csv", index=False)

    # DRE statistics: DRE(rep) = (F1_1x - F1_rep)_redundancy - (F1_1x - F1_rep)_control
    def _dre(df: pd.DataFrame, prefix: str) -> pd.Series:
        base = float(df.loc[df["repetition"] == 1, f"{prefix}f1_mean"].iloc[0])
        return base - df[f"{prefix}f1_mean"].astype(float)

    merged["F1_drop_redundancy"] = _dre(merged, "redundancy_")
    merged["F1_drop_control"] = _dre(merged, "control_")
    merged["DRE"] = merged["F1_drop_redundancy"] - merged["F1_drop_control"]
    merged[["repetition", "F1_drop_redundancy", "F1_drop_control", "DRE"]].to_csv(control_root / "DRE_statistics.csv", index=False)

    # Plots (publication-ish, grayscale-safe)
    import matplotlib.pyplot as plt

    plots_dir = control_root / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"figure.dpi": 200, "savefig.dpi": 400, "font.size": 11, "axes.spines.top": False, "axes.spines.right": False})

    def _plot(metric: str, ylab: str, out: str, *, ylim01: bool = False):
        df = merged.sort_values("repetition")
        x = df["repetition"].astype(int).tolist()
        y_r = df[f"redundancy_{metric}"].astype(float).tolist()
        y_c = df[f"control_{metric}"].astype(float).tolist()
        fig, ax = plt.subplots(figsize=(6.2, 3.6))
        ax.plot(x, y_r, "-o", color="black", linewidth=1.6, markersize=5, label="Redundancy")
        ax.plot(x, y_c, "--o", color="gray", linewidth=1.6, markersize=5, label="Length-matched filler")
        ax.set_xlabel("Repetition level (x)")
        ax.set_ylabel(ylab)
        ax.set_xticks(x)
        if ylim01:
            ax.set_ylim(0.0, 1.0)
        ax.grid(True, axis="y", linestyle="--", linewidth=0.6, alpha=0.6)
        ax.legend(frameon=False)
        fig.tight_layout()
        fig.savefig(plots_dir / out)
        plt.close(fig)

    _plot("f1_mean", "Micro F1 (mean)", "redundancy_vs_filler_F1.png", ylim01=True)
    _plot("omission_mean", "Omission count (mean)", "redundancy_vs_filler_omissions.png")
    _plot("halluc_mean", "Hallucination count (mean)", "redundancy_vs_filler_hallucinations.png")
    if "output_variance_mean" in merged.columns:
        _plot("output_variance_mean", "Output variance (semantic)", "redundancy_vs_filler_variance.png")

    # Narrative summary placeholder (filled after control run exists)
    (control_root / "redundancy_specificity_analysis.md").write_text(
        "\n".join(
            [
                "# Redundancy Specificity Analysis (Conservative)",
                "",
                "This compares the redundancy condition vs a constant-length unrelated-filler control.",
                "",
                "Primary outputs:",
                "- `control_vs_redundancy.csv`",
                "- `DRE_statistics.csv`",
                "- plots in `plots/`",
                "",
                "Interpretation guidance:",
                "- If filler-control shows similar degradation to redundancy, the effect may be largely generic long-context pressure.",
                "- If redundancy degrades more than filler at matched length (positive DRE), that supports a redundancy-specific component (still not causality-proof).",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="Run the constant-length control (makes API calls).")
    ap.add_argument("--postprocess_only", action="store_true", help="Postprocess an existing control run (no API calls).")
    ap.add_argument("--compare", action="store_true", help="Compare control run against redundancy run (no API calls).")
    ap.add_argument("--control_root", type=str, default="", help="Existing control run_root.")
    ap.add_argument("--redundancy_root", type=str, default="data/runs/full_pilot_20260520_192127", help="Redundancy run_root.")
    args = ap.parse_args()

    settings = get_settings()
    load_dotenv(settings.project_root / ".env")

    if args.run:
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_root = settings.data_dir / "runs" / f"full_pilot_control_{run_id}"
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        return run_control(run_root=run_root)

    if args.postprocess_only:
        if not args.control_root:
            raise SystemExit("--control_root required for --postprocess_only")
        # Currently run_control does postprocess at end; this mode is reserved for future recovery.
        return 0

    if args.compare:
        if not args.control_root:
            raise SystemExit("--control_root required for --compare")
        return compare_against_redundancy(control_root=Path(args.control_root), redundancy_root=Path(args.redundancy_root))

    raise SystemExit("Specify one of: --run, --postprocess_only, --compare")


if __name__ == "__main__":
    raise SystemExit(main())
