from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from analysis import pearson_corr, summarize_by_repetition, write_json
from config import get_settings
from run_experiments import run as run_full_pilot


def write_correlation_summary(out_md: Path, semantic_csv: Path, structural_csv: Path):
    sem = pd.read_csv(semantic_csv)
    st = pd.read_csv(structural_csv)
    merged = sem.merge(
        st[["patient_id", "repetition", "run", "structural_drift_score", "raw_valid_json"]],
        on=["patient_id", "repetition", "run"],
        how="left",
    )
    corr = {
        "SDS_vs_hallucination": pearson_corr(merged, "structural_drift_score", "hallucination_count"),
        "SDS_vs_omission": pearson_corr(merged, "structural_drift_score", "omission_count"),
        "repetition_vs_SDS": pearson_corr(merged, "repetition", "structural_drift_score"),
        "repetition_vs_raw_json_validity": pearson_corr(merged, "repetition", "raw_valid_json"),
    }

    lines = ["# Correlation Summary", ""]
    for k, v in corr.items():
        lines.append(f"- {k}: `{'' if v is None else f'{v:.3f}'}`")
    lines.append("")
    lines.append("Notes: Pearson correlations are descriptive for the pilot; treat as exploratory.")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_pilot_findings(out_md: Path, by_rep: pd.DataFrame, corr_md: Path, collapse_flags: Path | None):
    # Conservative narrative based on aggregate curves
    by_rep = by_rep.sort_values("repetition")
    f1_1x = float(by_rep.loc[by_rep["repetition"] == 1, "f1_mean"].iloc[0])
    f1_2x = float(by_rep.loc[by_rep["repetition"] == 2, "f1_mean"].iloc[0])
    f1_32x = float(by_rep.loc[by_rep["repetition"] == 32, "f1_mean"].iloc[0])
    sds_1x = float(by_rep.loc[by_rep["repetition"] == 1, "sds_mean"].iloc[0])
    sds_32x = float(by_rep.loc[by_rep["repetition"] == 32, "sds_mean"].iloc[0])
    repair_1x = float(by_rep.loc[by_rep["repetition"] == 1, "repair_rate"].iloc[0])
    repair_32x = float(by_rep.loc[by_rep["repetition"] == 32, "repair_rate"].iloc[0])

    lines = [
        "# Pilot Findings (Conservative)",
        "",
        "## Questions answered",
        "- Does redundancy improve extraction initially?",
        "- Does performance saturate or degrade at high redundancy?",
        "- Does structural instability increase (SDS / repair rate / raw JSON validity)?",
        "- Does redundancy increase output variance?",
        "",
        "## Summary (aggregate)",
        f"- F1: 1x `{f1_1x:.3f}`, 2x `{f1_2x:.3f}`, 32x `{f1_32x:.3f}`.",
        f"- Structural drift (SDS): 1x `{sds_1x:.3f}`, 32x `{sds_32x:.3f}`.",
        f"- Repair frequency: 1x `{repair_1x:.3f}`, 32x `{repair_32x:.3f}`.",
        "",
        "## Interpretation guidance",
        "- Evidence for a redundancy-driven phenomenon is strongest if structural instability increases with repetition while prompts/params are fixed.",
        "- Treat correlations as exploratory; confirm with larger N or additional controls.",
        "",
        f"See `{corr_md.name}` and the figures in `plots/`.",
    ]

    if collapse_flags and collapse_flags.exists():
        flags = collapse_flags.read_text(encoding="utf-8").strip().splitlines()
        if flags and any(f.strip() for f in flags):
            lines += ["", "## Early collapse flags"] + [f"- {f}" for f in flags]

    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    settings = get_settings()
    load_dotenv(settings.project_root / ".env")

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_root = settings.data_dir / "runs" / f"pilot_{run_id}"
    run_root.mkdir(parents=True, exist_ok=True)
    write_json(run_root / "pilot_manifest.json", {"run_id": run_id, "model": settings.model})

    rc = run_full_pilot(run_root=run_root)
    if rc != 0:
        return rc

    metrics_dir = run_root / "metrics"
    sem_csv = metrics_dir / "semantic_metrics.csv"
    st_csv = metrics_dir / "structural_metrics.csv"
    var_csv = metrics_dir / "variance_metrics.csv"

    sem = pd.read_csv(sem_csv)
    st = pd.read_csv(st_csv)
    var = pd.read_csv(var_csv) if var_csv.exists() else pd.DataFrame()

    by_rep = summarize_by_repetition(sem, st, var)
    by_rep.to_csv(metrics_dir / "redundancy_scaling_statistics.csv", index=False)

    corr_md = run_root / "correlation_summary.md"
    write_correlation_summary(corr_md, sem_csv, st_csv)

    collapse_flags = run_root / "collapse_flags.txt"
    pilot_md = run_root / "pilot_findings.md"
    write_pilot_findings(pilot_md, by_rep, corr_md, collapse_flags if collapse_flags.exists() else None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

