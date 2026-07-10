from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def _read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def _bootstrap_mean_ci(xs: list[float], *, n: int = 5000, seed: int = 1337) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    x = np.asarray(xs, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return float("nan"), float("nan"), float("nan")
    mean = float(x.mean())
    if len(x) == 1:
        return mean, mean, mean
    idx = rng.integers(0, len(x), size=(n, len(x)))
    boots = x[idx].mean(axis=1)
    lo = float(np.quantile(boots, 0.025))
    hi = float(np.quantile(boots, 0.975))
    return mean, lo, hi


def per_patient_dre_from_control_vs_redundancy(
    *,
    redundancy_root: Path,
    control_root: Path,
    out_dir: Path,
) -> None:
    """
    Computes per-patient DRE for the 8B 3-run full pilot pair:
    DRE(pid, rep) = (F1_1x - F1_rep)_redundancy - (F1_1x - F1_rep)_control
    using per-call semantic_metrics.csv from each run.
    """
    sem_r = _read_csv(redundancy_root / "metrics" / "semantic_metrics.csv")
    sem_c = _read_csv(control_root / "metrics" / "semantic_metrics.csv")

    # Aggregate to patient/repetition mean F1 across runs.
    r = sem_r.groupby(["patient_id", "repetition"], as_index=False)["micro_f1"].mean().rename(columns={"micro_f1": "f1"})
    c = sem_c.groupby(["patient_id", "repetition"], as_index=False)["micro_f1"].mean().rename(columns={"micro_f1": "f1"})

    # Baseline per patient at 1x
    r_base = r[r["repetition"] == 1][["patient_id", "f1"]].rename(columns={"f1": "f1_1x_r"})
    c_base = c[c["repetition"] == 1][["patient_id", "f1"]].rename(columns={"f1": "f1_1x_c"})

    r2 = r.merge(r_base, on="patient_id", how="left")
    c2 = c.merge(c_base, on="patient_id", how="left")

    r2["drop_r"] = r2["f1_1x_r"] - r2["f1"]
    c2["drop_c"] = c2["f1_1x_c"] - c2["f1"]

    merged = r2.merge(c2[["patient_id", "repetition", "drop_c"]], on=["patient_id", "repetition"], how="inner")
    merged["DRE"] = merged["drop_r"] - merged["drop_c"]
    merged = merged.sort_values(["patient_id", "repetition"])

    out_dir.mkdir(parents=True, exist_ok=True)
    merged.to_csv(out_dir / "per_patient_DRE_llama8b.csv", index=False)

    # Summaries per repetition
    rep_summary = merged.groupby("repetition", as_index=False)["DRE"].agg(["mean", "std", "count"]).reset_index().rename(columns={"index": "repetition"})
    rep_summary.to_csv(out_dir / "per_rep_DRE_llama8b.csv", index=False)

    # Overall summary excluding 1x
    xs = merged[merged["repetition"] != 1]["DRE"].astype(float).tolist()
    mean, lo, hi = _bootstrap_mean_ci(xs)
    md = [
        "# Per-Patient DRE (LLaMA-8B full pilots)",
        "",
        f"- redundancy_root: `{redundancy_root}`",
        f"- control_root: `{control_root}`",
        "",
        "Files:",
        "- `per_patient_DRE_llama8b.csv`",
        "- `per_rep_DRE_llama8b.csv`",
        "",
        "Aggregate DRE excluding 1x:",
        f"- mean: `{mean:.3f}` (bootstrap 95% CI: `[{lo:.3f}, {hi:.3f}]`) across {len(xs)} patient×rep cells",
        "",
    ]
    (out_dir / "per_patient_DRE_llama8b.md").write_text("\n".join(md) + "\n", encoding="utf-8")


def main() -> int:
    out_dir = Path("paper_artifacts")
    per_patient_dre_from_control_vs_redundancy(
        redundancy_root=Path("data/runs/full_pilot_20260520_192127"),
        control_root=Path("data/runs/full_pilot_control_20260520_235546"),
        out_dir=out_dir,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

