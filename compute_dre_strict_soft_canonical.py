from __future__ import annotations

from pathlib import Path

import pandas as pd


def _mean_by_rep(df: pd.DataFrame, col: str) -> pd.Series:
    return df.groupby("repetition")[col].mean().sort_index()


def compute(red_root: Path, ctl_root: Path, out_path: Path) -> None:
    red = pd.read_csv(red_root / "metrics" / "semantic_metrics_strict_soft_canonical.csv")
    ctl = pd.read_csv(ctl_root / "metrics" / "semantic_metrics_strict_soft_canonical.csv")

    metrics = [
        "micro_f1_strict",
        "micro_f1_soft",
        "micro_f1_canonical",
    ]

    rows = []
    for m in metrics:
        r = _mean_by_rep(red, m)
        c = _mean_by_rep(ctl, m)
        base_r = float(r.loc[1])
        base_c = float(c.loc[1])
        for rep in r.index.tolist():
            drop_r = base_r - float(r.loc[rep])
            drop_c = base_c - float(c.loc[rep])
            rows.append(
                {
                    "metric": m,
                    "repetition": int(rep),
                    "F1_drop_redundancy": drop_r,
                    "F1_drop_control": drop_c,
                    "DRE": drop_r - drop_c,
                }
            )

    out = pd.DataFrame(rows).sort_values(["metric", "repetition"]).reset_index(drop=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(out_path, index=False)
    print(f"Wrote: {out_path}")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--redundancy_root", required=True)
    ap.add_argument("--control_root", required=True)
    ap.add_argument("--out", default="paper_artifacts/dre_strict_soft_canonical.csv")
    args = ap.parse_args()
    compute(Path(args.redundancy_root), Path(args.control_root), Path(args.out))

