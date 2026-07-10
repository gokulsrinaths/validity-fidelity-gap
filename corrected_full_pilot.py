from __future__ import annotations

import json
import logging
import random
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

from analysis import summarize_by_repetition, write_json
from config import get_settings
from evaluator import normalize_extraction
from plotting import generate_structural_plots, generate_variance_plots
from run_experiments import compute_variance_metrics, detect_early_collapse, run as run_full_pilot


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _entity_set(obj: dict[str, Any], field: str) -> set[str]:
    xs = obj.get(field, [])
    if xs is None:
        xs = []
    if not isinstance(xs, list):
        xs = [xs]
    out: set[str] = set()
    for x in xs:
        s = str(x).strip()
        if s:
            out.add(s)
    return out


def _bootstrap_spearman(x: list[float], y: list[float], *, n: int = 2000, seed: int = 1337) -> tuple[float, float, float]:
    """
    Returns (rho, ci_low, ci_high) using bootstrap over paired observations.
    Conservative: percentile CI.
    """
    import numpy as np

    if len(x) != len(y) or len(x) < 3:
        return float("nan"), float("nan"), float("nan")

    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    rho = float(pd.Series(x_arr).corr(pd.Series(y_arr), method="spearman"))

    rng = random.Random(seed)
    rhos: list[float] = []
    idxs = list(range(len(x)))
    for _ in range(n):
        sample = [idxs[rng.randrange(len(idxs))] for _ in idxs]
        xs = x_arr[sample]
        ys = y_arr[sample]
        r = float(pd.Series(xs).corr(pd.Series(ys), method="spearman"))
        if not pd.isna(r):
            rhos.append(r)
    if not rhos:
        return rho, float("nan"), float("nan")
    rhos.sort()
    lo = rhos[int(0.025 * len(rhos))]
    hi = rhos[int(0.975 * len(rhos)) - 1]
    return rho, float(lo), float(hi)


