from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from config import get_settings
from deepinfra_client import DeepInfraClient, DeepInfraResult
from dotenv import load_dotenv
from repair_json import repair_and_analyze
from run_experiments import extract_pdf_text, pdf_page_count


@dataclass(frozen=True)
class DebugPaths:
    out_dir: Path
    raw_api_response_json: Path
    raw_api_response_text: Path
    response_structure_debug: Path
    json_mode_debug: Path
    raw_content: Path
    extracted_pdf_text: Path
    repaired_json: Path
    smoke_validation_md: Path


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def _debug_structure(resp: Any) -> str:
    lines: list[str] = []
    lines.append(f"type(response): {type(resp)}")
    if isinstance(resp, dict):
        lines.append(f"top-level keys: {sorted(resp.keys())}")
        choices = resp.get("choices")
        lines.append(f"type(choices): {type(choices)}")
        if isinstance(choices, list) and choices:
            c0 = choices[0]
            lines.append(f"type(choices[0]): {type(c0)}")
            if isinstance(c0, dict):
                lines.append(f"choices[0] keys: {sorted(c0.keys())}")
                msg = c0.get("message")
                lines.append(f"type(choices[0].message): {type(msg)}")
                if isinstance(msg, dict):
                    lines.append(f"message keys: {sorted(msg.keys())}")
                    content = msg.get("content")
                    lines.append(f"type(message.content): {type(content)}")
                    if isinstance(content, str):
                        lines.append(f"len(message.content): {len(content)}")
                        lines.append(f"message.content preview: {content[:400]!r}")
                fr = c0.get("finish_reason")
                lines.append(f"finish_reason: {fr!r}")
    return "\n".join(lines) + "\n"


def _assert_nonempty_content(content: str | None) -> None:
    if content is None:
        raise RuntimeError("Model content is None (no content captured).")
    if not content.strip():
        raise RuntimeError("Model content is empty/whitespace (no content captured).")


def _json_mode_debug(resp_json: dict[str, Any] | None) -> str:
    lines: list[str] = ["# JSON Mode Debug", ""]
    if resp_json is None:
        lines.append("- Response JSON: `None`")
        return "\n".join(lines) + "\n"

    lines.append("- `response_format` requested: `{type: json_object}` (see `deepinfra_client.py`).")
    choices = resp_json.get("choices") if isinstance(resp_json, dict) else None
    if not (isinstance(choices, list) and choices):
        lines.append("- Missing/empty `choices` in response.")
        return "\n".join(lines) + "\n"

    c0 = choices[0] if isinstance(choices[0], dict) else {}
    msg = c0.get("message") if isinstance(c0, dict) else None
    content = msg.get("content") if isinstance(msg, dict) else None
    lines.append(f"- `finish_reason`: `{c0.get('finish_reason')!r}`")
    usage = resp_json.get("usage")
    lines.append(f"- `usage` present: `{usage is not None}`")
    if isinstance(usage, dict):
        for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
            if k in usage:
                lines.append(f"  - `{k}`: `{usage.get(k)}`")
    lines.append(f"- `message.content` type: `{type(content)}`")
    if isinstance(content, str):
        lines.append(f"- `message.content` length: `{len(content)}`")
        lines.append("")
        lines.append("## Content preview (first 400 chars)")
        lines.append("```")
        lines.append(content[:400])
        lines.append("```")
    return "\n".join(lines) + "\n"


