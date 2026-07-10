from __future__ import annotations

import argparse
import json
import logging
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from analysis import write_json
from config import get_settings
from deepinfra_client import DeepInfraAuthError, DeepInfraClient
from evaluator import divergence_score, normalize_extraction, score_against_gold, structural_drift_score
from repair_json import repair_and_analyze
from run_experiments import extract_pdf_text, generate_synthetic_patients, setup_logging, write_patient_files


ENTITY_FIELDS = ("conditions", "medications", "observations", "procedures")


def _entity_count(obj: dict[str, Any]) -> int:
    return sum(len(obj.get(k) or []) for k in ENTITY_FIELDS)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def _call_id(run_id: str, pid: str, rep: int, run: int) -> str:
    return f"{run_id}__{pid}__rep_{rep}x__run_{run:02d}"


def resume(*, run_root: Path) -> int:
    settings = get_settings()
    load_dotenv(settings.project_root / ".env")

    run_root = Path(run_root)
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "outputs").mkdir(parents=True, exist_ok=True)
    (run_root / "raw_outputs").mkdir(parents=True, exist_ok=True)
    (run_root / "repaired_outputs").mkdir(parents=True, exist_ok=True)
    (run_root / "metrics").mkdir(parents=True, exist_ok=True)
    setup_logging(run_root / "resume.log")

    # Use a stable run_id for call_id naming; if original is unknown, derive from folder name.
    run_id = os.getenv("ATTNDRIFT_RUN_ID") or run_root.name.replace("pilot_", "resume_")

    write_json(
        run_root / "resume_manifest.json",
        {
            "timestamp": datetime.now().isoformat(),
            "run_root": str(run_root),
            "run_id": run_id,
            "model": settings.model,
            "temperature": settings.temperature,
            "top_p": settings.top_p,
            "max_tokens": getattr(settings, "max_tokens", None),
            "num_patients": settings.num_patients,
            "repetition_levels": list(settings.repetition_levels),
            "runs_per_condition": settings.runs_per_condition,
            "note": "Resumes only missing repaired.json calls; preserves existing outputs.",
        },
    )

    # Ensure patient PDFs + ground truth exist.
    patients = generate_synthetic_patients(settings)
    write_patient_files(settings, patients)

    try:
        client = DeepInfraClient(settings)
    except DeepInfraAuthError as e:
        logging.error(str(e))
        raise

    # Resume only missing calls.
    for i in range(1, settings.num_patients + 1):
        pid = f"patient_{i:02d}"
        for rep in settings.repetition_levels:
            for run in range(1, settings.runs_per_condition + 1):
                out_dir = run_root / "outputs" / pid / f"rep_{rep}x" / f"run_{run:02d}"
                repaired_path = out_dir / "repaired.json"
                if repaired_path.exists():
                    continue

                call_id = _call_id(run_id, pid, int(rep), int(run))
                pdf_path = settings.data_dir / pid / "pdfs" / f"{pid}_rep_{rep}x.pdf"
                gt_path = settings.data_dir / pid / "ground_truth" / f"{pid}.json"

                doc_text = extract_pdf_text(pdf_path)
                if not doc_text.strip():
                    _write_text(out_dir / "response_error.txt", "empty_extracted_pdf_text")
                    raise RuntimeError(f"Empty extracted PDF text for {call_id}")

                prompt = settings.extraction_prompt_template.format(document_text=doc_text)
                _write_text(out_dir / "prompt.txt", prompt)

                result = client.chat_completions(user_prompt=settings.extraction_prompt_template, document_text=doc_text)
                _write_json(out_dir / "response_meta.json", asdict(result))
                if result.response_json is not None:
                    _write_json(out_dir / "response.json", result.response_json)
                if result.usage is not None:
                    _write_json(out_dir / "usage.json", result.usage)

                raw = (result.content_text or "").strip()
                _write_text(out_dir / "raw_response.txt", raw + ("\n" if raw else ""))
                if not raw:
                    _write_text(out_dir / "response_error.txt", "empty_raw_content")
                    raise RuntimeError(f"Empty raw content for {call_id}")

                repair = repair_and_analyze(raw, patient_id=pid)
                _write_json(out_dir / "repair_event.json", asdict(repair))
                if repair.repaired_obj is None:
                    _write_text(out_dir / "response_error.txt", "repair_failed")
                    raise RuntimeError(f"Repair failed for {call_id}")

                _write_json(repaired_path, repair.repaired_obj)
                if _entity_count(repair.repaired_obj) == 0:
                    _write_text(out_dir / "response_error.txt", "repaired_entities_empty")
                    raise RuntimeError(f"Empty extraction for {call_id}")

                gold = json.loads(gt_path.read_text(encoding="utf-8"))
                pred_norm = normalize_extraction(repair.repaired_obj, patient_id=pid)
                gold_norm = normalize_extraction(gold, patient_id=pid)
                sem = score_against_gold(pred_norm, gold_norm)
                sem_row = {
                    "patient_id": pid,
                    "repetition": int(rep),
                    "run": int(run),
                    "micro_precision": float(sem["micro_precision"]),
                    "micro_recall": float(sem["micro_recall"]),
                    "micro_f1": float(sem["micro_f1"]),
                    "omission_count": int(sem["omission_count"]),
                    "hallucination_count": int(sem["hallucination_count"]),
                    "extracted_entities_n": _entity_count(repair.repaired_obj),
                }
                _write_json(out_dir / "semantic_metrics.json", sem_row)

                structural_row = {
                    "patient_id": pid,
                    "repetition": int(rep),
                    "run": int(run),
                    "raw_valid_json": int(repair.raw_valid_json),
                    "repair_needed": int(repair.repair_needed),
                    "schema_match": int(repair.schema_match),
                    "structural_drift_score": float(
                        structural_drift_score(
                            malformed_json=bool(repair.malformed_json),
                            missing_keys_count=int(len(repair.missing_keys or [])),
                            extra_keys_count=int(len(repair.extra_keys or [])),
                            schema_match=bool(repair.schema_match),
                            markdown_fence_present=bool(repair.markdown_fence_present),
                        )
                    ),
                    "semantic_pairwise_jaccard_distance": float(divergence_score(pred_norm, gold_norm)["jaccard_distance"]),
                }
                _write_json(out_dir / "structural_metrics.json", structural_row)

                logging.info("Completed %s", call_id)

    logging.info("Resume finished.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run_root", type=str, required=True)
    args = ap.parse_args()
    return resume(run_root=Path(args.run_root))


if __name__ == "__main__":
    raise SystemExit(main())
