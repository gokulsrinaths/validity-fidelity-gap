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


def _split_units(text: str) -> list[str]:
    """
    Split into shuffling units. Prefer paragraph-level; fallback to sentence-ish splitting.
    """
    t = text.strip()
    if not t:
        return []

    paras = [p.strip() for p in t.split("\n\n") if p.strip()]
    if len(paras) >= 4:
        return paras

    # fallback: crude sentence split (keeps punctuation attached)
    import re

    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", t) if s.strip()]
    if len(sents) >= 8:
        return sents

    return paras if paras else [t]


def build_shuffled_redundancy_doc(*, base_text: str, rep: int, rng: random.Random) -> str:
    """
    Build a redundancy doc where each copy is a shuffled permutation of the same content units.
    This keeps medical content identical in multiset terms, but breaks exact repeated ordering/strings.
    """
    units = _split_units(base_text)
    if not units:
        return base_text.strip() + "\n"

    blocks: list[str] = []
    for _ in range(rep):
        u = units[:]
        rng.shuffle(u)
        blocks.append("\n\n".join(u))

    return ("\n\n".join(blocks)).strip() + "\n"


def run_shuffled_control(*, run_root: Path, reps: list[int] | None = None, runs_per_condition: int | None = None, num_patients: int | None = None) -> int:
    """
    Shuffled redundancy control:
    - For each repetition r, create a document with r copies of the same medical content,
      but shuffle each copy (paragraph/sentence units) to break exact repetition identity.
    - Uses the same prompt/schema/repair/evaluator as the main pilot.
    """
    settings = get_settings()
    load_dotenv(settings.project_root / ".env")

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_root.mkdir(parents=True, exist_ok=True)
    for sub in ("outputs", "raw_outputs", "repaired_outputs", "metrics", "plots", "control_docs", "token_stats"):
        (run_root / sub).mkdir(parents=True, exist_ok=True)

    write_json(
        run_root / "control_manifest.json",
        {
            "run_id": run_id,
            "condition": "shuffled_redundancy_control",
            "model": settings.model,
            "temperature": settings.temperature,
            "top_p": settings.top_p,
            "max_tokens": getattr(settings, "max_tokens", None),
            "num_patients": settings.num_patients,
            "repetition_levels": list(settings.repetition_levels),
            "runs_per_condition": settings.runs_per_condition,
            "note": "Each repetition is a shuffled permutation of the same medical content units.",
        },
    )

    patients = generate_synthetic_patients(settings)
    if num_patients is not None:
        patients = patients[: int(num_patients)]
    write_patient_files(settings, patients)

    client = DeepInfraClient(settings)
    rng = random.Random(settings.random_seed)

    semantic_rows: list[dict[str, Any]] = []
    structural_rows: list[dict[str, Any]] = []
    context_rows: list[dict[str, Any]] = []
    token_rows: list[dict[str, Any]] = []

    logging.info("Starting shuffled redundancy control run_id=%s", run_id)

    for p in patients:
        pid = p["patient_id"]
        base_text = p["text"].strip() + "\n"
        gt_path = settings.data_dir / pid / "ground_truth" / f"{pid}.json"
        gold = json.loads(gt_path.read_text(encoding="utf-8"))

        # For divergence vs 1x
        one_x_norm: dict[str, Any] | None = None

        rep_levels = reps if reps is not None else list(settings.repetition_levels)
        for rep in rep_levels:
            rep_i = int(rep)

            # Build shuffled redundancy doc; also compute an estimate token count for transparency
            doc_text = build_shuffled_redundancy_doc(base_text=base_text, rep=rep_i, rng=rng)
            est_doc_tokens = estimate_tokens(len(doc_text), settings.est_chars_per_token)

            # Save control doc + token stats
            _write_text(run_root / "control_docs" / f"{pid}_rep_{rep_i}x.txt", doc_text)
            token_rows.append(
                {"patient_id": pid, "repetition": rep_i, "est_doc_tokens": est_doc_tokens, "doc_chars": len(doc_text)}
            )

            # Render PDF + extract text to match pipeline behavior
            doc_dir = run_root / "control_docs" / pid / f"rep_{rep_i}x"
            doc_dir.mkdir(parents=True, exist_ok=True)
            (doc_dir / "shuffled_document.txt").write_text(doc_text, encoding="utf-8")
            shuffled_pdf = doc_dir / "shuffled_document.pdf"
            render_pdf(doc_text, shuffled_pdf)

            extracted = extract_pdf_text(shuffled_pdf)
            extracted_len = len(extracted)
            pages = pdf_page_count(shuffled_pdf)
            context_rows.append(
                {"patient_id": pid, "repetition": rep_i, "pdf_pages": pages, "extracted_chars": extracted_len}
            )

            rpc = int(runs_per_condition) if runs_per_condition is not None else int(settings.runs_per_condition)
            for run_idx in range(1, rpc + 1):
                ts = datetime.now().isoformat(timespec="seconds")
                call_id = f"{pid}__rep_{rep_i}x__run_{run_idx:02d}"
                out_dir = run_root / "outputs" / pid / f"rep_{rep_i}x" / f"run_{run_idx:02d}"
                out_dir.mkdir(parents=True, exist_ok=True)

                # Resumable: skip if repaired exists
                if (out_dir / "repaired.json").exists():
                    continue

                prompt = settings.extraction_prompt_template.format(document_text=extracted)
                (out_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
                (out_dir / "document_source.txt").write_text(extracted, encoding="utf-8")

                result = client.chat_completions(user_prompt=settings.extraction_prompt_template, document_text=extracted)
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

                repaired_obj = repair.repaired_obj
                if repaired_obj is None:
                    _write_text(out_dir / "response_error.txt", "repair_returned_none")
                    raise RuntimeError(f"Repair produced None for {call_id}")

                ent_n = _entity_count(repaired_obj)
                if ent_n == 0:
                    _write_text(out_dir / "response_error.txt", "repaired_entities_empty")
                    raise RuntimeError(f"Empty repaired extraction for {call_id}")

                (out_dir / "repaired.json").write_text(json.dumps(repaired_obj, indent=2), encoding="utf-8")
                (run_root / "repaired_outputs" / f"{call_id}.json").write_text(
                    json.dumps(repaired_obj, indent=2), encoding="utf-8"
                )

                norm_pred = normalize_extraction(repaired_obj, patient_id=pid)
                norm_gold = normalize_extraction(gold, patient_id=pid)
                gold_scores = score_against_gold(norm_pred, norm_gold)

                if rep_i == 1 and run_idx == 1:
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

                semantic_rows.append(
                    {
                        "run_id": run_id,
                        "patient_id": pid,
                        "repetition": rep_i,
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
                        "drift_vs_1x": float(drift_vs_1x.get("jaccard_distance", 0.0)),
                        "drift_vs_gold": float(drift_vs_gold.get("jaccard_distance", 0.0)),
                        "drift_score": float(drift_score),
                        "extracted_entities_n": ent_n,
                    }
                )

                structural_rows.append(
                    {
                        "run_id": run_id,
                        "patient_id": pid,
                        "repetition": rep_i,
                        "run": run_idx,
                        "model": settings.model,
                        "timestamp": ts,
                        "raw_valid_json": int(repair.raw_valid_json),
                        "repair_needed": int(repair.repair_needed),
                        "structural_drift_score": float(sds),
                        "schema_match": int(repair.schema_match),
                        "drift_score": float(drift_score),
                    }
                )

                # checkpoint flush
                pd.DataFrame(semantic_rows).to_csv(run_root / "metrics" / "semantic_metrics_partial.csv", index=False)
                pd.DataFrame(structural_rows).to_csv(run_root / "metrics" / "structural_metrics_partial.csv", index=False)

    sem = pd.DataFrame(semantic_rows)
    st = pd.DataFrame(structural_rows)
    ctx = pd.DataFrame(context_rows)
    toks = pd.DataFrame(token_rows)

    sem.to_csv(run_root / "metrics" / "semantic_metrics.csv", index=False)
    st.to_csv(run_root / "metrics" / "structural_metrics.csv", index=False)
    ctx.to_csv(run_root / "metrics" / "context_stats.csv", index=False)
    toks.to_csv(run_root / "metrics" / "token_stats.csv", index=False)

    variance = compute_variance_metrics(sem, st)
    variance.to_csv(run_root / "metrics" / "variance_metrics.csv", index=False)

    by_rep = summarize_by_repetition(sem, st, variance_df=variance)
    by_rep.to_csv(run_root / "metrics" / "redundancy_scaling_statistics.csv", index=False)

    # collapse flags (descriptive)
    try:
        by_rep_sem = pd.read_csv(run_root / "metrics" / "redundancy_scaling_statistics.csv")[
            ["repetition", "halluc_mean", "omission_mean", "raw_json_valid_rate"]
        ]
        by_rep_str = pd.read_csv(run_root / "metrics" / "redundancy_scaling_statistics.csv")[
            ["repetition", "raw_json_valid_rate"]
        ]
        flags = detect_early_collapse(by_rep_sem, by_rep_str)
        (run_root / "metrics" / "collapse_flags.txt").write_text("\n".join(flags) + ("\n" if flags else ""), encoding="utf-8")
    except Exception:
        pass

    # Plotting helpers expect CSV paths (not dataframes).
    try:
        generate_structural_plots(run_root / "metrics" / "structural_metrics.csv", run_root / "plots")
        generate_variance_plots(run_root / "metrics" / "variance_metrics.csv", run_root / "plots")
    except Exception:
        pass

    return 0


def compare_against_exact_and_filler(*, shuffled_root: Path, exact_root: Path, filler_root: Path, out_dir: Path, baseline_rep: int = 1) -> int:
    """
    Offline comparison:
    - reads redundancy scaling CSVs for exact redundancy, shuffled redundancy, and filler control
    - writes a combined CSV + plots
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    exact = pd.read_csv(exact_root / "metrics" / "redundancy_scaling_statistics.csv").assign(condition="exact_redundancy")
    shuf = pd.read_csv(shuffled_root / "metrics" / "redundancy_scaling_statistics.csv").assign(condition="shuffled_redundancy")
    fill = pd.read_csv(filler_root / "metrics" / "redundancy_scaling_statistics.csv").assign(condition="filler_control")

    combined = pd.concat([exact, shuf, fill], ignore_index=True)
    combined.to_csv(out_dir / "exact_vs_shuffled_vs_filler.csv", index=False)

    # Simple DRE-style comparisons on means (descriptive)
    def dre(df: pd.DataFrame, *, baseline_rep: int) -> pd.DataFrame:
        d = df.sort_values("repetition").set_index("repetition")
        if baseline_rep not in d.index:
            # fall back to the smallest repetition available (e.g., midrange-only runs)
            baseline_rep = int(min(d.index.tolist()))
        base = float(d.loc[baseline_rep, "f1_mean"])
        rows = []
        for rep in d.index.tolist():
            rows.append({"repetition": int(rep), "F1_drop": base - float(d.loc[rep, "f1_mean"])})
        return pd.DataFrame(rows)

    d_exact = dre(exact, baseline_rep=baseline_rep)
    d_shuf = dre(shuf, baseline_rep=baseline_rep)
    d_fill = dre(fill, baseline_rep=baseline_rep)

    merged = d_exact.merge(d_shuf, on="repetition", suffixes=("_exact", "_shuffled")).merge(d_fill, on="repetition")
    merged = merged.rename(columns={"F1_drop": "F1_drop_filler"})
    merged["DRE_exact_vs_filler"] = merged["F1_drop_exact"] - merged["F1_drop_filler"]
    merged["DRE_shuffled_vs_filler"] = merged["F1_drop_shuffled"] - merged["F1_drop_filler"]
    merged["Exact_minus_Shuffled"] = merged["F1_drop_exact"] - merged["F1_drop_shuffled"]
    merged.to_csv(out_dir / "dre_exact_vs_shuffled_vs_filler.csv", index=False)

    # minimal plot (no seaborn dependency)
    import matplotlib.pyplot as plt

    plt.figure(figsize=(5.0, 3.2), dpi=250)
    for label, d in [("Exact", exact), ("Shuffled", shuf), ("Filler", fill)]:
        dd = d.sort_values("repetition")
        plt.plot(dd["repetition"], dd["f1_mean"], marker="o", linewidth=1.6, label=label)
    plt.xscale("log", base=2)
    plt.xticks([1, 2, 5, 10, 16, 32], ["1", "2", "5", "10", "16", "32"])
    plt.xlabel("Repetition / length level")
    plt.ylabel("Micro-F1 (mean)")
    plt.grid(True, alpha=0.25)
    plt.legend(frameon=False, fontsize=8)
    plt.tight_layout()
    plt.savefig(out_dir / "exact_vs_shuffled_vs_filler_F1.png")
    plt.close()

    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="Run shuffled redundancy control (API calls).")
    ap.add_argument("--compare", action="store_true", help="Compare shuffled vs exact vs filler (offline).")
    ap.add_argument("--out_root", type=str, default="data/runs")
    ap.add_argument("--run_root", type=str, default="", help="Explicit run root directory to resume into (optional).")
    ap.add_argument("--exact_root", type=str, default="data/runs/full_pilot_20260520_192127")
    ap.add_argument("--filler_root", type=str, default="data/runs/full_pilot_control_20260520_235546")
    ap.add_argument("--shuffled_root", type=str, default="")
    ap.add_argument("--baseline_rep", type=int, default=1, help="Baseline repetition for F1-drop calculations (default 1x).")
    ap.add_argument("--reps", type=str, default="5,10,16", help="Comma-separated repetition levels to run (default midrange: 5,10,16).")
    ap.add_argument("--runs_per_condition", type=int, default=1, help="Runs per condition (default 1).")
    ap.add_argument("--num_patients", type=int, default=10, help="Number of patients (default 10).")
    args = ap.parse_args()

    if args.run:
        # NOTE: default uses whatever settings are configured (patients/reps/runs/model).
        if args.run_root:
            run_root = Path(args.run_root)
        else:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            run_root = Path(args.out_root) / f"full_pilot_shuffled_{ts}"
        reps = [int(x.strip()) for x in args.reps.split(",") if x.strip()]
        return run_shuffled_control(
            run_root=run_root,
            reps=reps,
            runs_per_condition=int(args.runs_per_condition),
            num_patients=int(args.num_patients),
        )

    if args.compare:
        if not args.shuffled_root:
            raise SystemExit("--shuffled_root is required for --compare")
        out_dir = Path(args.shuffled_root) / "comparisons"
        return compare_against_exact_and_filler(
            shuffled_root=Path(args.shuffled_root),
            exact_root=Path(args.exact_root),
            filler_root=Path(args.filler_root),
            out_dir=out_dir,
            baseline_rep=int(args.baseline_rep),
        )

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
