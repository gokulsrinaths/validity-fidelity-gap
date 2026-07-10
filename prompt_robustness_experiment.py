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
from deepinfra_client import DeepInfraClient
from evaluator import normalize_extraction, score_against_gold, structural_drift_score
from plotting import generate_structural_plots
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


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def _entity_count(obj: dict[str, Any]) -> int:
    return sum(len(obj.get(k) or []) for k in ENTITY_FIELDS)


def _build_filler_control(*, base_text: str, target_tokens: int, settings, rng: random.Random) -> str:
    text = base_text.rstrip() + "\n"
    while estimate_tokens(len(text), settings.est_chars_per_token) < target_tokens:
        text += "\n" + rng.choice(FILLER_PARAGRAPHS) + "\n"
    return text.strip() + "\n"


def _prompt_variant_b(schema: dict[str, Any]) -> str:
    """
    Alternative wording, same schema and constraints.
    """
    # Keep schema identical; change instruction phrasing + ordering.
    # IMPORTANT: This template is formatted with `.format(document_text=...)`, so any literal
    # braces must be escaped as double braces.
    return (
        "You must extract clinical entities into the JSON object below.\n"
        "Output MUST be a single JSON object that exactly matches the schema.\n"
        "No markdown, no code fences, no extra text.\n\n"
        "Schema (do not change keys; arrays must exist):\n"
        "{{\n"
        '  \"patient_id\": \"\",\n'
        '  \"conditions\": [],\n'
        '  \"medications\": [],\n'
        '  \"observations\": [],\n'
        '  \"procedures\": []\n'
        "}}\n\n"
        "Guidelines:\n"
        "- Extract only what is explicitly stated.\n"
        "- Use short canonical strings.\n"
        "- If none for a field, use [].\n\n"
        "Document:\n"
        "{document_text}\n"
    )


def _prompt_variant_c(schema: dict[str, Any]) -> str:
    """
    Second alternative wording, same schema and constraints.
    """
    return (
        "TASK: Convert the document into a JSON object that matches the schema exactly.\n"
        "RESTRICTIONS: JSON only. No markdown. No extra keys. Do not rename fields.\n\n"
        "Required JSON schema:\n"
        "{{\n"
        '  \"patient_id\": \"\",\n'
        '  \"conditions\": [],\n'
        '  \"medications\": [],\n'
        '  \"observations\": [],\n'
        '  \"procedures\": []\n'
        "}}\n\n"
        "Return empty arrays when information is not present.\n"
        "Use concise strings.\n\n"
        "DOCUMENT START\n"
        "{document_text}\n"
        "DOCUMENT END\n"
    )


