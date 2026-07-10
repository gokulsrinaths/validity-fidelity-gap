from __future__ import annotations

import json
from dataclasses import dataclass
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


def _diff_sets(pred: dict[str, Any], gold: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for t in ENTITY_TYPES:
        p = set(_norm_list(pred.get(t)))
        g = set(_norm_list(gold.get(t)))
        out[t] = {
            "missing": sorted(g - p),
            "hallucinated": sorted(p - g),
            "matched": sorted(p & g),
        }
    return out


def sample(
    *,
    redundancy_root: Path,
    reps: list[int],
    out_path: Path,
    n_cases: int = 10,
) -> None:
    sem = pd.read_csv(redundancy_root / "metrics" / "semantic_metrics.csv")
    # pick rep max and rep 1, using run=1 for stability
    rep_hi = max(reps)
    subset = sem[(sem["repetition"].isin([1, rep_hi])) & (sem["run"] == 1)].copy()
    # compute per patient delta
    p = subset.pivot(index="patient_id", columns="repetition", values="micro_f1")
    p["delta"] = p[rep_hi] - p[1]
    worst = p.sort_values("delta").head(n_cases).reset_index()
    best = p.sort_values("delta", ascending=False).head(n_cases).reset_index()

    def case_block(pid: str) -> str:
        gt_path = Path("data") / pid / "ground_truth" / f"{pid}.json"
        gold = _read_json(gt_path)
        pred1 = _read_json(redundancy_root / "outputs" / pid / "rep_1x" / "run_01" / "repaired.json")
        predh = _read_json(redundancy_root / "outputs" / pid / f"rep_{rep_hi}x" / "run_01" / "repaired.json")
        d1 = _diff_sets(pred1, gold)
        dh = _diff_sets(predh, gold)
        lines = [f"## {pid}", "", f"- rep_hi: `{rep_hi}x`", ""]
        for t in ENTITY_TYPES:
            lines += [
                f"### {t}",
                f"- missing@1x: `{len(d1[t]['missing'])}`; halluc@1x: `{len(d1[t]['hallucinated'])}`",
                f"- missing@{rep_hi}x: `{len(dh[t]['missing'])}`; halluc@{rep_hi}x: `{len(dh[t]['hallucinated'])}`",
            ]
            if dh[t]["missing"]:
                lines.append(f"- example missing@{rep_hi}x: `{dh[t]['missing'][:3]}`")
            if dh[t]["hallucinated"]:
                lines.append(f"- example halluc@{rep_hi}x: `{dh[t]['hallucinated'][:3]}`")
            lines.append("")
        return "\n".join(lines)

    md = [
        "# Qualitative Cases (auto-sampled)",
        "",
        f"- redundancy_root: `{redundancy_root}`",
        f"- selection: run_01, reps 1x vs {rep_hi}x",
        "",
        "## Worst degradation cases (lowest F1 delta)",
        "",
    ]
    for pid in worst["patient_id"].tolist():
        md.append(case_block(pid))

    md += ["", "## Best / most stable cases (highest F1 delta)", ""]
    for pid in best["patient_id"].tolist():
        md.append(case_block(pid))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(md), encoding="utf-8")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--redundancy_root", required=True)
    ap.add_argument("--reps", default="1,2,5,10,16,32")
    ap.add_argument("--out", default="paper_artifacts/qualitative_cases.md")
    ap.add_argument("--n", type=int, default=8)
    args = ap.parse_args()

    reps = [int(x.strip()) for x in args.reps.split(",") if x.strip()]
    sample(redundancy_root=Path(args.redundancy_root), reps=reps, out_path=Path(args.out), n_cases=int(args.n))

