from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


REPS_DEFAULT = [1, 5, 10, 16]


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
    ci_low, ci_high = np.quantile(boots, [0.025, 0.975])
    return BootstrapCI(mean=float(v.mean()), ci_low=float(ci_low), ci_high=float(ci_high))


def _load_semantic(run_root: Path) -> pd.DataFrame:
    path = run_root / "metrics" / "semantic_metrics.csv"
    if not path.exists():
        raise FileNotFoundError(path)
    df = pd.read_csv(path)
    # normalize columns used across scripts
    keep = [
        "patient_id",
        "repetition",
        "run",
        "micro_f1",
        "omission_count",
        "hallucination_count",
    ]
    missing = [c for c in keep if c not in df.columns]
    if missing:
        raise RuntimeError(f"Missing expected columns in {path}: {missing}")
    return df[keep].copy()


def _per_patient_means(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.groupby(["patient_id", "repetition"], as_index=False)
        .agg(
            micro_f1=("micro_f1", "mean"),
            omission_count=("omission_count", "mean"),
            hallucination_count=("hallucination_count", "mean"),
        )
        .sort_values(["patient_id", "repetition"])
        .reset_index(drop=True)
    )


def _paired_deltas(per_patient: pd.DataFrame, reps: list[int]) -> pd.DataFrame:
    # wide table per patient for each metric
    wide = per_patient.pivot(index="patient_id", columns="repetition", values=["micro_f1", "omission_count", "hallucination_count"])
    wide.columns = [f"{metric}_{rep}x" for (metric, rep) in wide.columns]
    wide = wide.reset_index()

    # deltas relative to 1x
    for rep in reps:
        if rep == 1:
            continue
        wide[f"delta_f1_{rep}x_minus_1x"] = wide.get(f"micro_f1_{rep}x") - wide.get("micro_f1_1x")
        wide[f"delta_om_{rep}x_minus_1x"] = wide.get(f"omission_count_{rep}x") - wide.get("omission_count_1x")
        wide[f"delta_hal_{rep}x_minus_1x"] = wide.get(f"hallucination_count_{rep}x") - wide.get("hallucination_count_1x")

    return wide


def _dre_by_patient(
    *,
    red_per_patient: pd.DataFrame,
    ctl_per_patient: pd.DataFrame,
    reps: list[int],
) -> pd.DataFrame:
    red = red_per_patient.rename(
        columns={
            "micro_f1": "micro_f1_red",
            "omission_count": "omission_count_red",
            "hallucination_count": "hallucination_count_red",
        }
    )
    ctl = ctl_per_patient.rename(
        columns={
            "micro_f1": "micro_f1_ctl",
            "omission_count": "omission_count_ctl",
            "hallucination_count": "hallucination_count_ctl",
        }
    )
    merged = red.merge(ctl, on=["patient_id", "repetition"], how="inner")
    # compute drops relative to each condition's 1x baseline (paired within patient)
    out_rows = []
    for pid, g in merged.groupby("patient_id"):
        g = g.set_index("repetition")
        if 1 not in g.index:
            continue
        base_red = float(g.loc[1, "micro_f1_red"])
        base_ctl = float(g.loc[1, "micro_f1_ctl"])
        for rep in reps:
            if rep not in g.index:
                continue
            drop_red = base_red - float(g.loc[rep, "micro_f1_red"])
            drop_ctl = base_ctl - float(g.loc[rep, "micro_f1_ctl"])
            out_rows.append(
                {
                    "patient_id": pid,
                    "repetition": int(rep),
                    "F1_drop_redundancy": drop_red,
                    "F1_drop_control": drop_ctl,
                    "DRE": drop_red - drop_ctl,
                }
            )
    return pd.DataFrame(out_rows).sort_values(["patient_id", "repetition"]).reset_index(drop=True)


def _sign_counts(values: Iterable[float]) -> dict[str, int]:
    v = [float(x) for x in values if not pd.isna(x)]
    return {
        "n": len(v),
        "n_pos": sum(1 for x in v if x > 0),
        "n_neg": sum(1 for x in v if x < 0),
        "n_zero": sum(1 for x in v if x == 0),
    }


