from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any


REQUIRED_KEYS = ("patient_id", "conditions", "medications", "observations", "procedures")


@dataclass(frozen=True)
class RepairResult:
    raw_text: str
    markdown_fence_present: bool
    extracted_json_text: str | None
    raw_valid_json: bool
    malformed_json: bool
    schema_match: bool
    repair_needed: bool
    extra_keys: list[str]
    missing_keys: list[str]
    operations: list[str]
    repaired_obj: dict[str, Any] | None

    @property
    def extra_keys_count(self) -> int:
        return len(self.extra_keys)

    @property
    def missing_keys_count(self) -> int:
        return len(self.missing_keys)


def strip_markdown_fences(text: str) -> tuple[str, bool]:
    if text is None:
        return "", False
    s = text.strip()
    fence = bool(re.search(r"```", s))
    # Remove leading/trailing fence blocks if present
    s = re.sub(r"^\s*```(?:json)?\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*```\s*$", "", s)
    return s.strip(), fence


def extract_first_json_object(text: str) -> str | None:
    """
    Extract the first {...} JSON object substring using a simple brace balancer.
    Returns None if not found.
    """
    if not text:
        return None
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        else:
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
    return None


def normalize_to_schema(obj: dict[str, Any], *, patient_id: str) -> tuple[dict[str, Any], list[str]]:
    ops: list[str] = []
    out: dict[str, Any] = {}

    # patient_id forced
    out["patient_id"] = patient_id
    if obj.get("patient_id") != patient_id:
        ops.append("set_patient_id")

    for key in ("conditions", "medications", "observations", "procedures"):
        val = obj.get(key, [])
        if val is None:
            val = []
        if not isinstance(val, list):
            val = [val]
            ops.append(f"coerce_{key}_to_list")
        out[key] = val
        if key not in obj:
            ops.append(f"fill_missing_{key}")

    # Remove unsupported keys
    unsupported = [k for k in obj.keys() if k not in REQUIRED_KEYS]
    if unsupported:
        ops.append("remove_unsupported_keys")

    return out, ops


def repair_and_analyze(raw_text: str, *, patient_id: str) -> RepairResult:
    raw_text = raw_text or ""
    operations: list[str] = []

    stripped, fence_present = strip_markdown_fences(raw_text)
    if fence_present:
        operations.append("strip_markdown_fences")

    extracted = extract_first_json_object(stripped)
    if extracted and extracted != stripped:
        operations.append("extract_first_json_object")

    candidate = extracted if extracted is not None else stripped
    parsed: dict[str, Any] | None = None
    raw_valid_json = False
    malformed_json = False

    try:
        parsed_any = json.loads(candidate)
        if isinstance(parsed_any, dict):
            parsed = parsed_any
            raw_valid_json = True
        else:
            malformed_json = True
            operations.append("parsed_non_object")
    except Exception:
        malformed_json = True

    if parsed is None:
        # Fall back to empty object for normalization
        parsed = {}

    missing_keys = [k for k in REQUIRED_KEYS if k not in parsed]
    extra_keys = [k for k in parsed.keys() if k not in REQUIRED_KEYS]
    schema_match = (len(missing_keys) == 0) and (len(extra_keys) == 0)

    repaired_obj, norm_ops = normalize_to_schema(parsed, patient_id=patient_id)
    operations.extend(norm_ops)

    repair_needed = (not raw_valid_json) or fence_present or (extracted is not None and extracted != stripped) or (
        not schema_match
    ) or any(op.startswith("coerce_") for op in norm_ops)

    # If we did not successfully parse JSON at all, record explicit operation
    if not raw_valid_json:
        operations.append("repair_from_malformed_json")

    # If schema mismatch, record explicit
    if not schema_match:
        operations.append("repair_schema_mismatch")

    return RepairResult(
        raw_text=raw_text,
        markdown_fence_present=fence_present,
        extracted_json_text=extracted,
        raw_valid_json=raw_valid_json,
        malformed_json=malformed_json,
        schema_match=schema_match,
        repair_needed=repair_needed,
        extra_keys=sorted(extra_keys),
        missing_keys=sorted(missing_keys),
        operations=operations,
        repaired_obj=repaired_obj,
    )

