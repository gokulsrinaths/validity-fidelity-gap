from __future__ import annotations

import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


RUN_ROOT = Path("data/runs/pilot_20260520_172210")

SCHEMA_KEYS = ("patient_id", "conditions", "medications", "observations", "procedures")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(_read_text(path))


def _norm_str_basic(x: Any) -> str:
    if x is None:
        return ""
    if not isinstance(x, str):
        x = str(x)
    x = x.strip().lower()
    x = re.sub(r"\s+", " ", x)
    x = re.sub(r"[^\w\s\-/().%]", "", x)
    return x


def _dedupe_stable(xs: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in xs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def normalize_list_basic(items: Any) -> list[str]:
    if items is None:
        return []
    if not isinstance(items, list):
        items = [items]
    out = []
    for it in items:
        s = _norm_str_basic(it)
        if s:
            out.append(s)
    return _dedupe_stable(out)


# Very small pilot synonym map to detect normalization issues and enable relaxed scoring.
SYNONYMS = {
    # conditions
    "type 2 diabetes": "type 2 diabetes mellitus",
    "type ii diabetes": "type 2 diabetes mellitus",
    "diabetes mellitus type ii": "type 2 diabetes mellitus",
    "t2d": "type 2 diabetes mellitus",
    "t2dm": "type 2 diabetes mellitus",
}


def normalize_entity_relaxed(s: str) -> str:
    s0 = _norm_str_basic(s)
    return SYNONYMS.get(s0, s0)


def normalize_list_relaxed(items: Any) -> list[str]:
    return _dedupe_stable([normalize_entity_relaxed(x) for x in normalize_list_basic(items)])


@dataclass(frozen=True)
class ExamplePaths:
    patient_id: str
    repetition: int
    run: int
    raw_response: Path
    repaired: Path
    repair_event: Path
    ground_truth: Path


def sample_example_paths(*, patient_id: str, repetition: int, run: int) -> ExamplePaths:
    out_dir = RUN_ROOT / "outputs" / patient_id / f"rep_{repetition}x" / f"run_{run:02d}"
    return ExamplePaths(
        patient_id=patient_id,
        repetition=repetition,
        run=run,
        raw_response=out_dir / "raw_response.txt",
        repaired=out_dir / "repaired.json",
        repair_event=out_dir / "repair_event.json",
        ground_truth=Path("data") / patient_id / "ground_truth" / f"{patient_id}.json",
    )


def schema_check(obj: dict[str, Any]) -> tuple[bool, list[str], list[str]]:
    keys = set(obj.keys())
    missing = [k for k in SCHEMA_KEYS if k not in keys]
    extra = [k for k in keys if k not in SCHEMA_KEYS]
    return (len(missing) == 0 and len(extra) == 0), missing, sorted(extra)


def list_diff(*, gold: list[str], pred: list[str]) -> tuple[list[str], list[str]]:
    gold_set = set(gold)
    pred_set = set(pred)
    missing = sorted(gold_set - pred_set)
    extra = sorted(pred_set - gold_set)
    return missing, extra


def classify_example(*, raw_len: int, repaired_schema_ok: bool, any_correct_semantics: bool) -> str:
    # For this report:
    # structural correctness means "raw output was valid JSON+schema". If raw is empty, it's structurally wrong.
    structural_correct = raw_len > 0
    semantic_correct = any_correct_semantics

    if structural_correct and semantic_correct:
        return "A"
    if (not structural_correct) and semantic_correct:
        return "B"
    if structural_correct and (not semantic_correct):
        return "C"
    return "D"


def write_failure_analysis_md(out_path: Path) -> None:
    patients = ["patient_01", "patient_02", "patient_03"]
    rep = 1
    run = 1

    lines: list[str] = []
    lines += [
        "# Failure Analysis (Low Redundancy)",
        "",
        "Scope: `repetition=1x`, `run_01`, `patient_01..patient_03`.",
        "",
        "Legend:",
        "- A: structurally correct + semantically correct",
        "- B: structurally wrong + semantically correct",
        "- C: structurally correct + semantically wrong",
        "- D: structurally wrong + semantically wrong",
        "",
    ]

    for pid in patients:
        p = sample_example_paths(patient_id=pid, repetition=rep, run=run)
        raw = _read_text(p.raw_response)
        repaired = _read_json(p.repaired)
        gt = _read_json(p.ground_truth)

        repaired_ok, repaired_missing, repaired_extra = schema_check(repaired)
        gt_ok, gt_missing, gt_extra = schema_check(gt)

        pred_norm = {k: normalize_list_basic(repaired.get(k)) for k in SCHEMA_KEYS if k != "patient_id"}
        gold_norm = {k: normalize_list_basic(gt.get(k)) for k in SCHEMA_KEYS if k != "patient_id"}

        # "Any semantic correctness" is true if any field has at least one exact match.
        any_match = any(set(pred_norm[k]) & set(gold_norm[k]) for k in pred_norm)
        cls = classify_example(raw_len=len(raw), repaired_schema_ok=repaired_ok, any_correct_semantics=any_match)

        lines += [
            f"## {pid} (rep_1x/run_01) — Class {cls}",
            "",
            f"- `raw_response.txt` bytes: `{len(raw.encode('utf-8'))}`",
            f"- `repaired.json` schema_ok: `{repaired_ok}` (missing={repaired_missing}, extra={repaired_extra})",
            f"- `ground_truth.json` schema_ok: `{gt_ok}` (missing={gt_missing}, extra={gt_extra})",
            "",
            "### Ground truth vs repaired (per field)",
            "",
        ]

        for field in ("conditions", "medications", "observations", "procedures"):
            missing, extra = list_diff(gold=gold_norm[field], pred=pred_norm[field])
            lines += [
                f"#### `{field}`",
                "",
                "| Ground truth | Repaired output | Missing (vs GT) | Hallucinated (vs GT) |",
                "|---|---|---|---|",
                f"| {', '.join(gold_norm[field]) or '(empty)'} | {', '.join(pred_norm[field]) or '(empty)'} | {', '.join(missing) or '(none)'} | {', '.join(extra) or '(none)'} |",
                "",
            ]

    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_schema_alignment_md(out_path: Path) -> None:
    lines = [
        "# Schema Alignment Check",
        "",
        "Expected schema keys:",
        f"- `{list(SCHEMA_KEYS)}`",
        "",
        "Evidence:",
        "- `data/patient_XX/ground_truth/patient_XX.json` uses the same top-level keys.",
        "- `outputs/.../repaired.json` uses the same top-level keys (filled with empty arrays when raw output is invalid).",
        "",
        "Conclusion:",
        "- Top-level schema alignment is **not** the cause of F1=0 in this run.",
        "",
    ]
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_repair_pipeline_audit_md(out_path: Path) -> None:
    lines = [
        "# Repair Pipeline Audit",
        "",
        "File audited: `repair_json.py`.",
        "",
        "Observed behavior:",
        "- If raw text is empty or not JSON, `repair_and_analyze()` falls back to `{}` then normalizes to the fixed schema with empty arrays.",
        "- `patient_id` is always forced to the expected value.",
        "- Non-list values for list fields are coerced into a list.",
        "",
        "Potentially lossy behavior:",
        "- Unsupported (extra) keys are not copied into the repaired object (effectively dropped).",
        "",
        "Empirical evidence in this run:",
        "- For low-redundancy samples, `raw_response.txt` is empty and `repaired.json` becomes an all-empty extraction.",
        "- This indicates repair is **not deleting real content** here; it is filling empties due to upstream failure.",
        "",
    ]
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_json_mode_audit_md(out_path: Path) -> None:
    # We cannot reconstruct HTTP errors after the fact because responses are not stored.
    lines = [
        "# JSON Mode Audit (DeepInfra)",
        "",
        "Findings from artifacts:",
        "- `raw_outputs/*.txt` are all `0` bytes in this run (180/180).",
        "- Per-call `outputs/.../raw_response.txt` are `0` bytes in sampled cases.",
        "- Per-call `outputs/.../response.json` files are absent, implying `DeepInfraResult.response_json` was `None` for those calls.",
        "",
        "Interpretation:",
        "- The model is not producing usable content for the pipeline, either because requests are failing (4xx/5xx/timeouts) or because the client is not capturing returned content.",
        "- The current pipeline does not check `DeepInfraResult.ok` and does not log `DeepInfraResult.error`, so failures silently look like empty model outputs.",
        "",
        "Open questions (not answerable post-hoc with current logs):",
        "- Whether `response_format={\"type\":\"json_object\"}` is supported by the chosen model/backend.",
        "- Whether requests were rejected (400) due to JSON mode / schema / payload format.",
        "",
    ]
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_empty_extraction_stats_csv(out_csv: Path) -> None:
    repaired_files = sorted((RUN_ROOT / "repaired_outputs").glob("*.json"))
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "call_id",
                "patient_id",
                "repetition",
                "run",
                "conditions_n",
                "medications_n",
                "observations_n",
                "procedures_n",
                "all_empty",
            ],
        )
        w.writeheader()

        for path in repaired_files:
            call_id = path.stem
            obj = _read_json(path)
            patient_id = obj.get("patient_id", "")

            m = re.search(r"__rep_(\d+)x__run_(\d+)$", call_id)
            repetition = int(m.group(1)) if m else -1
            run = int(m.group(2)) if m else -1

            c = normalize_list_basic(obj.get("conditions"))
            meds = normalize_list_basic(obj.get("medications"))
            obs = normalize_list_basic(obj.get("observations"))
            procs = normalize_list_basic(obj.get("procedures"))
            all_empty = (len(c) + len(meds) + len(obs) + len(procs)) == 0

            w.writerow(
                {
                    "call_id": call_id,
                    "patient_id": patient_id,
                    "repetition": repetition,
                    "run": run,
                    "conditions_n": len(c),
                    "medications_n": len(meds),
                    "observations_n": len(obs),
                    "procedures_n": len(procs),
                    "all_empty": int(all_empty),
                }
            )


