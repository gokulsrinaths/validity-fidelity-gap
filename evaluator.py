from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Iterable


SCHEMA_KEYS = ("patient_id", "conditions", "medications", "observations", "procedures")


def safe_json_loads(text: str) -> tuple[dict[str, Any] | None, str | None]:
    """
    Best-effort parse: accept a single JSON object; strip codefences if present.
    Returns (obj, error).
    """
    if text is None:
        return None, "empty_response"

    s = text.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*```$", "", s)

    try:
        obj = json.loads(s)
        if not isinstance(obj, dict):
            return None, "not_json_object"
        return obj, None
    except Exception as e:
        return None, f"json_parse_error:{type(e).__name__}"


def _norm_str(x: Any) -> str:
    if x is None:
        return ""
    if not isinstance(x, str):
        x = str(x)
    x = x.strip().lower()
    x = re.sub(r"\s+", " ", x)
    x = re.sub(r"[^\w\s\-/().%]", "", x)  # remove punctuation noise
    return x


_ROMAN_NUMERAL_MAP = {
    " i ": " 1 ",
    " ii ": " 2 ",
    " iii ": " 3 ",
    " iv ": " 4 ",
    " v ": " 5 ",
}


_ABBREV_MAP = {
    # common clinical abbreviations (non-exhaustive; used only for a *secondary* metric)
    "t2d": "type 2 diabetes",
    "dm2": "type 2 diabetes",
    "t1d": "type 1 diabetes",
    "dm1": "type 1 diabetes",
    "htn": "hypertension",
    "hld": "hyperlipidemia",
    "mi": "myocardial infarction",
    "cad": "coronary artery disease",
    "ckd": "chronic kidney disease",
    "copd": "chronic obstructive pulmonary disease",
    "afib": "atrial fibrillation",
    "a fib": "atrial fibrillation",
}


def _soft_synonym_canonicalize(s: str) -> str:
    """
    "Soft" canonicalization intended for a *secondary* robustness metric.
    This is deliberately conservative: small set of common abbreviations + numeral normalization.
    """
    s = _norm_str(s)
    if not s:
        return s

    # normalize roman numerals (e.g., "type ii" -> "type 2")
    padded = f" {s} "
    for k, v in _ROMAN_NUMERAL_MAP.items():
        padded = padded.replace(k, v)
    s = padded.strip()

    # collapse diabetes phrasing variants
    s = re.sub(r"\b(diabetes mellitus)\b", "diabetes", s)
    s = re.sub(r"\btype\s*2\b", "type 2", s)
    s = re.sub(r"\btype\s*ii\b", "type 2", s)
    s = re.sub(r"\btype\s*1\b", "type 1", s)

    # expand a small set of abbreviations
    if s in _ABBREV_MAP:
        s = _ABBREV_MAP[s]
    return s


def normalize_list(items: Any) -> list[str]:
    if items is None:
        return []
    if not isinstance(items, list):
        items = [items]
    out = []
    for it in items:
        s = _norm_str(it)
        if s:
            out.append(s)
    # de-dup stable order
    seen = set()
    deduped = []
    for s in out:
        if s not in seen:
            seen.add(s)
            deduped.append(s)
    return deduped


def normalize_extraction(obj: dict[str, Any], *, patient_id: str) -> dict[str, Any]:
    norm: dict[str, Any] = {
        "patient_id": patient_id,
        "conditions": normalize_list(obj.get("conditions")),
        "medications": normalize_list(obj.get("medications")),
        "observations": normalize_list(obj.get("observations")),
        "procedures": normalize_list(obj.get("procedures")),
    }
    return norm


def normalize_extraction_soft(obj: dict[str, Any], *, patient_id: str) -> dict[str, Any]:
    """
    Secondary normalization used to test whether results are robust to common clinical synonymy.
    """
    def soft_list(x: Any) -> list[str]:
        if x is None:
            return []
        if not isinstance(x, list):
            x = [x]
        out: list[str] = []
        for it in x:
            s = _soft_synonym_canonicalize(it)
            if s:
                out.append(s)
        # stable de-dup
        seen: set[str] = set()
        deduped: list[str] = []
        for s in out:
            if s not in seen:
                seen.add(s)
                deduped.append(s)
        return deduped

    return {
        "patient_id": patient_id,
        "conditions": soft_list(obj.get("conditions")),
        "medications": soft_list(obj.get("medications")),
        "observations": soft_list(obj.get("observations")),
        "procedures": soft_list(obj.get("procedures")),
    }


_DOSE_RE = re.compile(r"\b\d+(\.\d+)?\b")
_UNIT_RE = re.compile(
    r"\b(mg|mcg|g|kg|ml|l|min|hr|h|odt|tab|tabs|tablet|tablets|capsule|capsules|puff|puffs|unit|units)\b"
)
_FREQ_RE = re.compile(r"\b(q\d+h|qd|bid|tid|qid|qhs|prn|daily|weekly|monthly)\b")


def canonicalize_condition(s: str) -> str:
    s = _soft_synonym_canonicalize(s)
    if not s:
        return s
    # collapse common qualifiers that often vary in surface form
    s = re.sub(r"\b(without|with)\b.*$", lambda m: m.group(0) if False else s, s)  # no-op placeholder
    s = s.replace("exacerbation", "").strip()
    s = re.sub(r"\s+", " ", s).strip()
    return s


def canonicalize_medication(s: str) -> str:
    """
    Ingredient-style canonicalization for robustness checks:
    - lower/strip punctuation
    - remove numeric doses, units, and frequency tokens
    - keep leading ingredient phrase until first removed segment
    This is intentionally simple and is used only for a secondary metric.
    """
    s = _soft_synonym_canonicalize(s)
    if not s:
        return s
    # remove parentheticals after normalization
    s = re.sub(r"\([^)]*\)", " ", s)
    # remove dose/freq tokens
    s = _DOSE_RE.sub(" ", s)
    s = _UNIT_RE.sub(" ", s)
    s = _FREQ_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # keep up to first 3 tokens to avoid trailing instructions
    toks = s.split()
    if len(toks) > 3:
        s = " ".join(toks[:3])
    return s


def normalize_extraction_canonical(obj: dict[str, Any], *, patient_id: str) -> dict[str, Any]:
    def canon_list(x: Any, *, fn) -> list[str]:
        if x is None:
            return []
        if not isinstance(x, list):
            x = [x]
        out: list[str] = []
        for it in x:
            ss = fn(it)
            if ss:
                out.append(ss)
        seen: set[str] = set()
        deduped: list[str] = []
        for ss in out:
            if ss not in seen:
                seen.add(ss)
                deduped.append(ss)
        return deduped

    return {
        "patient_id": patient_id,
        "conditions": canon_list(obj.get("conditions"), fn=canonicalize_condition),
        "medications": canon_list(obj.get("medications"), fn=canonicalize_medication),
        "observations": normalize_list(obj.get("observations")),
        "procedures": normalize_list(obj.get("procedures")),
    }


def as_set(xs: Iterable[str]) -> set[str]:
    return set(xs or [])


@dataclass(frozen=True)
class PRF:
    precision: float
    recall: float
    f1: float
    tp: int
    fp: int
    fn: int


def prf1(pred: set[str], gold: set[str]) -> PRF:
    tp = len(pred & gold)
    fp = len(pred - gold)
    fn = len(gold - pred)
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return PRF(precision=precision, recall=recall, f1=f1, tp=tp, fp=fp, fn=fn)


def score_against_gold(pred_obj: dict[str, Any], gold_obj: dict[str, Any]) -> dict[str, Any]:
    """
    Computes per-field and micro-averaged PRF over entity strings.
    Also returns omission/hallucination counts (fn/fp micro totals).
    """
    totals_tp = totals_fp = totals_fn = 0
    per_field: dict[str, Any] = {}
    for key in ("conditions", "medications", "observations", "procedures"):
        p = as_set(pred_obj.get(key, []))
        g = as_set(gold_obj.get(key, []))
        s = prf1(p, g)
        per_field[key] = s.__dict__
        totals_tp += s.tp
        totals_fp += s.fp
        totals_fn += s.fn

    micro = prf1(set().union(*(as_set(pred_obj.get(k, [])) for k in ("conditions","medications","observations","procedures"))),
                 set().union(*(as_set(gold_obj.get(k, [])) for k in ("conditions","medications","observations","procedures"))))

    return {
        "micro_precision": micro.precision,
        "micro_recall": micro.recall,
        "micro_f1": micro.f1,
        "omission_count": totals_fn,
        "hallucination_count": totals_fp,
        "per_field": per_field,
    }


def divergence_score(a_obj: dict[str, Any], b_obj: dict[str, Any]) -> dict[str, Any]:
    """
    Set-based divergence between two extractions (micro Jaccard distance + structural validity).
    """
    a = set().union(*(as_set(a_obj.get(k, [])) for k in ("conditions","medications","observations","procedures")))
    b = set().union(*(as_set(b_obj.get(k, [])) for k in ("conditions","medications","observations","procedures")))
    inter = len(a & b)
    union = len(a | b)
    jaccard = inter / union if union else 1.0
    return {"jaccard_similarity": jaccard, "jaccard_distance": 1.0 - jaccard, "a_size": len(a), "b_size": len(b)}


def structural_drift_score(
    *,
    malformed_json: bool,
    missing_keys_count: int,
    extra_keys_count: int,
    schema_match: bool,
    markdown_fence_present: bool,
) -> float:
    """
    Structural Drift Score (SDS): higher means more structural instability.
    We keep this intentionally simple + interpretable.
    """
    score = 0.0
    if malformed_json:
        score += 2.0
    if markdown_fence_present:
        score += 0.25
    score += 0.5 * missing_keys_count
    score += 0.25 * extra_keys_count
    if not schema_match:
        score += 0.5
    return float(score)
