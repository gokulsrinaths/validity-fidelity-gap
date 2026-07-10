from __future__ import annotations

import argparse
import json
import logging
import random
import time
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from dotenv import load_dotenv

from analysis import estimate_tokens
from config import Settings, get_settings
from deepinfra_client import DeepInfraClient
from evaluator import divergence_score, normalize_extraction, score_against_gold, structural_drift_score
from repair_json import repair_and_analyze
from run_experiments import (
    FILLER_PARAGRAPHS,
    extract_pdf_text,
    generate_synthetic_patients,
    pdf_page_count,
    render_pdf,
    write_patient_files,
)


ENTITY_FIELDS = ("conditions", "medications", "observations", "procedures")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _append_csv(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([row])
    exists = path.exists()
    df.to_csv(path, mode="a", header=not exists, index=False)


def _entity_count(obj: dict[str, Any]) -> int:
    return sum(len(obj.get(k) or []) for k in ENTITY_FIELDS)


def build_constant_length_control(
    *,
    base_text: str,
    target_est_tokens: int,
    settings: Settings,
    rng: random.Random,
) -> str:
    text = base_text.rstrip() + "\n"
    while estimate_tokens(len(text), settings.est_chars_per_token) < target_est_tokens:
        text += "\n" + rng.choice(FILLER_PARAGRAPHS) + "\n"
    return text.strip() + "\n"


def load_models_config(path: Path) -> dict[str, Any]:
    cfg = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(cfg, dict) or "models" not in cfg:
        raise RuntimeError("models_config.yaml must contain top-level `models:` mapping")
    return cfg["models"]


def heartbeat(run_root: Path, state: dict[str, Any]) -> None:
    state = dict(state)
    state["timestamp"] = datetime.now().isoformat()
    _write_json(run_root / "heartbeat.json", state)


def write_termination_state(run_root: Path, *, err: Exception) -> None:
    hb = None
    hb_path = run_root / "heartbeat.json"
    if hb_path.exists():
        try:
            hb = json.loads(hb_path.read_text(encoding="utf-8"))
        except Exception:
            hb = None
    _write_json(
        run_root / "termination_state.json",
        {
            "timestamp": datetime.now().isoformat(),
            "error": str(err),
            "last_heartbeat": hb,
        },
    )


def call_out_dir(*, run_root: Path, model_key: str, condition: str, patient_id: str, rep: int, run_idx: int) -> Path:
    return run_root / model_key / condition / "outputs" / patient_id / f"rep_{rep}x" / f"run_{run_idx:02d}"


def is_completed(*, run_root: Path, model_key: str, condition: str, patient_id: str, rep: int, run_idx: int) -> bool:
    return (call_out_dir(run_root=run_root, model_key=model_key, condition=condition, patient_id=patient_id, rep=rep, run_idx=run_idx) / "repaired.json").exists()


def run_validation(
    *,
    run_root: Path,
    model_key: str,
    model_cfg: dict[str, Any],
    conditions: list[str],
    patient_ids: list[str],
    repetition_levels: list[int],
    runs_per_condition: int,
) -> int:
    base_settings = get_settings()
    load_dotenv(base_settings.project_root / ".env")

    # Scientific constraints: keep decoding fixed
    if base_settings.temperature != 0.0 or base_settings.top_p != 1.0:
        raise RuntimeError("Refusing to run: settings temperature/top_p differ from fixed values.")

    # Override model + max_tokens only via Settings copy
    settings = replace(
        base_settings,
        model=str(model_cfg["model"]),
        max_tokens=int(model_cfg.get("max_tokens", base_settings.max_tokens or 512)),
    )

    # Ensure patient files exist
    patients_all = generate_synthetic_patients(settings)
    write_patient_files(settings, patients_all)
    patients = [p for p in patients_all if p["patient_id"] in set(patient_ids)]

    client = DeepInfraClient(settings)
    rng = random.Random(settings.random_seed)

    # Partial checkpoint CSVs (append per call)
    metrics_dir = run_root / model_key / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    sem_partial = metrics_dir / "semantic_metrics_partial.csv"
    str_partial = metrics_dir / "structural_metrics_partial.csv"
    cost_partial = metrics_dir / "cost_partial.csv"

    for condition in conditions:
        for p in patients:
            pid = p["patient_id"]
            base_text = p["text"].strip() + "\n"
            gt_path = settings.data_dir / pid / "ground_truth" / f"{pid}.json"
            gold = json.loads(gt_path.read_text(encoding="utf-8"))
            one_x_norm: dict[str, Any] | None = None

            for rep in repetition_levels:
                for run_idx in range(1, runs_per_condition + 1):
                    if is_completed(run_root=run_root, model_key=model_key, condition=condition, patient_id=pid, rep=rep, run_idx=run_idx):
                        continue

                    heartbeat(
                        run_root,
                        {
                            "phase": "running",
                            "model_key": model_key,
                            "model": settings.model,
                            "condition": condition,
                            "patient_id": pid,
                            "repetition": rep,
                            "run": run_idx,
                        },
                    )

                    out_dir = call_out_dir(
                        run_root=run_root, model_key=model_key, condition=condition, patient_id=pid, rep=rep, run_idx=run_idx
                    )
                    out_dir.mkdir(parents=True, exist_ok=True)
                    (out_dir.parent.parent.parent.parent.parent / "raw_outputs").mkdir(parents=True, exist_ok=True)
                    (out_dir.parent.parent.parent.parent.parent / "repaired_outputs").mkdir(parents=True, exist_ok=True)

                    call_id = f"{run_root.name}__{model_key}__{condition}__{pid}__rep_{rep}x__run_{run_idx:02d}"

                    # Build document for this condition
                    if condition == "redundancy":
                        doc_text_raw = (base_text * int(rep)).strip() + "\n"
                    elif condition == "filler_control":
                        target_tokens = estimate_tokens(len((base_text * int(rep)).strip() + "\n"), settings.est_chars_per_token)
                        doc_text_raw = build_constant_length_control(
                            base_text=base_text, target_est_tokens=target_tokens, settings=settings, rng=rng
                        )
                    else:
                        raise RuntimeError(f"Unknown condition: {condition}")

                    # Render to PDF to keep pipeline identical (pdf->extract text)
                    pdf_path = out_dir / "document.pdf"
                    render_pdf(doc_text_raw, pdf_path)
                    # Occasionally, PDF parsing can transiently fail (e.g., file system latency).
                    # Retry a couple times to avoid aborting expensive runs.
                    last_pdf_err: Exception | None = None
                    for attempt in range(1, 4):
                        try:
                            doc_text = extract_pdf_text(pdf_path)
                            pages = pdf_page_count(pdf_path)
                            last_pdf_err = None
                            break
                        except Exception as e:
                            last_pdf_err = e
                            time.sleep(0.5 * attempt)
                            # Re-render once in case file was corrupted on disk.
                            try:
                                render_pdf(doc_text_raw, pdf_path)
                            except Exception:
                                pass
                    if last_pdf_err is not None:
                        _write_text(out_dir / "response_error.txt", f"pdf_parse_failed:{type(last_pdf_err).__name__}")
                        raise
                    char_count = len(doc_text)
                    est_toks = estimate_tokens(char_count, settings.est_chars_per_token)

                    prompt = settings.extraction_prompt_template.format(document_text=doc_text)
                    (out_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
                    (out_dir / "document_source.txt").write_text(doc_text, encoding="utf-8")

                    result = client.chat_completions(user_prompt=settings.extraction_prompt_template, document_text=doc_text)
                    _write_json(out_dir / "response_meta.json", {"ok": result.ok, "status_code": result.status_code, "latency_s": result.latency_s, "error": result.error})
                    if result.response_json is not None:
                        _write_json(out_dir / "response.json", result.response_json)
                    if result.usage is not None:
                        _write_json(out_dir / "usage.json", result.usage)
                    if not result.ok:
                        _write_text(out_dir / "response_error.txt", result.error or "unknown_error")
                        raise RuntimeError(f"API failure for {call_id}: {result.status_code} {result.error}")

                    raw_text = result.content_text
                    if raw_text is None or not raw_text.strip():
                        _write_text(out_dir / "response_error.txt", "empty_or_missing_message_content")
                        raise RuntimeError(f"Empty model content for {call_id}")
                    (out_dir / "raw_response.txt").write_text(raw_text, encoding="utf-8")

                    # Store wide raw/repaired too
                    raw_out_path = out_dir.parent.parent.parent.parent.parent / "raw_outputs" / f"{call_id}.txt"
                    raw_out_path.write_text(raw_text, encoding="utf-8")

                    repair = repair_and_analyze(raw_text, patient_id=pid)
                    _write_json(out_dir / "repair_event.json", asdict(repair))

                    # Fail-fast protections (same as validated pipeline)
                    if not repair.raw_valid_json:
                        _write_text(out_dir / "response_error.txt", "raw_json_parse_failed")
                        raise RuntimeError(f"Raw JSON parse failed for {call_id}")
                    if not repair.schema_match:
                        _write_text(out_dir / "response_error.txt", "raw_schema_mismatch")
                        raise RuntimeError(f"Raw JSON schema mismatch for {call_id}")

                    repaired_obj = repair.repaired_obj
                    if repaired_obj is None:
                        _write_text(out_dir / "response_error.txt", "repair_returned_none")
                        raise RuntimeError(f"Repair returned None for {call_id}")
                    ent_n = _entity_count(repaired_obj)
                    if ent_n == 0:
                        _write_text(out_dir / "response_error.txt", "repaired_entities_empty")
                        raise RuntimeError(f"Empty extraction for {call_id}")

                    (out_dir / "repaired.json").write_text(json.dumps(repaired_obj, indent=2), encoding="utf-8")
                    repaired_out_path = out_dir.parent.parent.parent.parent.parent / "repaired_outputs" / f"{call_id}.json"
                    repaired_out_path.write_text(json.dumps(repaired_obj, indent=2), encoding="utf-8")

                    norm_pred = normalize_extraction(repaired_obj, patient_id=pid)
                    norm_gold = normalize_extraction(gold, patient_id=pid)
                    scores = score_against_gold(norm_pred, norm_gold)

                    if rep == 1 and run_idx == 1 and condition == "redundancy":
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
                        "model_key": model_key,
                        "model": settings.model,
                        "condition": condition,
                        "patient_id": pid,
                        "repetition": rep,
                        "run": run_idx,
                        "timestamp": ts,
                        "latency_s": result.latency_s,
                        "micro_precision": scores["micro_precision"],
                        "micro_recall": scores["micro_recall"],
                        "micro_f1": scores["micro_f1"],
                        "omission_count": scores["omission_count"],
                        "hallucination_count": scores["hallucination_count"],
                        "drift_vs_1x": drift_vs_1x["jaccard_distance"],
                        "drift_vs_gold": drift_vs_gold["jaccard_distance"],
                        "drift_score": drift_score,
                        "extracted_entities_n": ent_n,
                        "pdf_pages": pages,
                        "character_count": char_count,
                        "estimated_tokens": est_toks,
                    }
                    str_row = {
                        "model_key": model_key,
                        "model": settings.model,
                        "condition": condition,
                        "patient_id": pid,
                        "repetition": rep,
                        "run": run_idx,
                        "timestamp": ts,
                        "raw_valid_json": int(repair.raw_valid_json),
                        "schema_match": int(repair.schema_match),
                        "repair_needed": int(repair.repair_needed),
                        "structural_drift_score": sds,
                        "extra_keys_count": repair.extra_keys_count,
                        "missing_keys_count": repair.missing_keys_count,
                        "malformed_json": int(repair.malformed_json),
                        "markdown_fence_present": int(repair.markdown_fence_present),
                    }

                    _write_json(out_dir / "semantic_metrics.json", sem_row)
                    _write_json(out_dir / "structural_metrics.json", str_row)

                    _append_csv(sem_partial, sem_row)
                    _append_csv(str_partial, str_row)

                    # cost tracking (use DeepInfra usage if present)
                    usage = result.usage or {}
                    cost_row = {
                        "model_key": model_key,
                        "model": settings.model,
                        "condition": condition,
                        "patient_id": pid,
                        "repetition": rep,
                        "run": run_idx,
                        "prompt_tokens": usage.get("prompt_tokens", ""),
                        "completion_tokens": usage.get("completion_tokens", ""),
                        "total_tokens": usage.get("total_tokens", ""),
                        "estimated_cost": usage.get("estimated_cost", ""),
                    }
                    _append_csv(cost_partial, cost_row)

    heartbeat(run_root, {"phase": "completed", "model_key": model_key, "model": settings.model})
    return 0


def postprocess(*, run_root: Path) -> int:
    """
    Aggregates per-model partial CSVs into a single cross_model_results.csv and DRE stats.
    No API calls.
    """
    # Concatenate partials
    sem_parts = list(run_root.glob("*/metrics/semantic_metrics_partial.csv"))
    str_parts = list(run_root.glob("*/metrics/structural_metrics_partial.csv"))
    cost_parts = list(run_root.glob("*/metrics/cost_partial.csv"))
    sem = pd.concat([pd.read_csv(p) for p in sem_parts], ignore_index=True) if sem_parts else pd.DataFrame()
    st = pd.concat([pd.read_csv(p) for p in str_parts], ignore_index=True) if str_parts else pd.DataFrame()
    cost = pd.concat([pd.read_csv(p) for p in cost_parts], ignore_index=True) if cost_parts else pd.DataFrame()

    if not sem.empty:
        sem.to_csv(run_root / "cross_model_semantic_metrics.csv", index=False)
    if not st.empty:
        st.to_csv(run_root / "cross_model_structural_metrics.csv", index=False)
    if not cost.empty:
        cost.to_csv(run_root / "cost_analysis.csv", index=False)

    # Mean metrics by model/condition/repetition
    if sem.empty:
        return 0

    sem_mean = (
        sem.groupby(["model_key", "condition", "repetition"], as_index=False)
        .agg(
            f1_mean=("micro_f1", "mean"),
            omission_mean=("omission_count", "mean"),
            halluc_mean=("hallucination_count", "mean"),
            entities_mean=("extracted_entities_n", "mean"),
        )
        .sort_values(["model_key", "condition", "repetition"])
    )
    sem_mean.to_csv(run_root / "cross_model_results.csv", index=False)

    # DRE per model and repetition: DRE = (F1_drop_redundancy - F1_drop_control)
    # Baseline is the smallest repetition present in BOTH conditions for that model.
    dre_rows: list[dict[str, Any]] = []
    for model_key, g in sem_mean.groupby("model_key"):
        r = g[g["condition"] == "redundancy"].set_index("repetition")
        c = g[g["condition"] == "filler_control"].set_index("repetition")
        common_reps = sorted(set(r.index.tolist()) & set(c.index.tolist()))
        if not common_reps:
            continue
        baseline_rep = common_reps[0]
        base_r = float(r.loc[baseline_rep, "f1_mean"])
        base_c = float(c.loc[baseline_rep, "f1_mean"])
        for rep in common_reps:
            drop_r = base_r - float(r.loc[rep, "f1_mean"])
            drop_c = base_c - float(c.loc[rep, "f1_mean"])
            dre_rows.append(
                {"model_key": model_key, "repetition": int(rep), "F1_drop_redundancy": drop_r, "F1_drop_control": drop_c, "DRE": drop_r - drop_c}
            )
    dre_df = pd.DataFrame(dre_rows)
    if not dre_df.empty:
        dre_df = dre_df.sort_values(["model_key", "repetition"])
        dre_df.to_csv(run_root / "cross_model_DRE_statistics.csv", index=False)
    else:
        # Still write an empty file for visibility/debugging.
        (run_root / "cross_model_DRE_statistics.csv").write_text(
            "model_key,repetition,F1_drop_redundancy,F1_drop_control,DRE\n", encoding="utf-8"
        )

    # Minimal generalization narrative scaffold
    (run_root / "cross_model_generalization.md").write_text(
        "\n".join(
            [
                "# Cross-Model Generalization (Conservative)",
                "",
                "This report summarizes whether redundancy-amplified degradation (DRE>0 at mid repetitions) persists across models.",
                "",
                "Primary artifacts:",
                "- `cross_model_results.csv`",
                "- `cross_model_DRE_statistics.csv`",
                "- `cost_analysis.csv`",
                "",
                "Interpretation guidance:",
                "- Treat as pilot-scale across models (1 run/condition).",
                "- Look for consistent sign of DRE at 2x–16x within each model.",
                "",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run_root", type=str, default="", help="Existing run_root to resume into (optional).")
    ap.add_argument("--model", type=str, default="llama70b", help="Model key from models_config.yaml.")
    ap.add_argument("--models_config", type=str, default="models_config.yaml")
    ap.add_argument("--runs_per_condition", type=int, default=1, help="Runs per repetition per condition.")
    ap.add_argument("--patients", type=int, default=10, help="Number of patients to include (1..10).")
    ap.add_argument("--repetitions", type=str, default="1,2,5,10,16,32", help="Comma-separated repetition levels.")
    ap.add_argument("--postprocess", action="store_true", help="Postprocess only (no API calls).")
    args = ap.parse_args()

    run_root = Path(args.run_root) if args.run_root else (get_settings().data_dir / "runs" / f"cross_model_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    run_root.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    if args.postprocess:
        return postprocess(run_root=run_root)

    models = load_models_config(Path(args.models_config))
    if args.model not in models:
        raise SystemExit(f"Unknown model key {args.model}. Available: {', '.join(sorted(models.keys()))}")

    reps = [int(x.strip()) for x in str(args.repetitions).split(",") if x.strip()]
    if not reps:
        raise SystemExit("--repetitions must be a non-empty comma-separated list")
    if args.patients < 1 or args.patients > 10:
        raise SystemExit("--patients must be between 1 and 10")
    patient_ids = [f"patient_{i:02d}" for i in range(1, args.patients + 1)]

    try:
        return run_validation(
            run_root=run_root,
            model_key=args.model,
            model_cfg=models[args.model],
            conditions=["redundancy", "filler_control"],
            patient_ids=patient_ids,
            repetition_levels=reps,
            runs_per_condition=int(args.runs_per_condition),
        )
    except Exception as e:
        write_termination_state(run_root, err=e)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
