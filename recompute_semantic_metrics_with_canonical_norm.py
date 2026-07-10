from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from evaluator import normalize_extraction, normalize_extraction_canonical, normalize_extraction_soft, score_against_gold


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
        pid = patient_dir.name
        for rep_dir in sorted(patient_dir.glob("rep_*x")):
            m = rep_dir.name
            rep = int(m.replace("rep_", "").replace("x", ""))
            for run_dir in sorted(rep_dir.glob("run_*")):
                repaired = run_dir / "repaired.json"
                if repaired.exists():
                    yield RunRef(patient_id=pid, repetition=rep, run_id=run_dir.name, repaired_json=repaired)


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

        pred_can = normalize_extraction_canonical(pred_raw, patient_id=rr.patient_id)
        gold_can = normalize_extraction_canonical(gold_raw, patient_id=rr.patient_id)
        can = score_against_gold(pred_can, gold_can)

        rows.append(
            {
                "patient_id": rr.patient_id,
                "repetition": rr.repetition,
                "run_id": rr.run_id,
                "micro_f1_strict": strict["micro_f1"],
                "micro_f1_soft": soft["micro_f1"],
                "micro_f1_canonical": can["micro_f1"],
                "omission_count_strict": strict["omission_count"],
                "hallucination_count_strict": strict["hallucination_count"],
                "omission_count_canonical": can["omission_count"],
                "hallucination_count_canonical": can["hallucination_count"],
            }
        )

    df = pd.DataFrame(rows)
    out_csv = metrics_dir / "semantic_metrics_strict_soft_canonical.csv"
    df.to_csv(out_csv, index=False)

    # scaling summary
    agg = df.groupby("repetition", as_index=False).agg(
        n=("micro_f1_strict", "count"),
        micro_f1_strict_mean=("micro_f1_strict", "mean"),
        micro_f1_soft_mean=("micro_f1_soft", "mean"),
        micro_f1_canonical_mean=("micro_f1_canonical", "mean"),
    )
    agg.to_csv(metrics_dir / "redundancy_scaling_f1_strict_soft_canonical.csv", index=False)

    print(f"Wrote:\n- {out_csv}\n- {metrics_dir / 'redundancy_scaling_f1_strict_soft_canonical.csv'}")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--run_root", required=True)
    args = ap.parse_args()
    recompute(Path(args.run_root))

