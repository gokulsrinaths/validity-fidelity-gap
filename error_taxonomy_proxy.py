from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


ENTITY_TYPES = ("conditions", "medications", "observations", "procedures")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _norm_list(x: Any) -> list[str]:
    if x is None:
        return []
    if not isinstance(x, list):
        x = [x]
    out = []
    for it in x:
        s = str(it).strip().lower()
        s = " ".join(s.split())
        if s:
            out.append(s)
    return list(dict.fromkeys(out))


def _counts(pred: dict[str, Any], gold: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for t in ENTITY_TYPES:
        p = set(_norm_list(pred.get(t)))
        g = set(_norm_list(gold.get(t)))
        rows.append(
            {
                "entity_type": t,
                "tp": len(p & g),
                "fp": len(p - g),
                "fn": len(g - p),
                "pred_n": len(p),
                "gold_n": len(g),
            }
        )
    return rows


def analyze(run_root: Path, out_path: Path) -> None:
    sem = pd.read_csv(run_root / "metrics" / "semantic_metrics.csv")
    rep_hi = int(sem["repetition"].max())
    # run 1 only for simplicity
    sem = sem[(sem["run"] == 1) & (sem["repetition"].isin([1, rep_hi]))]
    out_rows = []
    for pid in sorted(sem["patient_id"].unique().tolist()):
        gt = _read_json(Path("data") / pid / "ground_truth" / f"{pid}.json")
        p1 = _read_json(run_root / "outputs" / pid / "rep_1x" / "run_01" / "repaired.json")
        ph = _read_json(run_root / "outputs" / pid / f"rep_{rep_hi}x" / "run_01" / "repaired.json")
        for rep, pred in [(1, p1), (rep_hi, ph)]:
            for row in _counts(pred, gt):
                out_rows.append({"patient_id": pid, "repetition": rep, **row})

    df = pd.DataFrame(out_rows)
    df.to_csv(out_path.parent / "error_taxonomy_proxy_counts.csv", index=False)
    # summarize by rep+type
    agg = df.groupby(["repetition", "entity_type"], as_index=False).agg(
        tp=("tp", "sum"),
        fp=("fp", "sum"),
        fn=("fn", "sum"),
        pred_n=("pred_n", "sum"),
        gold_n=("gold_n", "sum"),
    )
    agg["precision"] = agg["tp"] / (agg["tp"] + agg["fp"]).replace(0, pd.NA)
    agg["recall"] = agg["tp"] / (agg["tp"] + agg["fn"]).replace(0, pd.NA)
    agg.to_csv(out_path.parent / "error_taxonomy_proxy_summary.csv", index=False)

    md = [
        "# Error taxonomy (proxy by entity type)",
        "",
        f"- run_root: `{run_root}`",
        f"- comparison: 1x vs {rep_hi}x (run_01 only)",
        "",
        "This is a coarse proxy taxonomy: TP/FP/FN broken down by entity type. It supports statements like “medications accrue more FN under redundancy than conditions”.",
        "",
        "```",
        agg.to_string(index=False),
        "```",
        "",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(md), encoding="utf-8")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--run_root", required=True)
    ap.add_argument("--out", default="paper_artifacts/error_taxonomy_proxy.md")
    args = ap.parse_args()
    analyze(Path(args.run_root), Path(args.out))

