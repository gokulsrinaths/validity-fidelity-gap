from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ChangePoint:
    from_rep: int
    to_rep: int
    delta: float


def analyze(by_rep_csv: Path, out_path: Path) -> None:
    df = pd.read_csv(by_rep_csv).sort_values("repetition").reset_index(drop=True)
    reps = df["repetition"].astype(int).tolist()
    f1 = df["f1_mean"].astype(float).tolist()
    om = df["omission_mean"].astype(float).tolist() if "omission_mean" in df.columns else None
    hal = df["halluc_mean"].astype(float).tolist() if "halluc_mean" in df.columns else None

    def step_deltas(xs: list[float]) -> list[float]:
        return [xs[i] - xs[i - 1] for i in range(1, len(xs))]

    f1_d = step_deltas(f1)
    # collapse = most negative delta for F1 (largest drop)
    if f1_d:
        i = int(np.argmin(f1_d))
        f1_cp = ChangePoint(from_rep=reps[i], to_rep=reps[i + 1], delta=float(f1_d[i]))
    else:
        f1_cp = ChangePoint(from_rep=reps[0], to_rep=reps[0], delta=0.0)

    md = [
        "# Change-point (step-drop) summary (descriptive)",
        "",
        f"- source: `{by_rep_csv}`",
        "",
        "## Largest step drop in mean F1",
        f"- span: `{f1_cp.from_rep}x -> {f1_cp.to_rep}x`",
        f"- delta_F1: `{f1_cp.delta:.4f}` (more negative = larger drop)",
        "",
        "## Step deltas table",
        "",
        "```",
        pd.DataFrame(
            {
                "from_rep": reps[:-1],
                "to_rep": reps[1:],
                "delta_f1": f1_d,
            }
        ).to_string(index=False),
        "```",
        "",
        "Interpretation: this is a simple descriptive diagnostic, not a formal statistical change-point test.",
        "",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(md), encoding="utf-8")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--by_rep_csv", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    analyze(Path(args.by_rep_csv), Path(args.out))