def run(
    *,
    redundancy_root: Path,
    control_root: Path,
    reps: list[int],
    out_dir: Path,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    sem_red = _load_semantic(redundancy_root)
    sem_ctl = _load_semantic(control_root)

    red_pp = _per_patient_means(sem_red)
    ctl_pp = _per_patient_means(sem_ctl)

    red_deltas = _paired_deltas(red_pp, reps)
    ctl_deltas = _paired_deltas(ctl_pp, reps)

    red_deltas.to_csv(out_dir / "paired_patient_deltas_redundancy.csv", index=False)
    ctl_deltas.to_csv(out_dir / "paired_patient_deltas_control.csv", index=False)

    dre_pat = _dre_by_patient(red_per_patient=red_pp, ctl_per_patient=ctl_pp, reps=reps)
    dre_pat.to_csv(out_dir / "dre_by_patient.csv", index=False)

    # summarize by repetition with bootstrap CIs (paired deltas)
    summary_rows = []
    for rep in reps:
        if rep == 1:
            continue

        df = red_deltas[["patient_id", f"delta_f1_{rep}x_minus_1x", f"delta_om_{rep}x_minus_1x", f"delta_hal_{rep}x_minus_1x"]].copy()
        df = df.rename(
            columns={
                f"delta_f1_{rep}x_minus_1x": "delta_f1",
                f"delta_om_{rep}x_minus_1x": "delta_om",
                f"delta_hal_{rep}x_minus_1x": "delta_hal",
            }
        )
        # degradation = negative delta_f1 (since delta = rep - 1x). We report drop = -delta.
        f1_drop = (-df["delta_f1"]).to_numpy(dtype=float)
        om_rise = (df["delta_om"]).to_numpy(dtype=float)
        hal_rise = (df["delta_hal"]).to_numpy(dtype=float)

        f1_ci = _bootstrap_mean_ci(f1_drop)
        om_ci = _bootstrap_mean_ci(om_rise)
        hal_ci = _bootstrap_mean_ci(hal_rise)

        f1_sign = _sign_counts(f1_drop)

        summary_rows.append(
            {
                "repetition": int(rep),
                "metric": "F1_drop",
                "mean": f1_ci.mean,
                "ci_low": f1_ci.ci_low,
                "ci_high": f1_ci.ci_high,
                **{f"sign_{k}": v for k, v in f1_sign.items()},
            }
        )
        summary_rows.append(
            {
                "repetition": int(rep),
                "metric": "omission_rise",
                "mean": om_ci.mean,
                "ci_low": om_ci.ci_low,
                "ci_high": om_ci.ci_high,
            }
        )
        summary_rows.append(
            {
                "repetition": int(rep),
                "metric": "hallucination_rise",
                "mean": hal_ci.mean,
                "ci_low": hal_ci.ci_low,
                "ci_high": hal_ci.ci_high,
            }
        )

    summary = pd.DataFrame(summary_rows).sort_values(["metric", "repetition"]).reset_index(drop=True)
    summary.to_csv(out_dir / "paired_effects_bootstrap_summary.csv", index=False)

    # DRE summary (by repetition)
    dre_summary_rows = []
    for rep in reps:
        if rep == 1:
            continue
        v = dre_pat[dre_pat["repetition"] == rep]["DRE"].to_numpy(dtype=float)
        dre_ci = _bootstrap_mean_ci(v)
        dre_sign = _sign_counts(v)
        dre_summary_rows.append(
            {
                "repetition": int(rep),
                "mean_dre": dre_ci.mean,
                "dre_ci_low": dre_ci.ci_low,
                "dre_ci_high": dre_ci.ci_high,
                **{f"sign_{k}": val for k, val in dre_sign.items()},
            }
        )
    dre_summary = pd.DataFrame(dre_summary_rows).sort_values("repetition").reset_index(drop=True)
    dre_summary.to_csv(out_dir / "dre_bootstrap_summary.csv", index=False)

    # plots (matplotlib only)
    import matplotlib.pyplot as plt

    plt.rcParams.update({"figure.dpi": 200, "savefig.dpi": 400, "font.size": 10})

    # Paired F1 drop with CI
    f1_rows = summary[summary["metric"] == "F1_drop"].copy()
    x = f1_rows["repetition"].astype(int).to_list()
    y = f1_rows["mean"].astype(float).to_list()
    ylo = f1_rows["ci_low"].astype(float).to_list()
    yhi = f1_rows["ci_high"].astype(float).to_list()
    plt.figure(figsize=(5.3, 3.2))
    plt.plot(x, y, marker="o", color="black", linewidth=1.6)
    plt.fill_between(x, ylo, yhi, color="gray", alpha=0.25, linewidth=0)
    plt.xscale("log", base=2)
    plt.xticks(x, [str(v) for v in x])
    plt.xlabel("Repetition level (x)")
    plt.ylabel("Paired F1 drop (1x -> rx)")
    plt.grid(True, axis="y", linestyle="--", linewidth=0.6, alpha=0.6)
    plt.tight_layout()
    plt.savefig(out_dir / "paired_f1_drop_with_ci.png")
    plt.close()

    # DRE with CI
    x = dre_summary["repetition"].astype(int).to_list()
    y = dre_summary["mean_dre"].astype(float).to_list()
    ylo = dre_summary["dre_ci_low"].astype(float).to_list()
    yhi = dre_summary["dre_ci_high"].astype(float).to_list()
    plt.figure(figsize=(5.3, 3.2))
    plt.axhline(0.0, color="black", linewidth=0.8, alpha=0.5)
    plt.plot(x, y, marker="o", color="black", linewidth=1.6)
    plt.fill_between(x, ylo, yhi, color="gray", alpha=0.25, linewidth=0)
    plt.xscale("log", base=2)
    plt.xticks(x, [str(v) for v in x])
    plt.xlabel("Repetition level (x)")
    plt.ylabel("Mean DRE (F1 drop diff)")
    plt.grid(True, axis="y", linestyle="--", linewidth=0.6, alpha=0.6)
    plt.tight_layout()
    plt.savefig(out_dir / "dre_with_ci.png")
    plt.close()

    # DRE distribution (boxplot) per repetition
    reps_no1 = [r for r in reps if r != 1]
    data = [dre_pat[dre_pat["repetition"] == r]["DRE"].astype(float).to_numpy() for r in reps_no1]
    plt.figure(figsize=(5.6, 3.2))
    plt.axhline(0.0, color="black", linewidth=0.8, alpha=0.5)
    plt.boxplot(data, labels=[str(r) for r in reps_no1], showfliers=False)
    plt.xlabel("Repetition level (x)")
    plt.ylabel("Per-patient DRE")
    plt.grid(True, axis="y", linestyle="--", linewidth=0.6, alpha=0.6)
    plt.tight_layout()
    plt.savefig(out_dir / "dre_distribution_boxplot.png")
    plt.close()

    # write a short markdown snippet for paper integration
    md_lines = [
        "# Paired effects + DRE (large-N synthetic replication)",
        "",
        f"- redundancy_root: `{redundancy_root}`",
        f"- control_root: `{control_root}`",
        f"- reps: `{reps}`",
        "",
        "## Mean DRE with 95% bootstrap CI (paired by patient)",
        "",
        "```",
        dre_summary.to_string(index=False),
        "```",
        "",
        "## Mean paired F1 drop with 95% bootstrap CI (redundancy condition)",
        "",
        "```",
        f1_rows[["repetition", "mean", "ci_low", "ci_high", "sign_n", "sign_n_pos", "sign_n_neg", "sign_n_zero"]].to_string(index=False),
        "```",
        "",
    ]
    (out_dir / "paired_effects_report.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--redundancy_root", required=True)
    ap.add_argument("--control_root", required=True)
    ap.add_argument("--reps", default="1,5,10,16")
    ap.add_argument("--out_dir", default="paper_artifacts/largeN_paired_effects")
    args = ap.parse_args()

    reps = [int(x.strip()) for x in args.reps.split(",") if x.strip()]
    run(
        redundancy_root=Path(args.redundancy_root),
        control_root=Path(args.control_root),
        reps=reps,
        out_dir=Path(args.out_dir),
    )