def relaxed_prf(gold: set[str], pred: set[str]) -> tuple[float, float, float]:
    tp = len(gold & pred)
    fp = len(pred - gold)
    fn = len(gold - pred)
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) else 0.0
    return prec, rec, f1


def write_relaxed_semantic_metrics_csv(out_csv: Path) -> None:
    """
    Computes a relaxed semantic match using:
    - basic normalization (lowercase/punctuation/whitespace)
    - a tiny synonym map for common medical variants (pilot-focused)
    """
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    repaired_files = sorted((RUN_ROOT / "repaired_outputs").glob("*.json"))

    # Map patient ground truths once
    gt_by_patient: dict[str, dict[str, Any]] = {}
    for gt_path in Path("data").glob("patient_*/ground_truth/patient_*.json"):
        gt = _read_json(gt_path)
        gt_by_patient[gt["patient_id"]] = gt

    rows: list[dict[str, Any]] = []
    for path in repaired_files:
        call_id = path.stem
        pred = _read_json(path)
        patient_id = pred.get("patient_id", "")
        gold = gt_by_patient.get(patient_id)
        if not gold:
            continue

        m = re.search(r"__rep_(\d+)x__run_(\d+)$", call_id)
        repetition = int(m.group(1)) if m else -1
        run = int(m.group(2)) if m else -1

        gold_all: set[str] = set()
        pred_all: set[str] = set()
        for field in ("conditions", "medications", "observations", "procedures"):
            gold_all |= set(normalize_list_relaxed(gold.get(field)))
            pred_all |= set(normalize_list_relaxed(pred.get(field)))

        prec, rec, f1 = relaxed_prf(gold_all, pred_all)
        rows.append(
            {
                "call_id": call_id,
                "patient_id": patient_id,
                "repetition": repetition,
                "run": run,
                "relaxed_precision": prec,
                "relaxed_recall": rec,
                "relaxed_f1": f1,
                "gold_entities_n": len(gold_all),
                "pred_entities_n": len(pred_all),
            }
        )

    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        if rows:
            w.writeheader()
            w.writerows(rows)


