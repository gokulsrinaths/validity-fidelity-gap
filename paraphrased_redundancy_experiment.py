from __future__ import annotations

import argparse
import json
import logging
import os
import random
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from dotenv import load_dotenv

from analysis import estimate_tokens, write_json
from config import get_settings
from evaluator import normalize_extraction, score_against_gold, structural_drift_score
from plotting import generate_structural_plots
from repair_json import repair_and_analyze
from run_experiments import (
    FILLER_PARAGRAPHS,
    extract_pdf_text,
    generate_synthetic_patients,
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


@dataclass(frozen=True)
class TextResult:
    ok: bool
    status_code: int | None
    latency_s: float
    response_json: dict[str, Any] | None
    error: str | None

    @property
    def content_text(self) -> str | None:
        if not self.response_json:
            return None
        try:
            return self.response_json["choices"][0]["message"]["content"]
        except Exception:
            return None


def _deepinfra_text_call(*, settings, system_prompt: str, user_prompt: str, temperature: float, max_tokens: int) -> TextResult:
    api_key = os.getenv("DEEPINFRA_API_KEY")
    if not api_key:
        raise RuntimeError("Missing DEEPINFRA_API_KEY in environment/.env")
    url = f"{settings.deepinfra_base_url}/chat/completions"
    payload = {
        "model": settings.model,
        "temperature": float(temperature),
        "top_p": settings.top_p,
        "max_tokens": int(max_tokens),
        **({"seed": settings.seed} if settings.seed is not None else {}),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    backoff = settings.initial_backoff_s
    last_err: str | None = None
    for attempt in range(1, settings.max_retries + 1):
        t0 = time.perf_counter()
        try:
            resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=settings.request_timeout_s)
            latency = time.perf_counter() - t0
            if resp.status_code >= 500:
                last_err = f"Server error ({resp.status_code}): {resp.text[:300]}"
                raise RuntimeError(last_err)
            if resp.status_code >= 400:
                return TextResult(False, resp.status_code, latency, None, f"Request error ({resp.status_code}): {resp.text[:300]}")
            try:
                j = resp.json()
            except Exception:
                return TextResult(False, resp.status_code, latency, None, f"Non-JSON response: {resp.text[:300]}")
            return TextResult(True, resp.status_code, latency, j, None)
        except (requests.Timeout, requests.ConnectionError, RuntimeError) as e:
            latency = time.perf_counter() - t0
            last_err = str(e)
            if attempt == settings.max_retries:
                return TextResult(False, None, latency, None, f"Failed after {attempt} attempts: {last_err}")
            time.sleep(backoff)
            backoff *= 2
    return TextResult(False, None, 0.0, None, last_err or "unknown_error")


def _paraphrase_variants(*, settings, base_text: str, k: int, rng: random.Random, out_dir: Path) -> list[str]:
    """
    Generate k paraphrases intended to preserve factual content.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    system = (
        "You rewrite clinical notes. Preserve all medical facts exactly.\n"
        "Do NOT add, remove, or change any diagnoses, medications, dosages, labs, vitals, procedures, dates, or plans.\n"
        "Do NOT introduce new entities. Keep meaning identical.\n"
        "Output ONLY plain text. No markdown."
    )

    variants: list[str] = []
    for i in range(k):
        user = (
            "Paraphrase the following clinical note while preserving all facts exactly.\n"
            "Use different wording and sentence structure, but keep the same sections and content.\n\n"
            f"NOTE:\n{base_text.strip()}\n"
        )
        res = _deepinfra_text_call(settings=settings, system_prompt=system, user_prompt=user, temperature=0.2, max_tokens=2048)
        _write_json(out_dir / f"paraphrase_meta_{i+1:02d}.json", {"ok": res.ok, "status_code": res.status_code, "latency_s": res.latency_s, "error": res.error})
        if not res.ok:
            raise RuntimeError(f"Paraphrase call failed: {res.error}")
        txt = (res.content_text or "").strip()
        if not txt:
            raise RuntimeError("Empty paraphrase output")
        (out_dir / f"paraphrase_{i+1:02d}.txt").write_text(txt + "\n", encoding="utf-8")
        variants.append(txt + "\n")
    return variants


def run(*, num_patients: int, reps: list[int], runs_per_condition: int, k_paraphrases: int) -> int:
    settings = get_settings()
    load_dotenv(settings.project_root / ".env")

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_root = Path("data/runs") / f"paraphrased_redundancy_{run_id}"
    run_root.mkdir(parents=True, exist_ok=True)
    for sub in ("outputs", "metrics", "plots", "docs"):
        (run_root / sub).mkdir(parents=True, exist_ok=True)

    write_json(
        run_root / "manifest.json",
        {
            "run_id": run_id,
            "experiment": "paraphrased_redundancy_midrange",
            "model_extraction": settings.model,
            "model_paraphrase": settings.model,
            "temperature_extraction": settings.temperature,
            "temperature_paraphrase": 0.2,
            "num_patients": num_patients,
            "repetition_levels": reps,
            "runs_per_condition": runs_per_condition,
            "k_paraphrases": k_paraphrases,
            "conditions": ["paraphrased_redundancy", "filler_control"],
            "note": "Paraphrases are generated to preserve facts; extraction prompt/schema unchanged.",
        },
    )

    patients = generate_synthetic_patients(settings)[: int(num_patients)]
    write_patient_files(settings, patients)
    rng = random.Random(settings.random_seed)

    # Use the standard DeepInfra JSON-mode extraction client
    from deepinfra_client import DeepInfraClient

    client = DeepInfraClient(settings)

    sem_rows: list[dict[str, Any]] = []
    st_rows: list[dict[str, Any]] = []

    for p in patients:
        pid = p["patient_id"]
        base_text = p["text"].strip() + "\n"
        gt_path = settings.data_dir / pid / "ground_truth" / f"{pid}.json"
        gold = json.loads(gt_path.read_text(encoding="utf-8"))

        # generate a small bank of paraphrases once per patient (reused across reps)
        bank_k = max(1, min(int(k_paraphrases), 8))
        bank = _paraphrase_variants(settings=settings, base_text=base_text, k=bank_k, rng=rng, out_dir=run_root / "docs" / pid / "paraphrases")

        for rep in reps:
            rep_i = int(rep)
            if rep_i == 1:
                para_doc = base_text
            else:
                # build document by cycling paraphrase bank to reach rep_i copies
                parts = [bank[i % len(bank)].strip() for i in range(rep_i)]
                para_doc = ("\n\n".join(parts)).strip() + "\n"

            # target length matches the original exact-redundancy document length (heuristic token estimator)
            target_tokens = estimate_tokens(len((base_text * rep_i).strip() + "\n"), settings.est_chars_per_token)
            filler_doc = _build_filler_control(base_text=base_text, target_tokens=target_tokens, settings=settings, rng=rng)

            # save docs
            ddir = run_root / "docs" / pid / f"rep_{rep_i}x"
            ddir.mkdir(parents=True, exist_ok=True)
            (ddir / "paraphrased_redundancy.txt").write_text(para_doc, encoding="utf-8")
            (ddir / "filler_control.txt").write_text(filler_doc, encoding="utf-8")

            # render/extract
            para_pdf = ddir / "paraphrased_redundancy.pdf"
            fill_pdf = ddir / "filler_control.pdf"
            render_pdf(para_doc, para_pdf)
            render_pdf(filler_doc, fill_pdf)
            para_text = extract_pdf_text(para_pdf)
            fill_text = extract_pdf_text(fill_pdf)

            for cond, doc_text in [("paraphrased_redundancy", para_text), ("filler_control", fill_text)]:
                for run_idx in range(1, runs_per_condition + 1):
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
                        raise RuntimeError(f"Extraction call failed for {pid} {cond} rep={rep_i}: {result.error}")

                    raw = result.content_text
                    if raw is None or not raw.strip():
                        _write_text(out_dir / "response_error.txt", "empty_or_missing_message_content")
                        raise RuntimeError(f"Empty extraction content for {pid} {cond} rep={rep_i}")
                    (out_dir / "raw_response.txt").write_text(raw, encoding="utf-8")
                    if result.usage is not None:
                        _write_json(out_dir / "usage.json", result.usage)
                    if result.response_json is not None:
                        _write_json(out_dir / "response.json", result.response_json)

                    repair = repair_and_analyze(raw, patient_id=pid)
                    _write_json(out_dir / "repair_event.json", asdict(repair))
                    if repair.repaired_obj is None:
                        raise RuntimeError("repair returned None")
                    ent_n = _entity_count(repair.repaired_obj)
                    if ent_n == 0:
                        raise RuntimeError("empty extraction after repair")
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
                            "condition": cond,
                            "run": run_idx,
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
                            "condition": cond,
                            "run": run_idx,
                            "raw_valid_json": int(repair.raw_valid_json),
                            "repair_needed": int(repair.repair_needed),
                            "structural_drift_score": float(sds),
                        }
                    )

        # checkpoint flush
        pd.DataFrame(sem_rows).to_csv(run_root / "metrics" / "semantic_metrics_partial.csv", index=False)

    sem = pd.DataFrame(sem_rows)
    st = pd.DataFrame(st_rows)
    sem.to_csv(run_root / "metrics" / "semantic_metrics.csv", index=False)
    st.to_csv(run_root / "metrics" / "structural_metrics.csv", index=False)
    generate_structural_plots(run_root / "metrics" / "structural_metrics.csv", run_root / "plots")

    # DRE summary (means)
    rows = []
    for cond, g in sem.groupby("condition"):
        by = g.groupby("repetition", as_index=False).agg(f1_mean=("micro_f1", "mean"))
        by["condition"] = cond
        rows.append(by)
    summary = pd.concat(rows, ignore_index=True)
    summary.to_csv(run_root / "metrics" / "f1_by_condition.csv", index=False)

    # compute DRE
    red = summary[summary["condition"] == "paraphrased_redundancy"].set_index("repetition")
    ctl = summary[summary["condition"] == "filler_control"].set_index("repetition")
    base_r = float(red.loc[1, "f1_mean"])
    base_c = float(ctl.loc[1, "f1_mean"])
    dre_rows = []
    for rep in reps:
        drop_r = base_r - float(red.loc[rep, "f1_mean"])
        drop_c = base_c - float(ctl.loc[rep, "f1_mean"])
        dre_rows.append({"repetition": int(rep), "F1_drop_paraphrase": drop_r, "F1_drop_control": drop_c, "DRE": drop_r - drop_c})
    pd.DataFrame(dre_rows).to_csv(run_root / "DRE_statistics.csv", index=False)

    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--num_patients", type=int, default=50)
    ap.add_argument("--reps", type=str, default="1,5,10,16")
    ap.add_argument("--runs_per_condition", type=int, default=1)
    ap.add_argument("--k_paraphrases", type=int, default=4)
    args = ap.parse_args()

    reps = [int(x.strip()) for x in args.reps.split(",") if x.strip()]
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return run(num_patients=int(args.num_patients), reps=reps, runs_per_condition=int(args.runs_per_condition), k_paraphrases=int(args.k_paraphrases))


if __name__ == "__main__":
    raise SystemExit(main())

