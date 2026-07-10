from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ENTITY_TYPES = ("conditions", "medications", "observations", "procedures")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _norm(s: str) -> str:
    s = s.strip().lower()
    s = " ".join(s.split())
    return s


def _find_first_pos(text: str, needle: str) -> float | None:
    """
    Returns fractional position of first match (0..1) or None.
    Uses a simple escaped substring match.
    """
    if not needle:
        return None
    t = text.lower()
    n = needle.lower()
    idx = t.find(n)
    if idx < 0:
        return None
    return idx / max(len(t), 1)


def analyze(run_root: Path, out_path: Path) -> None:
    sem = pd.read_csv(run_root / "metrics" / "semantic_metrics.csv")
    # choose run 1 only for interpretability
    sem = sem[sem["run"] == 1].copy()
    rep_hi = int(sem["repetition"].max())

    rows = []
    for pid in sorted(sem["patient_id"].unique().tolist()):
        # load base document text (rep 1) that went to model
        doc_path = run_root / "outputs" / pid / "rep_1x" / "run_01" / "document_source.txt"
        if not doc_path.exists():
            continue
        doc = _read_text(doc_path)
        gt = _read_json(Path("data") / pid / "ground_truth" / f"{pid}.json")
        pred_hi = _read_json(run_root / "outputs" / pid / f"rep_{rep_hi}x" / "run_01" / "repaired.json")

        # build sets
        for t in ENTITY_TYPES:
            gold_items = [_norm(str(x)) for x in (gt.get(t) or [])]
            pred_items = {_norm(str(x)) for x in (pred_hi.get(t) or [])}
            for ent in gold_items:
                pos = _find_first_pos(doc, ent)
                missed = 1 if ent not in pred_items else 0
                rows.append(
                    {
                        "patient_id": pid,
                        "entity_type": t,
                        "entity": ent,
                        "pos_frac": pos,
                        "missed_at_high_rep": missed,
                    }
                )

    df = pd.DataFrame(rows).dropna(subset=["pos_frac"])
    if df.empty:
        out_path.write_text("# Position sensitivity\n\nNo entities were found in document text via substring match.\n", encoding="utf-8")
        return

    # bin into terciles
    df["pos_bin"] = pd.cut(df["pos_frac"], bins=[0.0, 0.33, 0.66, 1.0], labels=["early", "middle", "late"], include_lowest=True)
    agg = df.groupby(["entity_type", "pos_bin"], as_index=False).agg(
        n=("missed_at_high_rep", "count"),
        miss_rate=("missed_at_high_rep", "mean"),
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path.parent / "position_sensitivity_entities.csv", index=False)
    agg.to_csv(out_path.parent / "position_sensitivity_summary.csv", index=False)

    md = [
        "# Position sensitivity (descriptive)",
        "",
        f"- run_root: `{run_root}`",
        f"- high repetition: `{rep_hi}x` (run_01 only)",
        "",
        "This is a coarse diagnostic: we locate gold entity strings in the 1x document via substring match and measure whether the entity is omitted at the highest repetition.",
        "",
        "```",
        agg.to_string(index=False),
        "```",
        "",
    ]
    out_path.write_text("\n".join(md), encoding="utf-8")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--run_root", required=True)
    ap.add_argument("--out", default="paper_artifacts/position_sensitivity.md")
    args = ap.parse_args()
    analyze(Path(args.run_root), Path(args.out))