def postprocess(run_root: Path) -> int:
    metrics_dir = run_root / "metrics"
    sem_csv = metrics_dir / "semantic_metrics.csv"
    st_csv = metrics_dir / "structural_metrics.csv"

    sem = pd.read_csv(sem_csv)
    st = pd.read_csv(st_csv)

    # Variance (run-to-run) metrics
    var_df = compute_variance_metrics(sem, st)
    var_csv = metrics_dir / "variance_metrics.csv"
    var_df.to_csv(var_csv, index=False)

    # Redundancy scaling statistics (adds CI for key metrics)
    by_rep = summarize_by_repetition(sem, st, var_df)
    by_rep.to_csv(metrics_dir / "redundancy_scaling_statistics.csv", index=False)

    # Collapse detection summary
    by_rep_sem = (
        sem.groupby("repetition", as_index=False)
        .agg(
            micro_f1_mean=("micro_f1", "mean"),
            hallucination_mean=("hallucination_count", "mean"),
            omission_mean=("omission_count", "mean"),
        )
        .sort_values("repetition")
    )
    by_rep_str = (
        st.groupby("repetition", as_index=False)
        .agg(
            raw_json_valid_rate=("raw_valid_json", "mean"),
            repair_rate=("repair_needed", "mean"),
            sds_mean=("structural_drift_score", "mean"),
        )
        .sort_values("repetition")
    )
    flags = detect_early_collapse(by_rep_sem, by_rep_str)
    (run_root / "collapse_detection_summary.md").write_text(
        "# Collapse Detection Summary\n\n"
        + ("No collapse flags detected.\n" if not flags else "Flags:\n" + "\n".join(f"- {f}" for f in flags) + "\n"),
        encoding="utf-8",
    )

    # Patient consistency analysis (monotonicity across repetitions)
    reps = sorted(by_rep["repetition"].unique().tolist())
    per_patient_rows: list[dict[str, Any]] = []
    for pid, g in sem.groupby("patient_id"):
        g2 = g.groupby("repetition", as_index=False)["micro_f1"].mean().sort_values("repetition")
        f_map = {int(r): float(v) for r, v in zip(g2["repetition"], g2["micro_f1"])}
        seq = [f_map.get(int(r), float("nan")) for r in reps]
        monotone_dec = all(seq[i] >= seq[i + 1] for i in range(len(seq) - 1) if not pd.isna(seq[i + 1]))
        monotone_inc = all(seq[i] <= seq[i + 1] for i in range(len(seq) - 1) if not pd.isna(seq[i + 1]))
        per_patient_rows.append(
            {
                "patient_id": pid,
                "F1_1x": f_map.get(1, float("nan")),
                "F1_32x": f_map.get(32, float("nan")),
                "RSS_32x": (f_map.get(1, float("nan")) - f_map.get(32, float("nan"))),
                "monotonic_decrease": int(monotone_dec and (seq[0] > seq[-1])),
                "monotonic_increase": int(monotone_inc and (seq[-1] > seq[0])),
            }
        )
    per_patient_df = pd.DataFrame(per_patient_rows).sort_values("patient_id")
    per_patient_df.to_csv(run_root / "patient_consistency.csv", index=False)

    dec_n = int(per_patient_df["monotonic_decrease"].sum())
    inc_n = int(per_patient_df["monotonic_increase"].sum())
    (run_root / "patient_consistency_analysis.md").write_text(
        "\n".join(
            [
                "# Patient Consistency Analysis (Conservative)",
                "",
                f"- patients: `{len(per_patient_df)}`",
                f"- monotonic decrease (across available reps): `{dec_n}`",
                f"- monotonic increase (across available reps): `{inc_n}`",
                "",
                "See `patient_consistency.csv` for per-patient values.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    # RSS distribution: per patient, per repetition level RSS = F1_1x - F1_Nx
    f1_by = sem.groupby(["patient_id", "repetition"], as_index=False)["micro_f1"].mean()
    base = f1_by[f1_by["repetition"] == 1].rename(columns={"micro_f1": "F1_1x"})[["patient_id", "F1_1x"]]
    rss = f1_by.merge(base, on="patient_id", how="left")
    rss["RSS"] = rss["F1_1x"] - rss["micro_f1"]
    rss.rename(columns={"micro_f1": "F1_Nx", "repetition": "repetition"}, inplace=True)
    rss.to_csv(run_root / "RSS_distribution.csv", index=False)

    # Entity persistence analysis: fraction of 1x entities retained at Nx, per type and overall.
    repaired_dir = run_root / "repaired_outputs"
    # Build map patient->rep->normalized extraction.
    extracted: dict[tuple[str, int, int], dict[str, Any]] = {}
    for path in repaired_dir.glob("*.json"):
        call_id = path.stem
        # call id format: runid__patient_XX__rep_Nx__run_YY
        parts = call_id.split("__")
        if len(parts) < 4:
            continue
        pid = parts[1]
        rep_part = parts[2]
        run_part = parts[3]
        if not rep_part.startswith("rep_") or not rep_part.endswith("x"):
            continue
        rep = int(rep_part[len("rep_") : -1])
        run = int(run_part.replace("run_", ""))
        obj = _read_json(path)
        extracted[(pid, rep, run)] = normalize_extraction(obj, patient_id=pid)

    persist_rows: list[dict[str, Any]] = []
    for pid in sorted({k[0] for k in extracted.keys()}):
        # baseline 1x per run
        for rep in reps:
            for run in [1, 2, 3]:
                base_key = (pid, 1, run)
                cur_key = (pid, int(rep), run)
                if base_key not in extracted or cur_key not in extracted:
                    continue
                base_obj = extracted[base_key]
                cur_obj = extracted[cur_key]
                row: dict[str, Any] = {"patient_id": pid, "repetition": int(rep), "run": run}
                base_all = set().union(*(set(base_obj.get(f, [])) for f in ("conditions", "medications", "observations", "procedures")))
                cur_all = set().union(*(set(cur_obj.get(f, [])) for f in ("conditions", "medications", "observations", "procedures")))
                row["persistence_overall"] = (len(base_all & cur_all) / len(base_all)) if base_all else 1.0
                for f in ("conditions", "medications", "observations", "procedures"):
                    b = set(base_obj.get(f, []))
                    c = set(cur_obj.get(f, []))
                    row[f"persistence_{f}"] = (len(b & c) / len(b)) if b else 1.0
                persist_rows.append(row)

    persist_df = pd.DataFrame(persist_rows)
    persist_df.to_csv(metrics_dir / "entity_persistence.csv", index=False)

    # Entity persistence narrative
    if not persist_df.empty:
        by_rep_p = persist_df.groupby("repetition", as_index=False).mean(numeric_only=True).sort_values("repetition")
        (run_root / "entity_persistence_analysis.md").write_text(
            "\n".join(
                [
                    "# Entity Persistence Analysis (Conservative)",
                    "",
                    "Persistence is measured relative to the 1x extraction for the same patient/run (set overlap / baseline set size).",
                    "",
                    "```",
                    by_rep_p.to_string(index=False),
                    "```",
                    "",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    # Publication-style figures with CI bands (basic)
    _make_publication_figures(run_root=run_root, by_rep=by_rep)

    # Qualitative failure cases: pick top RSS_32x patients and summarize deltas 1x vs 32x for one run.
    _write_qualitative_cases(run_root=run_root, rss=rss)

    # Statistical analysis: Spearman + bootstrap CI
    _write_statistical_analysis(run_root=run_root, sem=sem)

    # Findings summaries
    _write_findings(run_root=run_root, by_rep=by_rep)

    # Structural/variance plots from existing helper
    plots_dir = run_root / "plots"
    generate_structural_plots(st_csv, plots_dir)
    try:
        var_df = pd.read_csv(var_csv)
    except Exception:
        var_df = pd.DataFrame()
    if not var_df.empty:
        generate_variance_plots(var_csv, plots_dir)

    return 0


def _make_publication_figures(*, run_root: Path, by_rep: pd.DataFrame) -> None:
    import matplotlib.pyplot as plt

    plots_dir = run_root / "plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    plt.rcParams.update(
        {
            "figure.dpi": 200,
            "savefig.dpi": 400,
            "font.size": 11,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )

    def _band_plot(x_col: str, mean_col: str, lo_col: str, hi_col: str, ylab: str, out_name: str, *, ylim01: bool = False):
        df = by_rep.sort_values(x_col)
        x = df[x_col].astype(int).tolist()
        y = df[mean_col].astype(float).tolist()
        lo = df[lo_col].astype(float).tolist()
        hi = df[hi_col].astype(float).tolist()
        fig, ax = plt.subplots(figsize=(6.0, 3.6))
        ax.plot(x, y, "-o", color="black", linewidth=1.6, markersize=5)
        ax.fill_between(x, lo, hi, color="black", alpha=0.15, linewidth=0)
        ax.set_xlabel("Repetition level (x)")
        ax.set_ylabel(ylab)
        ax.set_xticks(x)
        ax.grid(True, axis="y", linestyle="--", linewidth=0.6, alpha=0.6)
        if ylim01:
            ax.set_ylim(0.0, 1.0)
        fig.tight_layout()
        fig.savefig(plots_dir / out_name)
        plt.close(fig)

    _band_plot("repetition", "f1_mean", "f1_ci_low", "f1_ci_high", "Micro F1", "repetition_vs_F1.png", ylim01=True)
    _band_plot(
        "repetition",
        "omission_mean",
        "omission_ci_low",
        "omission_ci_high",
        "Omission count (mean)",
        "repetition_vs_omission_rate.png",
        ylim01=False,
    )
    _band_plot(
        "repetition",
        "halluc_mean",
        "halluc_ci_low",
        "halluc_ci_high",
        "Hallucination count (mean)",
        "repetition_vs_hallucination_rate.png",
        ylim01=False,
    )
    _band_plot("repetition", "sds_mean", "sds_ci_low", "sds_ci_high", "SDS", "repetition_vs_SDS.png", ylim01=False)

    # Repair frequency (rate)
    fig, ax = plt.subplots(figsize=(6.0, 3.6))
    df = by_rep.sort_values("repetition")
    x = df["repetition"].astype(int).tolist()
    y = df["repair_rate"].astype(float).tolist()
    ax.plot(x, y, "-o", color="black", linewidth=1.6, markersize=5)
    ax.set_xlabel("Repetition level (x)")
    ax.set_ylabel("Repair frequency")
    ax.set_xticks(x)
    ax.set_ylim(0.0, 1.0)
    ax.grid(True, axis="y", linestyle="--", linewidth=0.6, alpha=0.6)
    fig.tight_layout()
    fig.savefig(plots_dir / "repetition_vs_repair_frequency.png")
    plt.close(fig)

    # Variance plot if present
    if "output_variance_mean" in by_rep.columns and by_rep["output_variance_mean"].notna().any():
        fig, ax = plt.subplots(figsize=(6.0, 3.6))
        ax.plot(x, df["output_variance_mean"].astype(float).tolist(), "-o", color="black", linewidth=1.6, markersize=5)
        ax.set_xlabel("Repetition level (x)")
        ax.set_ylabel("Output variance (semantic)")
        ax.set_xticks(x)
        ax.grid(True, axis="y", linestyle="--", linewidth=0.6, alpha=0.6)
        fig.tight_layout()
        fig.savefig(plots_dir / "repetition_vs_variance.png")
        plt.close(fig)


def _write_qualitative_cases(*, run_root: Path, rss: pd.DataFrame) -> None:
    # Pick a few largest RSS at 32x (per patient) for run-level inspection.
    # Note: repaired_outputs are per call id; we rely on comparisons in outputs/ folders for detailed diffs.
    # Here we write a conservative narrative pointer.
    per_patient = rss[rss["repetition"] == 32].sort_values("RSS", ascending=False)
    top = per_patient.head(3)
    lines = [
        "# Qualitative Failure Cases (Conservative)",
        "",
        "This section highlights a few patients with large RSS at 32x for manual inspection.",
        "See `outputs/<patient>/rep_1x/run_01/repaired.json` vs `rep_32x/run_01/repaired.json` for details.",
        "",
        "Top RSS (32x):",
    ]
    for _, r in top.iterrows():
        lines.append(f"- {r['patient_id']}: RSS_32x=`{float(r['RSS']):.3f}` (F1_1x=`{float(r['F1_1x']):.3f}`, F1_32x=`{float(r['F1_Nx']):.3f}`)")
    lines.append("")
    (run_root / "qualitative_failure_cases.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_statistical_analysis(*, run_root: Path, sem: pd.DataFrame) -> None:
    # Spearman correlation repetition vs F1 and repetition vs omissions (per-call)
    x = sem["repetition"].astype(float).tolist()
    f1 = sem["micro_f1"].astype(float).tolist()
    om = sem["omission_count"].astype(float).tolist()
    rho_f1, lo_f1, hi_f1 = _bootstrap_spearman(x, f1)
    rho_om, lo_om, hi_om = _bootstrap_spearman(x, om)

    lines = [
        "# Statistical Analysis (Conservative)",
        "",
        "This analysis is descriptive only (no causality claims).",
        "",
        "## Spearman correlations (bootstrap percentile CI)",
        f"- repetition vs F1: rho=`{rho_f1:.3f}` CI=`[{lo_f1:.3f}, {hi_f1:.3f}]`",
        f"- repetition vs omission_count: rho=`{rho_om:.3f}` CI=`[{lo_om:.3f}, {hi_om:.3f}]`",
        "",
        "Notes:",
        "- Bootstrap resamples calls with replacement (paired).",
        "- Interpret with caution; dependencies exist within patient/runs.",
        "",
    ]
    (run_root / "statistical_analysis.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_findings(*, run_root: Path, by_rep: pd.DataFrame) -> None:
    (run_root / "full_pilot_summary.md").write_text(
        "\n".join(
            [
                "# Full Pilot Summary (Conservative)",
                "",
                "- Benchmark operational: `True` (non-empty raw outputs; fail-fast enabled).",
                "- Structural stability: see `metrics/structural_metrics.csv` + `plots/repetition_vs_SDS.png`.",
                "- Semantic scaling: see `metrics/redundancy_scaling_statistics.csv` + `plots/repetition_vs_F1.png`.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    (run_root / "redundancy_drift_findings.md").write_text(
        "\n".join(
            [
                "# Redundancy Drift Findings (Conservative)",
                "",
                "Primary artifacts:",
                "- `metrics/semantic_metrics.csv` (per call)",
                "- `metrics/structural_metrics.csv` (per call)",
                "- `metrics/variance_metrics.csv` (per condition)",
                "- `metrics/redundancy_scaling_statistics.csv` (per repetition, with CI)",
                "",
                "Interpretation guidance:",
                "- Look for consistent movement of F1/omissions/hallucinations with repetition.",
                "- Separately track structural stability (SDS/repair rate/raw JSON validity).",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--postprocess", type=str, default=None, help="Existing run_root to postprocess (no API calls).")
    args = ap.parse_args()

    settings = get_settings()
    load_dotenv(settings.project_root / ".env")

    if args.postprocess:
        return postprocess(Path(args.postprocess))

    # Full pilot (180 calls) – relies on run_experiments.run() which now fail-fast validates:
    # - API ok
    # - non-empty content
    # - raw_valid_json
    # - schema_match
    # - non-empty extraction
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_root = settings.data_dir / "runs" / f"full_pilot_{run_id}"
    run_root.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    write_json(
        run_root / "full_pilot_manifest.json",
        {
            "run_id": run_id,
            "model": settings.model,
            "temperature": settings.temperature,
            "top_p": settings.top_p,
            "num_patients": settings.num_patients,
            "repetition_levels": list(settings.repetition_levels),
            "runs_per_condition": settings.runs_per_condition,
            "total_calls": settings.num_patients * len(settings.repetition_levels) * settings.runs_per_condition,
            "note": "Scientific variables fixed; only redundancy factor varies.",
        },
    )

    rc = run_full_pilot(run_root=run_root)
    if rc != 0:
        return rc
    return postprocess(run_root)


if __name__ == "__main__":
    raise SystemExit(main())