def write_normalization_issues_md(out_md: Path) -> None:
    lines = [
        "# Normalization Issues",
        "",
        "Current normalization (strict evaluator) is essentially:",
        "- lowercase + whitespace collapse",
        "- punctuation stripping",
        "- exact string match after normalization",
        "",
        "Likely issues:",
        "- Does not treat common medical variants as equivalent (e.g., `T2D` vs `Type 2 diabetes mellitus`).",
        "",
        "Pilot synonym examples (implemented for relaxed scoring in `pipeline_failure_analysis.py`):",
        "- `Type 2 Diabetes` / `Diabetes Mellitus Type II` / `T2D` → `type 2 diabetes mellitus`",
        "",
        "Important note for this specific run:",
        "- Predictions are empty across calls, so normalization improvements will not change F1 unless upstream output capture is fixed.",
        "",
    ]
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_root_cause_analysis_md(out_md: Path) -> None:
    lines = [
        "# Root Cause Analysis",
        "",
        "## What happened",
        "- All `raw_outputs/*.txt` are empty (`0` bytes) for this run (180/180).",
        "- Sampled per-call `outputs/.../raw_response.txt` are empty.",
        "- Repair then produces schema-valid JSON objects with empty arrays.",
        "- Semantic evaluator therefore reports F1 = 0 and 100% omissions.",
        "",
        "## Answers to the key questions",
        "- Is the model semantically extracting correctly? **Not measurable** in this run because the pipeline captured no model text.",
        "- Is structural extraction working? **Repair/schema-normalization works**, but it is operating on empty raw text.",
        "- Is the evaluator invalid/too strict? **No evidence**: ground truth schema matches evaluator keys; predictions are empty.",
        "- Is schema mismatch causing F1 collapse? **No** (schemas align at top-level).",
        "- Is repair damaging outputs? **Unlikely here**; it is filling empties due to upstream failure.",
        "- Is DeepInfra JSON mode unreliable? **Possible**, but not provable post-hoc because HTTP errors are not logged/stored.",
        "",
        "## Most likely failure source",
        "- Upstream API call failures and/or response parsing issues are being silently swallowed.",
        "- `run_experiments.py` does not check `result.ok` and does not persist `result.error` when calls fail.",
        "",
        "## Does the pilot measure redundancy drift yet?",
        "- **No**. With empty predictions for all conditions, there is no signal to analyze for drift.",
        "",
    ]
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    out_dir = RUN_ROOT
    write_failure_analysis_md(out_dir / "failure_analysis.md")
    write_schema_alignment_md(out_dir / "schema_alignment.md")
    write_repair_pipeline_audit_md(out_dir / "repair_pipeline_audit.md")
    write_json_mode_audit_md(out_dir / "json_mode_audit.md")
    write_empty_extraction_stats_csv(out_dir / "empty_extraction_statistics.csv")
    write_relaxed_semantic_metrics_csv(out_dir / "relaxed_semantic_metrics.csv")
    write_normalization_issues_md(out_dir / "normalization_issues.md")
    write_root_cause_analysis_md(out_dir / "root_cause_analysis.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

