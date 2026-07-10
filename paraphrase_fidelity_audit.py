from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from evaluator import canonicalize_medication, canonicalize_condition


ENTITY_TYPES = ("conditions", "medications", "observations", "procedures")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _norm(s: str) -> str:
    s = s.lower().strip()
    s = " ".join(s.split())
    return s


def audit(run_root: Path, out_dir: Path, sample_n: int = 50) -> None:
    """
    Heuristic fidelity audit:
    - For each paraphrase text file, check whether each gold entity string appears as a substring.
    - This is not a semantic proof, but it catches obvious paraphrase drift (drops/rewrites that lose mention).
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for pid_dir in sorted((run_root / "docs").glob("patient_*")):
        pid = pid_dir.name
        gt_path = Path("data") / pid / "ground_truth" / f"{pid}.json"
        if not gt_path.exists():
            continue
        gt = _read_json(gt_path)
        # Conditions/procedures: substring mention of canonicalized form is reasonable.
        # Medications: check ingredient-like canonicalization (dose/frequency may vary).
        # Observations: often contain numbers/vitals/labs; substring checks are too brittle,
        # so we exclude observations from this mention audit and treat them as out-of-scope.
        gold: dict[str, list[str]] = {}
        gold["conditions"] = [canonicalize_condition(str(x)) for x in (gt.get("conditions") or [])]
        gold["procedures"] = [_norm(str(x)) for x in (gt.get("procedures") or [])]
        gold["medications"] = [canonicalize_medication(str(x)) for x in (gt.get("medications") or [])]
        gold["observations"] = []

        for para_path in sorted((pid_dir / "paraphrases").glob("paraphrase_*.txt")):
            txt = _norm(_read_text(para_path))
            for t in ("conditions", "medications", "procedures"):
                missing = [e for e in gold[t] if e and (e not in txt)]
                rows.append(
                    {
                        "patient_id": pid,
                        "paraphrase_file": str(para_path).replace("\\", "/"),
                        "entity_type": t,
                        "gold_n": len(gold[t]),
                        "missing_mentions_n": len(missing),
                        "missing_mentions_examples": "; ".join(missing[:3]),
                    }
                )

    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "paraphrase_fidelity_mentions.csv", index=False)

    # aggregate
    agg = (
        df.groupby(["entity_type"], as_index=False)
        .agg(
            paraphrase_items=("paraphrase_file", "nunique"),
            gold_total=("gold_n", "sum"),
            missing_total=("missing_mentions_n", "sum"),
        )
        .sort_values("entity_type")
    )
    agg["missing_rate"] = agg["missing_total"] / agg["gold_total"].where(agg["gold_total"] > 0, 1)
    agg.to_csv(out_dir / "paraphrase_fidelity_summary.csv", index=False)

    # worst paraphrases by missing mentions
    worst = (
        df.groupby(["patient_id", "paraphrase_file"], as_index=False)["missing_mentions_n"]
        .sum()
        .sort_values("missing_mentions_n", ascending=False)
        .head(sample_n)
    )
    worst.to_csv(out_dir / "paraphrase_fidelity_worst.csv", index=False)

    md = [
        "# Paraphrase Fidelity Audit (Heuristic)",
        "",
        f"- run_root: `{run_root}`",
        "",
        "This audit checks whether ground-truth entity strings (normalized) appear as substrings in the generated paraphrases.",
        "It is a conservative *mention-preservation* diagnostic (not a semantic equivalence proof).",
        "",
        "## Summary by entity type",
        "```",
        agg.to_string(index=False),
        "```",
        "",
        "## Worst paraphrases (highest missing-mention counts)",
        "```",
        worst.to_string(index=False),
        "```",
        "",
        "Artifacts:",
        f"- `{(out_dir / 'paraphrase_fidelity_mentions.csv').as_posix()}`",
        f"- `{(out_dir / 'paraphrase_fidelity_summary.csv').as_posix()}`",
        f"- `{(out_dir / 'paraphrase_fidelity_worst.csv').as_posix()}`",
        "",
    ]
    (out_dir / "paraphrase_fidelity_audit.md").write_text("\n".join(md), encoding="utf-8")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--run_root", required=True)
    ap.add_argument("--out_dir", default="paper_artifacts/paraphrase_fidelity_audit")
    ap.add_argument("--worst_n", type=int, default=30)
    args = ap.parse_args()
    audit(Path(args.run_root), Path(args.out_dir), sample_n=int(args.worst_n))

