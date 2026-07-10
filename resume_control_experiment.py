from __future__ import annotations

import argparse
import json
import logging
import random
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

from analysis import estimate_tokens, write_json
from config import get_settings
from deepinfra_client import DeepInfraAuthError, DeepInfraClient
from evaluator import divergence_score, normalize_extraction, score_against_gold, structural_drift_score
from repair_json import repair_and_analyze
from run_experiments import FILLER_PARAGRAPHS, extract_pdf_text, generate_synthetic_patients, write_patient_files


ENTITY_FIELDS = ("conditions", "medications", "observations", "procedures")


def _entity_count(obj: dict[str, Any]) -> int:
    return sum(len(obj.get(k) or []) for k in ENTITY_FIELDS)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def build_constant_length_control(*, base_text: str, target_est_tokens: int, settings, rng: random.Random) -> str:
    text = base_text.rstrip() + "\n"
    while estimate_tokens(len(text), settings.est_chars_per_token) < target_est_tokens:
        text += "\n" + rng.choice(FILLER_PARAGRAPHS) + "\n"
    return text.strip() + "\n"


def resume(*, control_root: Path) -> int:
    settings = get_settings()
    load_dotenv(settings.project_root / ".env")
    control_root = Path(control_root)

    if not control_root.exists():
        raise SystemExit(f"control_root not found: {control_root}")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    # Ensure directories exist.
    for sub in ("outputs", "metrics", "plots", "control_docs", "filler_sources", "token_stats"):
        (control_root / sub).mkdir(parents=True, exist_ok=True)

    (control_root / "filler_sources" / "filler_paragraphs.txt").write_text(
        "\n\n".join(FILLER_PARAGRAPHS) + "\n", encoding="utf-8"
    )

    # Load/create manifest (do not overwrite if present).
    manifest_path = control_root / "resume_manifest.json"
    write_json(
        manifest_path,
        {
            "timestamp": datetime.now().isoformat(),
            "control_root": str(control_root),
            "model": settings.model,
            "temperature": settings.temperature,
            "top_p": settings.top_p,
            "max_tokens": getattr(settings, "max_tokens", None),
            "num_patients": settings.num_patients,
            "repetition_levels": list(settings.repetition_levels),
            "runs_per_condition": settings.runs_per_condition,
            "note": "Resumes constant-length filler control by skipping existing repaired.json outputs.",
        },
    )

    patients = generate_synthetic_patients(settings)
    write_patient_files(settings, patients)
    client = DeepInfraClient(settings)
    rng = random.Random(settings.random_seed)

    # Load existing per-call metrics if present; we only append new rows.
    sem_rows: list[dict[str, Any]] = []
    str_rows: list[dict[str, Any]] = []
    ctx_rows: list[dict[str, Any]] = []
    tok_rows: list[dict[str, Any]] = []

    # Resume loop.
    for i in range(1, settings.num_patients + 1):
        pid = f"patient_{i:02d}"
        base_txt_path = settings.data_dir / pid / "raw" / f"{pid}_base.txt"
        gt_path = settings.data_dir / pid / "ground_truth" / f"{pid}.json"
        base_text = base_txt_path.read_text(encoding="utf-8")
        gold = json.loads(gt_path.read_text(encoding="utf-8"))

        for rep in settings.repetition_levels:
            # Redundancy doc length proxy (base repeated).
            target_text = (base_text.strip() + "\n") * int(rep)
            target_est_tokens = estimate_tokens(len(target_text), settings.est_chars_per_token)

            control_doc = build_constant_length_control(
                base_text=base_text, target_est_tokens=target_est_tokens, settings=settings, rng=rng
            )
            (control_root / "control_docs" / pid).mkdir(parents=True, exist_ok=True)
            (control_root / "control_docs" / pid / f"{pid}_control_rep_{rep}x.txt").write_text(
                control_doc, encoding="utf-8"
            )

            for run in range(1, settings.runs_per_condition + 1):
                out_dir = control_root / "outputs" / pid / f"rep_{rep}x" / f"run_{run:02d}"
                repaired_path = out_dir / "repaired.json"
                if repaired_path.exists():
                    continue

                out_dir.mkdir(parents=True, exist_ok=True)
                prompt = settings.extraction_prompt_template.format(document_text=control_doc)
                _write_text(out_dir / "prompt.txt", prompt)
                _write_text(out_dir / "document.txt", control_doc)

                result = client.chat_completions(user_prompt=settings.extraction_prompt_template, document_text=control_doc)
                _write_json(out_dir / "response_meta.json", asdict(result))
                if result.response_json is not None:
                    _write_json(out_dir / "response.json", result.response_json)
                if result.usage is not None:
                    _write_json(out_dir / "usage.json", result.usage)

                raw = (result.content_text or "").strip()
                _write_text(out_dir / "raw_response.txt", raw + ("\n" if raw else ""))
                if not raw:
                    _write_text(out_dir / "response_error.txt", "empty_raw_content")
                    raise RuntimeError(f"Empty raw content for {pid} rep={rep} run={run}")

                repair = repair_and_analyze(raw, patient_id=pid)
                _write_json(out_dir / "repair_event.json", asdict(repair))
                if repair.repaired_obj is None:
                    _write_text(out_dir / "response_error.txt", "repair_failed")
                    raise RuntimeError(f"Repair failed for {pid} rep={rep} run={run}")

                _write_json(repaired_path, repair.repaired_obj)
                if _entity_count(repair.repaired_obj) == 0:
                    _write_text(out_dir / "response_error.txt", "repaired_entities_empty")
                    raise RuntimeError(f"Empty extraction for {pid} rep={rep} run={run}")

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
                sem_rows.append(sem_row)

                str_row = {
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
                }
                _write_json(out_dir / "structural_metrics.json", str_row)
                str_rows.append(str_row)

                ctx_row = {
                    "patient_id": pid,
                    "repetition": int(rep),
                    "run": int(run),
                    "document_chars": int(len(control_doc)),
                    "document_est_tokens": int(estimate_tokens(len(control_doc), settings.est_chars_per_token)),
                }
                _write_json(out_dir / "context_meta.json", ctx_row)
                ctx_rows.append(ctx_row)

                tok_row = {
                    "patient_id": pid,
                    "repetition": int(rep),
                    "run": int(run),
                    "target_est_tokens": int(target_est_tokens),
                    "control_est_tokens": int(estimate_tokens(len(control_doc), settings.est_chars_per_token)),
                }
                tok_rows.append(tok_row)

                logging.info("Completed control %s rep=%sx run=%02d", pid, rep, run)

    # Append partial CSVs for new rows.
    if sem_rows:
        pd.DataFrame(sem_rows).to_csv(control_root / "metrics" / "semantic_metrics_partial_resume.csv", index=False)
    if str_rows:
        pd.DataFrame(str_rows).to_csv(control_root / "metrics" / "structural_metrics_partial_resume.csv", index=False)
    if tok_rows:
        pd.DataFrame(tok_rows).to_csv(control_root / "token_stats" / "token_length_matching_resume.csv", index=False)

    logging.info("Resume control finished.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--control_root", type=str, required=True)
    args = ap.parse_args()

    try:
        return resume(control_root=Path(args.control_root))
    except DeepInfraAuthError as e:
        logging.error(str(e))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

