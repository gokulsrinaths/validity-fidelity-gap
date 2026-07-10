from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from analysis import summarize_by_repetition
from run_experiments import compute_variance_metrics


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def postprocess(*, run_root: Path) -> int:
    run_root = Path(run_root)
    outputs_root = run_root / "outputs"
    if not outputs_root.exists():
        raise SystemExit(f"Missing outputs/: {outputs_root}")

    metrics_dir = run_root / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)

    sem_paths = list(outputs_root.rglob("semantic_metrics.json"))
    st_paths = list(outputs_root.rglob("structural_metrics.json"))
    if not sem_paths or not st_paths:
        raise SystemExit("No per-call metric JSONs found (semantic_metrics.json / structural_metrics.json).")

    sem_rows = [_read_json(p) for p in sem_paths]
    st_rows = [_read_json(p) for p in st_paths]

    sem = pd.DataFrame(sem_rows)
    st = pd.DataFrame(st_rows)

    sem_csv = metrics_dir / "semantic_metrics.csv"
    st_csv = metrics_dir / "structural_metrics.csv"
    sem.to_csv(sem_csv, index=False)
    st.to_csv(st_csv, index=False)

    var_df = compute_variance_metrics(sem, st)
    var_csv = metrics_dir / "variance_metrics.csv"
    var_df.to_csv(var_csv, index=False)

    by_rep = summarize_by_repetition(sem, st, var_df)
    by_rep.to_csv(metrics_dir / "redundancy_scaling_statistics.csv", index=False)

    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Postprocess an existing run_root from per-call metric JSONs only.")
    ap.add_argument("--run_root", type=str, required=True)
    args = ap.parse_args()
    return postprocess(run_root=Path(args.run_root))


if __name__ == "__main__":
    raise SystemExit(main())

