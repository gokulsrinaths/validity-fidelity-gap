from __future__ import annotations

import argparse
from pathlib import Path

import json
import pandas as pd

from corrected_full_pilot import postprocess


def _rebuild_metrics_if_missing(run_root: Path) -> None:
    metrics_dir = run_root / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    sem_csv = metrics_dir / "semantic_metrics.csv"
    st_csv = metrics_dir / "structural_metrics.csv"
    if sem_csv.exists() and st_csv.exists():
        return

    sem_rows = []
    st_rows = []
    for path in run_root.glob("outputs/**/semantic_metrics.json"):
        try:
            sem_rows.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    for path in run_root.glob("outputs/**/structural_metrics.json"):
        try:
            st_rows.append(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue

    if sem_rows:
        pd.DataFrame(sem_rows).to_csv(sem_csv, index=False)
    if st_rows:
        pd.DataFrame(st_rows).to_csv(st_csv, index=False)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--run_root",
        type=str,
        default="data/runs/full_pilot_20260520_192127",
        help="Existing full pilot run_root to postprocess (no API calls).",
    )
    args = ap.parse_args()
    run_root = Path(args.run_root)
    _rebuild_metrics_if_missing(run_root)
    return postprocess(run_root)


if __name__ == "__main__":
    raise SystemExit(main())
