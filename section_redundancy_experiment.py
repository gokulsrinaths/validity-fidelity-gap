from __future__ import annotations

import argparse
import json
import logging
import random
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

from analysis import estimate_tokens, summarize_by_repetition, write_json
from config import get_settings
from deepinfra_client import DeepInfraClient
from evaluator import divergence_score, normalize_extraction, score_against_gold, structural_drift_score
from plotting import generate_structural_plots, generate_variance_plots
from repair_json import repair_and_analyze
from run_experiments import (
    FILLER_PARAGRAPHS,
    compute_variance_metrics,
    detect_early_collapse,
    extract_pdf_text,
    generate_synthetic_patients,
    pdf_page_count,
    render_pdf,
    write_patient_files,
)


ENTITY_FIELDS = ("conditions", "medications", "observations", "procedures")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def _entity_count(obj: dict[str, Any]) -> int:
    return sum(len(obj.get(k) or []) for k in ENTITY_FIELDS)


_HEADER_RE = re.compile(r"^(?P<h>[A-Z][A-Z0-9 /&()-]{2,})\s*$", re.MULTILINE)


def _extract_sections(note: str) -> dict[str, str]:
    """
    Best-effort sectionizer for our synthetic notes.
    Returns a mapping header->body (body excludes the header line).
    """
    text = note.strip() + "\n"
    matches = list(_HEADER_RE.finditer(text))
    if not matches:
        return {"__FULL__": text}

    sections: dict[str, str] = {}
    for i, m in enumerate(matches):
        h = m.group("h").strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip("\n")
        sections[h] = (h + "\n" + body.strip() + "\n").strip() + "\n"
    return sections


def build_section_redundancy_doc(
    *,
    base_text: str,
    rep: int,
    section_names: tuple[str, ...] = ("MEDICATIONS", "MEDICATIONS ON DISCHARGE", "DIAGNOSES"),
) -> str:
    """
    Copy-forward style redundancy: keep the note once, then repeat only selected sections rep times.
    This is still synthetic but closer to EHR boilerplate/copy-forward than full-note repetition.
    """
    if rep <= 1:
        return base_text.strip() + "\n"

    sections = _extract_sections(base_text)
    # choose sections that exist
    picked = []
    for name in section_names:
        if name in sections:
            picked.append(sections[name])
    if not picked:
        # fallback: repeat the whole note (but caller can avoid this)
        return (base_text.strip() + "\n") * rep

    extra = ("\n".join(picked)).strip() + "\n"
    # append rep-1 times
    return (base_text.strip() + "\n\n" + ("\n".join([extra] * (rep - 1))).strip() + "\n").strip() + "\n"


def build_length_matched_filler(
    *,
    base_text: str,
    target_est_tokens: int,
    settings,
    rng: random.Random,
) -> str:
    text = base_text.rstrip() + "\n"
    while estimate_tokens(len(text), settings.est_chars_per_token) < target_est_tokens:
        text += "\n" + rng.choice(FILLER_PARAGRAPHS) + "\n"
    return text.strip() + "\n"


