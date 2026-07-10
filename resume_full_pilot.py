from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

from analysis import estimate_tokens
from config import get_settings
from deepinfra_client import DeepInfraClient
from evaluator import divergence_score, normalize_extraction, score_against_gold, structural_drift_score
from repair_json import repair_and_analyze
from run_experiments import extract_pdf_text, pdf_page_count


ENTITY_FIELDS = ("conditions", "medications", "observations", "procedures")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _entity_count(obj: dict[str, Any]) -> int:
    return sum(len(obj.get(k) or []) for k in ENTITY_FIELDS)


def _append_csv(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([row])
    exists = path.exists()
    df.to_csv(path, mode="a", header=not exists, index=False)


def _heartbeat(path: Path, *, state: dict[str, Any]) -> None:
    state = dict(state)
    state["timestamp"] = datetime.now().isoformat()
    _write_json(path, state)


def _find_run_id(run_root: Path) -> str:
    manifest = run_root / "full_pilot_manifest.json"
    if manifest.exists():
        j = json.loads(manifest.read_text(encoding="utf-8"))
        if isinstance(j, dict) and j.get("run_id"):
            return str(j["run_id"])
    # fallback: parse folder name full_pilot_<runid>
    name = run_root.name
    if name.startswith("full_pilot_"):
        return name[len("full_pilot_") :]
    raise RuntimeError(f"Could not determine run_id for {run_root}")


def main() -> int:
    settings = get_settings()
    load_dotenv(settings.project_root / ".env")

    run_root = settings.data_dir / "runs" / "full_pilot_20260520_192127"
    run_id = _find_run_id(run_root)

    # Resume scope: only missing patients
    patient_ids = ["patient_09", "patient_10"]

    # Fixed scientific variables: repetition levels + runs/condition
    repetition_levels = list(settings.repetition_levels)
    runs_per_condition = int(settings.runs_per_condition)

    metrics_dir = run_root / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    sem_partial = metrics_dir / "semantic_metrics_partial.csv"
    str_partial = metrics_dir / "structural_metrics_partial.csv"

    heartbeat_path = run_root / "heartbeat.json"
    termination_state = run_root / "termination_state.json"

    # Determine completed call folders (checkpoint detection)
    def is_done(pid: str, rep: int, run_idx: int) -> bool:
        out_dir = run_root / "outputs" / pid / f"rep_{rep}x" / f"run_{run_idx:02d}"
        return (out_dir / "repaired.json").exists()

    client = DeepInfraClient(settings)

    try:
        for pid in patient_ids:
            gt_path = settings.data_dir / pid / "ground_truth" / f"{pid}.json"
            gold = json.loads(gt_path.read_text(encoding="utf-8"))
            one_x_norm: dict[str, Any] | None = None

            for rep in repetition_levels:
                for run_idx in range(1, runs_per_condition + 1):
                    if is_done(pid, rep, run_idx):
                        continue

                    _heartbeat(
                        heartbeat_path,
                        state={
                            "run_id": run_id,
                            "run_root": str(run_root),
                            "patient_id": pid,
                            "repetition": rep,
                            "run": run_idx,
                            "note": "resuming missing calls only",
                        },
                    )

                    call_id = f"{run_id}__{pid}__rep_{rep}x__run_{run_idx:02d}"
                    out_dir = run_root / "outputs" / pid / f"rep_{rep}x" / f"run_{run_idx:02d}"
                    out_dir.mkdir(parents=True, exist_ok=True)

                    pdf_path = settings.data_dir / pid / "pdfs" / f"{pid}_rep_{rep}x.pdf"
                    doc_text = extract_pdf_text(pdf_path)
                    pages = pdf_page_count(pdf_path)
                    char_count = len(doc_text)
                    est_toks = estimate_tokens(char_count, settings.est_chars_per_token)

                    prompt = settings.extraction_prompt_template.format(document_text=doc_text)
                    (out_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
                    (out_dir / "document_source.txt").write_text(doc_text, encoding="utf-8")

                    result = client.chat_completions(user_prompt=settings.extraction_prompt_template, document_text=doc_text)
                    _write_json(
                        out_dir / "response_meta.json",
                        {"ok": result.ok, "status_code": result.status_code, "latency_s": result.latency_s, "error": result.error},
                    )
                    if not result.ok:
                        _write_text(out_dir / "response_error.txt", result.error or "unknown_error")
                        raise RuntimeError(f"DeepInfra call failed for {call_id}: {result.status_code} {result.error}")

                    (out_dir / "latency_s.txt").write_text(f"{result.latency_s:.6f}\n", encoding="utf-8")
                    if result.usage is not None:
                        _write_json(out_dir / "usage.json", result.usage)
                    if result.response_json is not None:
                        _write_json(out_dir / "response.json", result.response_json)

                    raw_text = result.content_text
                    if raw_text is None or not raw_text.strip():
                        _write_text(out_dir / "response_error.txt", "empty_or_missing_message_content")
                        raise RuntimeError(f"Empty model content for {call_id}")
                    (out_dir / "raw_response.txt").write_text(raw_text, encoding="utf-8")
                    (run_root / "raw_outputs" / f"{call_id}.txt").write_text(raw_text, encoding="utf-8")

                    repair = repair_and_analyze(raw_text, patient_id=pid)
                    _write_json(out_dir / "repair_event.json", asdict(repair))

                    if not repair.raw_valid_json:
                        _write_text(out_dir / "response_error.txt", "raw_json_parse_failed")
                        raise RuntimeError(f"Raw JSON parsing failed for {call_id}")
                    if not repair.schema_match:
                        _write_text(out_dir / "response_error.txt", "raw_schema_mismatch")
                        raise RuntimeError(f"Raw JSON schema mismatch for {call_id}")

                    repaired_obj = repair.repaired_obj
                    if repaired_obj is None:
                        _write_text(out_dir / "response_error.txt", "repair_returned_none")
                        raise RuntimeError(f"Repair produced None for {call_id}")

                    ent_n = _entity_count(repaired_obj)
                    if ent_n == 0:
                        _write_text(out_dir / "response_error.txt", "repaired_entities_empty")
                        raise RuntimeError(f"Repaired extraction empty for {call_id}")

                    (out_dir / "repaired.json").write_text(json.dumps(repaired_obj, indent=2), encoding="utf-8")
                    (run_root / "repaired_outputs" / f"{call_id}.json").write_text(
                        json.dumps(repaired_obj, indent=2), encoding="utf-8"
                    )

                    norm_pred = normalize_extraction(repaired_obj, patient_id=pid)
                    norm_gold = normalize_extraction(gold, patient_id=pid)
                    gold_scores = score_against_gold(norm_pred, norm_gold)

                    if rep == 1 and run_idx == 1:
                        one_x_norm = norm_pred

                    drift_vs_1x = divergence_score(norm_pred, one_x_norm) if one_x_norm is not None else {"jaccard_distance": 0.0}
                    drift_vs_gold = divergence_score(norm_pred, norm_gold)
                    drift_score = 0.5 * float(drift_vs_1x["jaccard_distance"]) + 0.5 * float(drift_vs_gold["jaccard_distance"])

                    sds = structural_drift_score(
                        malformed_json=repair.malformed_json,
                        missing_keys_count=repair.missing_keys_count,
                        extra_keys_count=repair.extra_keys_count,
                        schema_match=repair.schema_match,
                        markdown_fence_present=repair.markdown_fence_present,
                    )

                    ts = datetime.now().isoformat()
                    sem_row = {
                        "run_id": run_id,
                        "patient_id": pid,
                        "repetition": rep,
                        "run": run_idx,
                        "model": settings.model,
                        "timestamp": ts,
                        "ok": 1,
                        "status_code": result.status_code if result.status_code is not None else "",
                        "latency_s": result.latency_s,
                        "micro_precision": gold_scores["micro_precision"],
                        "micro_recall": gold_scores["micro_recall"],
                        "micro_f1": gold_scores["micro_f1"],
                        "omission_count": gold_scores["omission_count"],
                        "hallucination_count": gold_scores["hallucination_count"],
                        "drift_vs_1x": drift_vs_1x["jaccard_distance"],
                        "drift_vs_gold": drift_vs_gold["jaccard_distance"],
                        "drift_score": drift_score,
                        "extracted_entities_n": ent_n,
                    }
                    str_row = {
                        "run_id": run_id,
                        "patient_id": pid,
                        "repetition": rep,
                        "run": run_idx,
                        "model": settings.model,
                        "timestamp": ts,
                        "ok": 1,
                        "status_code": result.status_code if result.status_code is not None else "",
                        "latency_s": result.latency_s,
                        "raw_valid_json": int(repair.raw_valid_json),
                        "schema_match": int(repair.schema_match),
                        "repair_needed": int(repair.repair_needed),
                        "extra_keys_count": repair.extra_keys_count,
                        "missing_keys_count": repair.missing_keys_count,
                        "malformed_json": int(repair.malformed_json),
                        "markdown_fence_present": int(repair.markdown_fence_present),
                        "structural_drift_score": sds,
                        "extracted_entities_n": ent_n,
                        "pdf_pages": pages,
                        "character_count": char_count,
                        "estimated_tokens": est_toks,
                    }

                    _write_json(out_dir / "semantic_metrics.json", sem_row)
                    _write_json(out_dir / "structural_metrics.json", str_row)

                    _append_csv(sem_partial, sem_row)
                    _append_csv(str_partial, str_row)

        _heartbeat(heartbeat_path, state={"run_id": run_id, "status": "completed"})
        return 0
    except Exception as e:
        _write_json(
            termination_state,
            {
                "run_id": run_id,
                "run_root": str(run_root),
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
                "last_heartbeat": json.loads(heartbeat_path.read_text(encoding="utf-8")) if heartbeat_path.exists() else None,
            },
        )
        raise


if __name__ == "__main__":
    raise SystemExit(main())

