from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd


ENTITY_FIELDS = ("conditions", "medications", "observations", "procedures")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _norm(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\w\s\-/().%]", "", s)
    return s


def _entity_strings(gt: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for f in ENTITY_FIELDS:
        xs = gt.get(f, [])
        if xs is None:
            xs = []
        if not isinstance(xs, list):
            xs = [xs]
        for x in xs:
            out.append(_norm(str(x)))
    # unique
    seen = set()
    uniq = []
    for x in out:
        if x and x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def audit_filler_quality(*, control_root: Path, out_md: Path) -> pd.DataFrame:
    """
    Scans control documents for overlaps with ground-truth entity strings.
    This is a conservative lexical overlap check (not semantic).
    """
    docs_root = control_root / "control_docs"
    if not docs_root.exists():
        raise RuntimeError(f"Missing control_docs folder: {docs_root}")

    rows: list[dict[str, Any]] = []

    for pid_dir in sorted(docs_root.glob("patient_*")):
        pid = pid_dir.name
        gt_path = Path("data") / pid / "ground_truth" / f"{pid}.json"
        if not gt_path.exists():
            continue
        gt = _read_json(gt_path)
        entities = _entity_strings(gt)

        for rep_dir in sorted(pid_dir.glob("rep_*x")):
            rep = int(rep_dir.name.replace("rep_", "").replace("x", ""))
            control_txt = rep_dir / "control_document.txt"
            if not control_txt.exists():
                continue
            text = _norm(control_txt.read_text(encoding="utf-8"))

            hits = []
            for ent in entities:
                # require substring match on normalized strings
                if ent and ent in text:
                    hits.append(ent)

            rows.append(
                {
                    "patient_id": pid,
                    "repetition": rep,
                    "gt_entities_n": len(entities),
                    "overlap_entities_n": len(hits),
                    "overlap_frac": (len(hits) / len(entities)) if entities else 0.0,
                    "overlap_entities": "; ".join(hits[:20]),
                }
            )

    df = pd.DataFrame(rows).sort_values(["patient_id", "repetition"])

    by_rep = df.groupby("repetition", as_index=False).agg(
        overlap_entities_mean=("overlap_entities_n", "mean"),
        overlap_frac_mean=("overlap_frac", "mean"),
        overlap_any_rate=("overlap_entities_n", lambda s: float((s > 0).mean())),
    )

    lines = [
        "# Filler Quality Audit (Lexical Overlap Check)",
        "",
        "This audits whether the filler-control documents contain lexical overlaps with ground-truth entity strings.",
        "It is a conservative substring check on normalized text; it may undercount paraphrases and overcount incidental matches.",
        "",
        f"- control_root: `{control_root}`",
        "",
        "## Overlap summary by repetition",
        "```",
        by_rep.to_string(index=False),
        "```",
        "",
        "## Notes",
        "- Any nonzero overlap does not necessarily imply leakage of *facts*, but it is a red flag for control purity.",
        "- If overlap is frequent, consider replacing filler with a curated external neutral corpus and re-running control.",
        "",
    ]
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    df.to_csv(out_md.with_suffix(".csv"), index=False)
    return df


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--control_root", type=str, default="data/runs/full_pilot_control_20260520_235546")
    ap.add_argument("--out_md", type=str, default="data/runs/full_pilot_control_20260520_235546/filler_quality_audit.md")
    args = ap.parse_args()

    audit_filler_quality(control_root=Path(args.control_root), out_md=Path(args.out_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

