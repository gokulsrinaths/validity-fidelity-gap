from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from analysis import summarize_by_repetition
from evaluator import divergence_score, normalize_extraction
from plotting import generate_structural_plots, generate_variance_plots
from run_experiments import compute_variance_metrics


ENTITY_FIELDS = ("conditions", "medications", "observations", "procedures")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_repaired(run_root: Path, patient_id: str, rep: int, run_idx: int) -> dict[str, Any]:
    p = run_root / "outputs" / patient_id / f"rep_{rep}x" / f"run_{run_idx:02d}" / "repaired.json"
    return _read_json(p)


def _compute_drift_cols(run_root: Path, sem: pd.DataFrame, *, baseline_rep: int) -> pd.DataFrame:
    """
    Adds drift_vs_1x, drift_vs_gold, drift_score to a semantic metrics frame based on stored repaired.json.
    For midrange-only runs, we use baseline_rep (default 5) as the within-patient baseline.
    """
    sem = sem.copy()
    sem["drift_vs_1x"] = 0.0
    sem["drift_vs_gold"] = 0.0
    sem["drift_score"] = 0.0

    for pid, g in sem.groupby("patient_id"):
        gt_path = Path("data") / pid / "ground_truth" / f"{pid}.json"
        gold_raw = _read_json(gt_path)
        gold_norm = normalize_extraction(gold_raw, patient_id=pid)

        # baseline: baseline_rep + run 1 if present, else smallest rep/run for that patient
        base_rows = g[(g["repetition"] == baseline_rep) & (g["run"] == 1)]
        if base_rows.empty:
            base_rows = g.sort_values(["repetition", "run"]).head(1)
        base_rep = int(base_rows.iloc[0]["repetition"])
        base_run = int(base_rows.iloc[0]["run"])
        base_obj = _load_repaired(run_root, pid, base_rep, base_run)
        base_norm = normalize_extraction(base_obj, patient_id=pid)

        for idx, row in g.iterrows():
            rep = int(row["repetition"])
            run_idx = int(row["run"])
            pred_obj = _load_repaired(run_root, pid, rep, run_idx)
            pred_norm = normalize_extraction(pred_obj, patient_id=pid)

            d1 = divergence_score(pred_norm, base_norm)
            dg = divergence_score(pred_norm, gold_norm)
            drift_vs_1x = float(d1["jaccard_distance"])
            drift_vs_gold = float(dg["jaccard_distance"])
            sem.loc[idx, "drift_vs_1x"] = drift_vs_1x
            sem.loc[idx, "drift_vs_gold"] = drift_vs_gold
            sem.loc[idx, "drift_score"] = 0.5 * drift_vs_1x + 0.5 * drift_vs_gold

    return sem


def postprocess(run_root: Path, *, baseline_rep: int = 5) -> None:
    metrics_dir = run_root / "metrics"
    plots_dir = run_root / "plots"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)

    sem_path = metrics_dir / "semantic_metrics.csv"
    st_path = metrics_dir / "structural_metrics.csv"
    if not sem_path.exists() or not st_path.exists():
        raise FileNotFoundError("Expected metrics/semantic_metrics.csv and metrics/structural_metrics.csv to exist.")

    sem = pd.read_csv(sem_path)
    st = pd.read_csv(st_path)

    # ensure columns exist
    sem = _compute_drift_cols(run_root, sem, baseline_rep=baseline_rep)
    sem.to_csv(sem_path, index=False)

    variance = compute_variance_metrics(sem, st)
    variance.to_csv(metrics_dir / "variance_metrics.csv", index=False)

    by_rep = summarize_by_repetition(sem, st, variance_df=variance)
    by_rep.to_csv(metrics_dir / "redundancy_scaling_statistics.csv", index=False)

    # plots expect CSV paths
    generate_structural_plots(st_path, plots_dir)
    generate_variance_plots(metrics_dir / "variance_metrics.csv", plots_dir)

    print("Wrote:")
    print(f"- {metrics_dir / 'redundancy_scaling_statistics.csv'}")
    print(f"- {metrics_dir / 'variance_metrics.csv'}")
    print(f"- {plots_dir}")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--run_root", required=True)
    ap.add_argument("--baseline_rep", type=int, default=5)
    args = ap.parse_args()
    postprocess(Path(args.run_root), baseline_rep=int(args.baseline_rep))