def main() -> int:
    settings = get_settings()
    load_dotenv(settings.project_root / ".env")

    # Smoke test scope (no loops):
    patient_id = "patient_01"
    repetition = 1
    run_idx = 1

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = settings.data_dir / "runs" / f"smoke_{run_id}"
    paths = DebugPaths(
        out_dir=out_dir,
        raw_api_response_json=out_dir / "debug_raw_api_response.json",
        raw_api_response_text=out_dir / "debug_raw_api_response_text.txt",
        response_structure_debug=out_dir / "response_structure_debug.txt",
        json_mode_debug=out_dir / "json_mode_debug.md",
        raw_content=out_dir / "debug_raw_content.txt",
        extracted_pdf_text=out_dir / "debug_extracted_pdf_text.txt",
        repaired_json=out_dir / "repaired.json",
        smoke_validation_md=out_dir / "smoke_test_validation.md",
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    _write_json(out_dir / "smoke_manifest.json", asdict(paths) | {"patient_id": patient_id, "repetition": repetition})

    pdf_path = settings.data_dir / patient_id / "pdfs" / f"{patient_id}_rep_{repetition}x.pdf"
    doc_text = extract_pdf_text(pdf_path)
    pages = pdf_page_count(pdf_path)
    _write_text(
        paths.extracted_pdf_text,
        f"pdf_path: {pdf_path}\npages: {pages}\nchars: {len(doc_text)}\n\n--- BEGIN PREVIEW ---\n"
        + doc_text[:1000]
        + "\n--- END PREVIEW ---\n",
    )

    client = DeepInfraClient(settings)
    result: DeepInfraResult = client.chat_completions(
        user_prompt=settings.extraction_prompt_template,
        document_text=doc_text,
    )

    # Save the full response object (best-effort) before any parsing logic.
    _write_json(
        paths.raw_api_response_json,
        {
            "ok": result.ok,
            "status_code": result.status_code,
            "latency_s": result.latency_s,
            "error": result.error,
            "response_json": result.response_json,
        },
    )
    _write_text(paths.raw_api_response_text, "" if result.response_json is not None else (result.error or ""))

    _write_text(paths.response_structure_debug, _debug_structure(result.response_json))
    _write_text(paths.json_mode_debug, _json_mode_debug(result.response_json))

    raw_content = result.content_text
    _assert_nonempty_content(raw_content)
    _write_text(paths.raw_content, raw_content)

    repair = repair_and_analyze(raw_content, patient_id=patient_id)
    repaired_obj = repair.repaired_obj or {
        "patient_id": patient_id,
        "conditions": [],
        "medications": [],
        "observations": [],
        "procedures": [],
    }
    _write_json(paths.repaired_json, repaired_obj)

    # Minimal end-to-end validation: ensure repaired output has non-empty entity list(s).
    ent_count = sum(len(repaired_obj.get(k) or []) for k in ("conditions", "medications", "observations", "procedures"))
    if ent_count == 0:
        raise RuntimeError("Smoke test produced an all-empty repaired.json (no entities captured).")

    # Compare to ground truth using existing evaluator (manual-readable output).
    gt_path = settings.data_dir / patient_id / "ground_truth" / f"{patient_id}.json"
    gold = json.loads(gt_path.read_text(encoding="utf-8"))

    # Import locally to avoid changing evaluator code.
    from evaluator import normalize_extraction, score_against_gold

    pred_norm = normalize_extraction(repaired_obj, patient_id=patient_id)
    gold_norm = normalize_extraction(gold, patient_id=patient_id)
    scores = score_against_gold(gold_norm, pred_norm)

    _write_text(
        paths.smoke_validation_md,
        "\n".join(
            [
                "# Smoke Test Validation",
                "",
                f"- patient_id: `{patient_id}`",
                f"- repetition: `{repetition}x`",
                f"- run: `{run_idx:02d}`",
                f"- api_ok: `{result.ok}` status_code=`{result.status_code}` latency_s=`{result.latency_s:.3f}`",
                f"- pdf pages: `{pages}` chars: `{len(doc_text)}`",
                f"- raw content length: `{len(raw_content)}`",
                f"- repaired entity count: `{ent_count}`",
                "",
                "## Evaluator (strict) results",
                f"- micro_precision: `{float(scores['micro_precision']):.3f}`",
                f"- micro_recall: `{float(scores['micro_recall']):.3f}`",
                f"- micro_f1: `{float(scores['micro_f1']):.3f}`",
                f"- omissions: `{int(scores['omission_count'])}`",
                f"- hallucinations: `{int(scores['hallucination_count'])}`",
                "",
                "## Where to inspect",
                f"- raw response object: `{paths.raw_api_response_json}`",
                f"- response structure: `{paths.response_structure_debug}`",
                f"- JSON mode debug: `{paths.json_mode_debug}`",
                f"- extracted pdf preview: `{paths.extracted_pdf_text}`",
                f"- raw model content: `{paths.raw_content}`",
                f"- repaired output: `{paths.repaired_json}`",
                "",
            ]
        )
        + "\n",
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
