from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BootstrapCI:
    mean: float
    ci_low: float
    ci_high: float


def _bootstrap_mean_ci(values: np.ndarray, *, n_boot: int = 5000, seed: int = 1337) -> BootstrapCI:
    rng = np.random.default_rng(seed)
    v = np.asarray(values, dtype=float)
    v = v[~np.isnan(v)]
    if v.size == 0:
        return BootstrapCI(mean=float("nan"), ci_low=float("nan"), ci_high=float("nan"))
    if v.size == 1:
        m = float(v.mean())
        return BootstrapCI(mean=m, ci_low=m, ci_high=m)
    boots = rng.choice(v, size=(n_boot, v.size), replace=True).mean(axis=1)
    lo, hi = np.quantile(boots, [0.025, 0.975])
    return BootstrapCI(mean=float(v.mean()), ci_low=float(lo), ci_high=float(hi))


def analyze(*, run_root: Path, reps: list[int], out_dir: Path) -> None:
    metrics_dir = run_root / "metrics"
    sem_path = metrics_dir / "semantic_metrics.csv"
    if not sem_path.exists():
        raise FileNotFoundError(sem_path)

    sem = pd.read_csv(sem_path)
    required = {"patient_id", "condition", "repetition", "micro_f1", "omission_count", "hallucination_count"}
    missing = sorted(required - set(sem.columns))
    if missing:
        raise RuntimeError(f"Missing columns in {sem_path}: {missing}")

    # per-patient per-rep means (only 1 run in this experiment, but keep it general)
    pp = (
        sem.groupby(["patient_id", "condition", "repetition"], as_index=False)
        .agg(
            micro_f1=("micro_f1", "mean"),
            omission_count=("omission_count", "mean"),
            hallucination_count=("hallucination_count", "mean"),
        )
        .sort_values(["patient_id", "condition", "repetition"])
        .reset_index(drop=True)
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    pp.to_csv(out_dir / "per_patient_means.csv", index=False)

    # compute paired deltas within each condition per patient: drop = F1(1x)-F1(rx)
    rows = []
    for (pid, cond), g in pp.groupby(["patient_id", "condition"]):
        g = g.set_index("repetition")
        if 1 not in g.index:
            continue
        base_f1 = float(g.loc[1, "micro_f1"])
        base_om = float(g.loc[1, "omission_count"])
        base_hal = float(g.loc[1, "hallucination_count"])
        for rep in reps:
            if rep == 1 or rep not in g.index:
                continue
            rows.append(
                {
                    "patient_id": pid,
                    "condition": cond,
                    "repetition": int(rep),
                    "F1_drop": base_f1 - float(g.loc[rep, "micro_f1"]),
                    "omission_rise": float(g.loc[rep, "omission_count"]) - base_om,
                    "hallucination_rise": float(g.loc[rep, "hallucination_count"]) - base_hal,
                }
            )
    deltas = pd.DataFrame(rows).sort_values(["condition", "repetition", "patient_id"]).reset_index(drop=True)
    deltas.to_csv(out_dir / "paired_deltas_by_patient.csv", index=False)

    # DRE-like differential: section redundancy vs filler control
    # DRE_section = F1_drop(section) - F1_drop(filler)
    sec_name = "section_redundancy"
    fill_name = "filler_control"
    merged = (
        deltas[deltas["condition"] == sec_name]
        .merge(
            deltas[deltas["condition"] == fill_name],
            on=["patient_id", "repetition"],
            suffixes=("_section", "_filler"),
            how="inner",
        )
        .copy()
    )
    merged["DRE_section_vs_filler"] = merged["F1_drop_section"] - merged["F1_drop_filler"]
    merged.to_csv(out_dir / "dre_by_patient.csv", index=False)

    # summaries with bootstrap CIs
    summary_rows = []
    for rep in reps:
        if rep == 1:
            continue
        for cond in (sec_name, fill_name):
            v = deltas[(deltas["condition"] == cond) & (deltas["repetition"] == rep)]["F1_drop"].to_numpy(dtype=float)
            ci = _bootstrap_mean_ci(v)
            summary_rows.append(
                {"condition": cond, "repetition": int(rep), "mean_f1_drop": ci.mean, "ci_low": ci.ci_low, "ci_high": ci.ci_high}
            )

        vdre = merged[merged["repetition"] == rep]["DRE_section_vs_filler"].to_numpy(dtype=float)
        ci = _bootstrap_mean_ci(vdre)
        summary_rows.append(
            {"condition": "DRE_section_vs_filler", "repetition": int(rep), "mean_f1_drop": ci.mean, "ci_low": ci.ci_low, "ci_high": ci.ci_high}
        )

    summary = pd.DataFrame(summary_rows).sort_values(["condition", "repetition"]).reset_index(drop=True)
    summary.to_csv(out_dir / "dre_bootstrap_summary.csv", index=False)

    # plots
    import matplotlib.pyplot as plt

    plt.rcParams.update({"figure.dpi": 200, "savefig.dpi": 400, "font.size": 10})
    reps_no1 = [r for r in reps if r != 1]

    # DRE mean with CI
    dre_rows = summary[summary["condition"] == "DRE_section_vs_filler"].copy()
    x = dre_rows["repetition"].astype(int).to_list()
    y = dre_rows["mean_f1_drop"].astype(float).to_list()
    ylo = dre_rows["ci_low"].astype(float).to_list()
    yhi = dre_rows["ci_high"].astype(float).to_list()
    plt.figure(figsize=(5.3, 3.2))
    plt.axhline(0.0, color="black", linewidth=0.8, alpha=0.5)
    plt.plot(x, y, marker="o", color="black", linewidth=1.6)
    plt.fill_between(x, ylo, yhi, color="gray", alpha=0.25, linewidth=0)
    plt.xscale("log", base=2)
    plt.xticks(x, [str(v) for v in x])
    plt.xlabel("Repetition level (x)")
    plt.ylabel("Mean DRE (section vs filler)")
    plt.grid(True, axis="y", linestyle="--", linewidth=0.6, alpha=0.6)
    plt.tight_layout()
    plt.savefig(out_dir / "section_dre_with_ci.png")
    plt.close()

    # per-patient DRE distribution
    data = [merged[merged["repetition"] == r]["DRE_section_vs_filler"].astype(float).to_numpy() for r in reps_no1]
    plt.figure(figsize=(5.6, 3.2))
    plt.axhline(0.0, color="black", linewidth=0.8, alpha=0.5)
    plt.boxplot(data, tick_labels=[str(r) for r in reps_no1], showfliers=False)
    plt.xlabel("Repetition level (x)")
    plt.ylabel("Per-patient DRE (section vs filler)")
    plt.grid(True, axis="y", linestyle="--", linewidth=0.6, alpha=0.6)
    plt.tight_layout()
    plt.savefig(out_dir / "section_dre_distribution_boxplot.png")
    plt.close()

    # save a short markdown snippet
    md = [
        "# Section-level redundancy vs filler (synthetic realism ablation)",
        "",
        f"- run_root: `{run_root}`",
        f"- reps: `{reps}`",
        "",
        "## Mean DRE (section redundancy vs filler) with 95% bootstrap CI",
        "",
        "```",
        dre_rows.to_string(index=False),
        "```",
        "",
    ]
    (out_dir / "section_redundancy_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--run_root", required=True)
    ap.add_argument("--reps", default="1,5,10,16")
    ap.add_argument("--out_dir", default="paper_artifacts/section_redundancy_largeN")
    args = ap.parse_args()

    reps = [int(x.strip()) for x in args.reps.split(",") if x.strip()]
    analyze(run_root=Path(args.run_root), reps=reps, out_dir=Path(args.out_dir))

