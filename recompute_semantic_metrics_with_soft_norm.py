from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from evaluator import normalize_extraction, normalize_extraction_soft, score_against_gold


REPS = [1, 2, 5, 10, 16, 32]


@dataclass(frozen=True)
class RunRef:
    patient_id: str
    repetition: int
    run_id: str
    repaired_json: Path


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_runs(run_root: Path) -> Iterable[RunRef]:
    out_root = run_root / "outputs"
    for patient_dir in sorted(out_root.glob("patient_*")):
        patient_id = patient_dir.name
        for rep in REPS:
            rep_dir = patient_dir / f"rep_{rep}x"
            if not rep_dir.exists():
                continue
            for run_dir in sorted(rep_dir.glob("run_*")):
                repaired = run_dir / "repaired.json"
                if repaired.exists():
                    yield RunRef(
                        patient_id=patient_id,
                        repetition=rep,
                        run_id=run_dir.name,
                        repaired_json=repaired,
                    )


def _scaling_stats(df: pd.DataFrame, *, metric_col: str) -> pd.DataFrame:
    g = (
        df.groupby("repetition", as_index=False)[metric_col]
        .agg(n="count", mean="mean", std="std")
        .reset_index(drop=True)
    )
    g = g.rename(columns={"mean": f"{metric_col}_mean", "std": f"{metric_col}_std"})
    return g.sort_values("repetition").reset_index(drop=True)


def recompute(run_root: Path) -> None:
    metrics_dir = run_root / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for rr in _iter_runs(run_root):
        gt_path = Path("data") / rr.patient_id / "ground_truth" / f"{rr.patient_id}.json"
        if not gt_path.exists():
            raise FileNotFoundError(f"missing ground truth: {gt_path}")

        pred_raw = _read_json(rr.repaired_json)
        gold_raw = _read_json(gt_path)

        pred_strict = normalize_extraction(pred_raw, patient_id=rr.patient_id)
        gold_strict = normalize_extraction(gold_raw, patient_id=rr.patient_id)
        strict = score_against_gold(pred_strict, gold_strict)

        pred_soft = normalize_extraction_soft(pred_raw, patient_id=rr.patient_id)
        gold_soft = normalize_extraction_soft(gold_raw, patient_id=rr.patient_id)
        soft = score_against_gold(pred_soft, gold_soft)

        rows.append(
            {
                "patient_id": rr.patient_id,
                "repetition": rr.repetition,
                "run_id": rr.run_id,
                "micro_f1_strict": strict["micro_f1"],
                "micro_precision_strict": strict["micro_precision"],
                "micro_recall_strict": strict["micro_recall"],
                "omission_count_strict": strict["omission_count"],
                "hallucination_count_strict": strict["hallucination_count"],
                "micro_f1_soft": soft["micro_f1"],
                "micro_precision_soft": soft["micro_precision"],
                "micro_recall_soft": soft["micro_recall"],
                "omission_count_soft": soft["omission_count"],
                "hallucination_count_soft": soft["hallucination_count"],
            }
        )

    df = pd.DataFrame(rows)
    out_csv = metrics_dir / "semantic_metrics_strict_vs_soft.csv"
    df.to_csv(out_csv, index=False)

    strict_stats = _scaling_stats(df, metric_col="micro_f1_strict")
    soft_stats = _scaling_stats(df, metric_col="micro_f1_soft")
    combined = strict_stats.merge(soft_stats, on=["repetition", "n"], how="outer")
    combined.to_csv(metrics_dir / "redundancy_scaling_f1_strict_vs_soft.csv", index=False)

    # paired per-patient deltas (1x -> rep)
    pivot = df.groupby(["patient_id", "repetition"], as_index=False)[["micro_f1_strict", "micro_f1_soft"]].mean()
    wide = pivot.pivot(index="patient_id", columns="repetition", values=["micro_f1_strict", "micro_f1_soft"])
    wide.columns = [f"{a}_{b}x" for (a, b) in wide.columns]
    wide = wide.reset_index()
    for rep in REPS:
        if rep == 1:
            continue
        if f"micro_f1_strict_1x" in wide.columns and f"micro_f1_strict_{rep}x" in wide.columns:
            wide[f"delta_strict_{rep}x_minus_1x"] = wide[f"micro_f1_strict_{rep}x"] - wide["micro_f1_strict_1x"]
        if f"micro_f1_soft_1x" in wide.columns and f"micro_f1_soft_{rep}x" in wide.columns:
            wide[f"delta_soft_{rep}x_minus_1x"] = wide[f"micro_f1_soft_{rep}x"] - wide["micro_f1_soft_1x"]
    wide.to_csv(metrics_dir / "paired_patient_deltas_strict_vs_soft.csv", index=False)

    print(f"Wrote:\n- {out_csv}\n- {metrics_dir / 'redundancy_scaling_f1_strict_vs_soft.csv'}\n- {metrics_dir / 'paired_patient_deltas_strict_vs_soft.csv'}")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--run_root", type=str, required=True)
    args = ap.parse_args()
    recompute(Path(args.run_root))