def run(*, run_root: Path, num_patients: int, reps: list[int]) -> int:
    settings = get_settings()
    load_dotenv(settings.project_root / ".env")

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_root.mkdir(parents=True, exist_ok=True)
    for sub in ("outputs", "metrics", "plots"):
        (run_root / sub).mkdir(parents=True, exist_ok=True)

    prompt_a = settings.extraction_prompt_template
    prompt_b = _prompt_variant_b(settings.fixed_schema)
    prompt_c = _prompt_variant_c(settings.fixed_schema)
    prompts = {"promptA": prompt_a, "promptB": prompt_b, "promptC": prompt_c}

    write_json(
        run_root / "manifest.json",
        {
            "run_id": run_id,
            "experiment": "prompt_robustness_midrange",
            "model": settings.model,
            "temperature": settings.temperature,
            "max_tokens": getattr(settings, "max_tokens", None),
            "num_patients": num_patients,
            "repetition_levels": reps,
            "runs_per_condition": 1,
            "conditions": ["redundancy", "filler_control"],
            "prompts": {"promptA": "baseline", "promptB": "alternative_wording_same_schema_v1", "promptC": "alternative_wording_same_schema_v2"},
        },
    )

    patients = generate_synthetic_patients(settings)[: int(num_patients)]
    write_patient_files(settings, patients)
    client = DeepInfraClient(settings)
    rng = random.Random(settings.random_seed)

    sem_rows: list[dict[str, Any]] = []
    st_rows: list[dict[str, Any]] = []

    for p in patients:
        pid = p["patient_id"]
        base_text = p["text"].strip() + "\n"
        gt_path = settings.data_dir / pid / "ground_truth" / f"{pid}.json"
        gold = json.loads(gt_path.read_text(encoding="utf-8"))

        for rep in reps:
            rep_i = int(rep)

            redundancy_text = (base_text * rep_i).strip() + "\n"
            target_tokens = estimate_tokens(len(redundancy_text), settings.est_chars_per_token)
            filler_text = _build_filler_control(base_text=base_text, target_tokens=target_tokens, settings=settings, rng=rng)

            # Render/extract both texts (pipeline parity)
            doc_dir = run_root / "outputs" / pid / f"rep_{rep_i}x"
            doc_dir.mkdir(parents=True, exist_ok=True)
            red_pdf = doc_dir / "redundancy.pdf"
            ctl_pdf = doc_dir / "filler_control.pdf"
            render_pdf(redundancy_text, red_pdf)
            render_pdf(filler_text, ctl_pdf)
            red_extracted = extract_pdf_text(red_pdf)
            ctl_extracted = extract_pdf_text(ctl_pdf)

            for prompt_name, prompt_tmpl in prompts.items():
                for cond, doc_text in [("redundancy", red_extracted), ("filler_control", ctl_extracted)]:
                    call_id = f"{pid}__{prompt_name}__{cond}__rep_{rep_i}x"
                    out_dir = run_root / "outputs" / pid / f"rep_{rep_i}x" / prompt_name / cond
                    out_dir.mkdir(parents=True, exist_ok=True)
                    if (out_dir / "repaired.json").exists():
                        continue

                    # Save prompt + doc for audit
                    (out_dir / "document_source.txt").write_text(doc_text, encoding="utf-8")
                    (out_dir / "prompt_template.txt").write_text(prompt_tmpl, encoding="utf-8")

                    result = client.chat_completions(user_prompt=prompt_tmpl, document_text=doc_text)
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

                    repair = repair_and_analyze(raw, patient_id=pid)
                    _write_json(out_dir / "repair_event.json", asdict(repair))
                    if repair.repaired_obj is None:
                        raise RuntimeError(f"Repair returned None for {call_id}")

                    ent_n = _entity_count(repair.repaired_obj)
                    if ent_n == 0:
                        _write_text(out_dir / "response_error.txt", "repaired_entities_empty")
                        raise RuntimeError(f"Empty repaired extraction for {call_id}")

                    (out_dir / "repaired.json").write_text(json.dumps(repair.repaired_obj, indent=2), encoding="utf-8")

                    pred = normalize_extraction(repair.repaired_obj, patient_id=pid)
                    goldn = normalize_extraction(gold, patient_id=pid)
                    scores = score_against_gold(pred, goldn)

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
                            "repetition": rep_i,
                            "prompt": prompt_name,
                            "condition": cond,
                            "micro_f1": scores["micro_f1"],
                            "omission_count": scores["omission_count"],
                            "hallucination_count": scores["hallucination_count"],
                        }
                    )
                    st_rows.append(
                        {
                            "run_id": run_id,
                            "patient_id": pid,
                            "repetition": rep_i,
                            "prompt": prompt_name,
                            "condition": cond,
                            "raw_valid_json": int(repair.raw_valid_json),
                            "repair_needed": int(repair.repair_needed),
                            "structural_drift_score": float(sds),
                        }
                    )

        # checkpoint flush per patient
        pd.DataFrame(sem_rows).to_csv(run_root / "metrics" / "semantic_metrics_partial.csv", index=False)
        pd.DataFrame(st_rows).to_csv(run_root / "metrics" / "structural_metrics_partial.csv", index=False)

    sem = pd.DataFrame(sem_rows)
    st = pd.DataFrame(st_rows)
    sem.to_csv(run_root / "metrics" / "semantic_metrics.csv", index=False)
    st.to_csv(run_root / "metrics" / "structural_metrics.csv", index=False)

    # Summaries per prompt x condition
    rows = []
    for (prompt_name, cond), g in sem.groupby(["prompt", "condition"]):
        # simple by-rep means
        by_rep = g.groupby("repetition", as_index=False).agg(
            n=("micro_f1", "count"),
            f1_mean=("micro_f1", "mean"),
            omission_mean=("omission_count", "mean"),
            halluc_mean=("hallucination_count", "mean"),
        )
        by_rep["prompt"] = prompt_name
        by_rep["condition"] = cond
        rows.append(by_rep)
    summary = pd.concat(rows, ignore_index=True).sort_values(["prompt", "condition", "repetition"])
    summary.to_csv(run_root / "metrics" / "scaling_by_prompt_condition.csv", index=False)

    # Compute DRE per prompt: (drop redundancy) - (drop filler), baseline 1x
    dre_rows = []
    for prompt_name, g in summary.groupby("prompt"):
        gr = g[g["condition"] == "redundancy"].set_index("repetition")
        gc = g[g["condition"] == "filler_control"].set_index("repetition")
        base_r = float(gr.loc[1, "f1_mean"])
        base_c = float(gc.loc[1, "f1_mean"])
        for rep in reps:
            drop_r = base_r - float(gr.loc[rep, "f1_mean"])
            drop_c = base_c - float(gc.loc[rep, "f1_mean"])
            dre_rows.append(
                {
                    "prompt": prompt_name,
                    "repetition": int(rep),
                    "F1_drop_redundancy": drop_r,
                    "F1_drop_control": drop_c,
                    "DRE": drop_r - drop_c,
                }
            )
    pd.DataFrame(dre_rows).sort_values(["prompt", "repetition"]).to_csv(run_root / "DRE_by_prompt.csv", index=False)

    # minimal plot: DRE by prompt (midrange)
    import matplotlib.pyplot as plt

    plt.rcParams.update({"figure.dpi": 200, "savefig.dpi": 400, "font.size": 10})
    plt.figure(figsize=(5.4, 3.2))
    for prompt_name in ["promptA", "promptB", "promptC"]:
        d = pd.DataFrame(dre_rows)
        d = d[d["prompt"] == prompt_name].sort_values("repetition")
        plt.plot(d["repetition"], d["DRE"], marker="o", linewidth=1.6, label=prompt_name)
    plt.axhline(0.0, color="black", linewidth=0.8, alpha=0.5)
    plt.xscale("log", base=2)
    plt.xticks(reps, [str(r) for r in reps])
    plt.xlabel("Repetition level (x)")
    plt.ylabel("DRE (F1 drop diff)")
    plt.grid(True, axis="y", linestyle="--", linewidth=0.6, alpha=0.6)
    plt.legend(frameon=False)
    plt.tight_layout()
    plt.savefig(run_root / "plots" / "dre_by_prompt.png")
    plt.close()

    # structural plots per prompt/condition
    generate_structural_plots(run_root / "metrics" / "structural_metrics.csv", run_root / "plots")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--num_patients", type=int, default=50)
    ap.add_argument("--reps", type=str, default="1,5,10,16")
    args = ap.parse_args()

    if not args.run:
        ap.print_help()
        return 0

    reps = [int(x.strip()) for x in args.reps.split(",") if x.strip()]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_root = Path("data/runs") / f"prompt_robustness_{ts}"
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return run(run_root=run_root, num_patients=int(args.num_patients), reps=reps)


if __name__ == "__main__":
    raise SystemExit(main())