def run_experiment(*, run_root: Path, reps: list[int], runs_per_condition: int, num_patients: int) -> int:
    """
    Runs two conditions:
    A) section-redundancy (copy-forward style)
    B) length-matched filler (same token length as A, but unrelated)
    """
    settings = get_settings()
    load_dotenv(settings.project_root / ".env")

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_root.mkdir(parents=True, exist_ok=True)
    for sub in ("outputs", "raw_outputs", "repaired_outputs", "metrics", "plots", "docs", "token_stats"):
        (run_root / sub).mkdir(parents=True, exist_ok=True)

    write_json(
        run_root / "manifest.json",
        {
            "run_id": run_id,
            "condition_a": "section_redundancy",
            "condition_b": "length_matched_filler",
            "model": settings.model,
            "temperature": settings.temperature,
            "max_tokens": getattr(settings, "max_tokens", None),
            "num_patients": num_patients,
            "repetition_levels": reps,
            "runs_per_condition": runs_per_condition,
            "note": "No prompt/schema/evaluator changes; varies only document composition.",
        },
    )

    patients = generate_synthetic_patients(settings)[: int(num_patients)]
    write_patient_files(settings, patients)
    client = DeepInfraClient(settings)
    rng = random.Random(settings.random_seed)

    sem_rows: list[dict[str, Any]] = []
    st_rows: list[dict[str, Any]] = []
    token_rows: list[dict[str, Any]] = []

    for p in patients:
        pid = p["patient_id"]
        base_text = p["text"].strip() + "\n"
        gt_path = settings.data_dir / pid / "ground_truth" / f"{pid}.json"
        gold = json.loads(gt_path.read_text(encoding="utf-8"))

        one_x_norm: dict[str, Any] | None = None

        for rep in reps:
            rep_i = int(rep)

            doc_a = build_section_redundancy_doc(base_text=base_text, rep=rep_i)
            target_tokens = estimate_tokens(len(doc_a), settings.est_chars_per_token)
            doc_b = build_length_matched_filler(base_text=base_text, target_est_tokens=target_tokens, settings=settings, rng=rng)

            token_rows.append(
                {
                    "patient_id": pid,
                    "repetition": rep_i,
                    "target_est_tokens": target_tokens,
                    "section_doc_chars": len(doc_a),
                    "filler_doc_chars": len(doc_b),
                }
            )

            # save docs
            ddir = run_root / "docs" / pid / f"rep_{rep_i}x"
            ddir.mkdir(parents=True, exist_ok=True)
            (ddir / "section_redundancy.txt").write_text(doc_a, encoding="utf-8")
            (ddir / "filler_control.txt").write_text(doc_b, encoding="utf-8")

            # render/extract to match pipeline
            a_pdf = ddir / "section_redundancy.pdf"
            b_pdf = ddir / "filler_control.pdf"
            render_pdf(doc_a, a_pdf)
            render_pdf(doc_b, b_pdf)
            a_text = extract_pdf_text(a_pdf)
            b_text = extract_pdf_text(b_pdf)

            for cond, doc_text in [("section_redundancy", a_text), ("filler_control", b_text)]:
                for run_idx in range(1, runs_per_condition + 1):
                    call_id = f"{pid}__{cond}__rep_{rep_i}x__run_{run_idx:02d}"
                    out_dir = run_root / "outputs" / pid / cond / f"rep_{rep_i}x" / f"run_{run_idx:02d}"
                    out_dir.mkdir(parents=True, exist_ok=True)
                    if (out_dir / "repaired.json").exists():
                        continue

                    prompt = settings.extraction_prompt_template.format(document_text=doc_text)
                    (out_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
                    (out_dir / "document_source.txt").write_text(doc_text, encoding="utf-8")

                    result = client.chat_completions(user_prompt=settings.extraction_prompt_template, document_text=doc_text)
                    _write_json(out_dir / "response_meta.json", {"ok": result.ok, "status_code": result.status_code, "latency_s": result.latency_s, "error": result.error})
                    if not result.ok:
                        _write_text(out_dir / "response_error.txt", result.error or "unknown_error")
                        raise RuntimeError(f"DeepInfra call failed for {call_id}: {result.status_code} {result.error}")

                    if result.usage is not None:
                        _write_json(out_dir / "usage.json", result.usage)
                    if result.response_json is not None:
                        _write_json(out_dir / "response.json", result.response_json)

                    raw = result.content_text
                    if raw is None or not raw.strip():
                        _write_text(out_dir / "response_error.txt", "empty_or_missing_message_content")
                        raise RuntimeError(f"Empty model content for {call_id}")
                    (out_dir / "raw_response.txt").write_text(raw, encoding="utf-8")
                    (run_root / "raw_outputs" / f"{call_id}.txt").write_text(raw, encoding="utf-8")

                    repair = repair_and_analyze(raw, patient_id=pid)
                    _write_json(out_dir / "repair_event.json", asdict(repair))
                    if repair.repaired_obj is None:
                        raise RuntimeError(f"Repair returned None for {call_id}")

                    ent_n = _entity_count(repair.repaired_obj)
                    if ent_n == 0:
                        _write_text(out_dir / "response_error.txt", "repaired_entities_empty")
                        raise RuntimeError(f"Empty repaired extraction for {call_id}")

                    (out_dir / "repaired.json").write_text(json.dumps(repair.repaired_obj, indent=2), encoding="utf-8")
                    (run_root / "repaired_outputs" / f"{call_id}.json").write_text(json.dumps(repair.repaired_obj, indent=2), encoding="utf-8")

                    pred = normalize_extraction(repair.repaired_obj, patient_id=pid)
                    goldn = normalize_extraction(gold, patient_id=pid)
                    scores = score_against_gold(pred, goldn)

                    if rep_i == 1 and run_idx == 1 and cond == "section_redundancy":
                        one_x_norm = pred

                    drift_vs_1x = divergence_score(pred, one_x_norm) if one_x_norm is not None else {"jaccard_distance": 0.0}
                    drift_vs_gold = divergence_score(pred, goldn)
                    drift_score = 0.5 * float(drift_vs_1x["jaccard_distance"]) + 0.5 * float(drift_vs_gold["jaccard_distance"])

                    sds = structural_drift_score(
                        malformed_json=repair.malformed_json,
                        missing_keys_count=repair.missing_keys_count,
                        extra_keys_count=repair.extra_keys_count,
                        schema_match=repair.schema_match,
                        markdown_fence_present=repair.markdown_fence_present,
                    )

                    sem_rows.append(
                        {
                            "run_id": run_id,
                            "patient_id": pid,
                            "condition": cond,
                            "repetition": rep_i,
                            "run": run_idx,
                            "micro_precision": scores["micro_precision"],
                            "micro_recall": scores["micro_recall"],
                            "micro_f1": scores["micro_f1"],
                            "omission_count": scores["omission_count"],
                            "hallucination_count": scores["hallucination_count"],
                            "drift_score": drift_score,
                        }
                    )
                    st_rows.append(
                        {
                            "run_id": run_id,
                            "patient_id": pid,
                            "condition": cond,
                            "repetition": rep_i,
                            "run": run_idx,
                            "raw_valid_json": int(repair.raw_valid_json),
                            "repair_needed": int(repair.repair_needed),
                            "structural_drift_score": float(sds),
                        }
                    )

    sem = pd.DataFrame(sem_rows)
    st = pd.DataFrame(st_rows)
    toks = pd.DataFrame(token_rows)
    metrics_dir = run_root / "metrics"
    sem.to_csv(metrics_dir / "semantic_metrics.csv", index=False)
    st.to_csv(metrics_dir / "structural_metrics.csv", index=False)
    toks.to_csv(metrics_dir / "token_stats.csv", index=False)

    # compute by-rep summaries per condition
    out = []
    for cond in sorted(sem["condition"].unique().tolist()):
        by_rep = summarize_by_repetition(sem[sem["condition"] == cond], st[st["condition"] == cond])
        by_rep["condition"] = cond
        out.append(by_rep)
    by = pd.concat(out, ignore_index=True).sort_values(["condition", "repetition"])
    by.to_csv(metrics_dir / "scaling_by_condition.csv", index=False)

    # simple plots (reuse plotting module by saving temp csvs per condition)
    plots_dir = run_root / "plots"
    for cond in sorted(sem["condition"].unique().tolist()):
        sem_c = sem[sem["condition"] == cond].copy()
        st_c = st[st["condition"] == cond].copy()
        sem_path = metrics_dir / f"semantic_{cond}.csv"
        st_path = metrics_dir / f"structural_{cond}.csv"
        sem_c.to_csv(sem_path, index=False)
        st_c.to_csv(st_path, index=False)
        generate_structural_plots(st_path, plots_dir / cond)
        # variance plots only if multiple runs
        if runs_per_condition > 1:
            var = compute_variance_metrics(sem_c, st_c)
            var_path = metrics_dir / f"variance_{cond}.csv"
            var.to_csv(var_path, index=False)
            if not var.empty:
                generate_variance_plots(var_path, plots_dir / cond)

    # collapse flags (descriptive)
    flags = []
    for cond in sorted(sem["condition"].unique().tolist()):
        sem_c = sem[sem["condition"] == cond]
        st_c = st[st["condition"] == cond]
        by_rep_sem = (
            sem_c.groupby("repetition", as_index=False)
            .agg(
                micro_f1_mean=("micro_f1", "mean"),
                hallucination_mean=("hallucination_count", "mean"),
                omission_mean=("omission_count", "mean"),
            )
            .sort_values("repetition")
        )
        by_rep_str = (
            st_c.groupby("repetition", as_index=False)
            .agg(raw_json_valid_rate=("raw_valid_json", "mean"))
            .sort_values("repetition")
        )
        for f in detect_early_collapse(by_rep_sem, by_rep_str):
            flags.append(f"{cond}: {f}")
    (run_root / "collapse_flags.txt").write_text("\n".join(flags) + ("\n" if flags else ""), encoding="utf-8")

    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true", help="Run the section-level redundancy experiment (API calls).")
    ap.add_argument("--out_root", type=str, default="data/runs")
    ap.add_argument("--reps", type=str, default="1,5,10,16")
    ap.add_argument("--runs_per_condition", type=int, default=1)
    ap.add_argument("--num_patients", type=int, default=50)
    args = ap.parse_args()

    if not args.run:
        ap.print_help()
        return 0

    reps = [int(x.strip()) for x in args.reps.split(",") if x.strip()]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_root = Path(args.out_root) / f"section_redundancy_{ts}"
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return run_experiment(run_root=run_root, reps=reps, runs_per_condition=int(args.runs_per_condition), num_patients=int(args.num_patients))


if __name__ == "__main__":
    raise SystemExit(main())

