from __future__ import annotations

import json
import logging
import os
import random
from datetime import datetime
from pathlib import Path

import pandas as pd
import pdfplumber
from dotenv import load_dotenv
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from tqdm import tqdm

from config import get_settings
from deepinfra_client import DeepInfraAuthError, DeepInfraClient
from analysis import estimate_tokens, write_json
from evaluator import (
    divergence_score,
    normalize_extraction,
    score_against_gold,
    structural_drift_score,
)
from plotting import generate_plots, generate_structural_plots, generate_variance_plots
from repair_json import repair_and_analyze


def setup_logging(log_path: Path):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler()],
    )


def ensure_dir_structure(settings):
    for sub in ("outputs", "metrics", "plots"):
        (settings.data_dir / sub).mkdir(parents=True, exist_ok=True)

    for i in range(1, settings.num_patients + 1):
        pid = f"patient_{i:02d}"
        base = settings.data_dir / pid
        for sub in ("raw", "pdfs", "ground_truth"):
            (base / sub).mkdir(parents=True, exist_ok=True)


def _wrap_lines(text: str, width: int = 95) -> list[str]:
    import textwrap

    out = []
    for para in text.splitlines():
        if not para.strip():
            out.append("")
            continue
        out.extend(textwrap.wrap(para, width=width, replace_whitespace=False))
    return out


def render_pdf(text: str, out_pdf: Path):
    out_pdf.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_pdf), pagesize=letter)
    w, h = letter
    margin = 0.75 * inch
    y = h - margin
    line_height = 12

    for line in _wrap_lines(text, width=105):
        if y < margin + line_height:
            c.showPage()
            y = h - margin
        c.setFont("Times-Roman", 10)
        c.drawString(margin, y, line)
        y -= line_height

    c.save()


def extract_pdf_text(pdf_path: Path) -> str:
    with pdfplumber.open(str(pdf_path)) as pdf:
        pages = []
        for p in pdf.pages:
            pages.append(p.extract_text() or "")
    return "\n".join(pages).strip()


def pdf_page_count(pdf_path: Path) -> int:
    with pdfplumber.open(str(pdf_path)) as pdf:
        return len(pdf.pages)


FILLER_PARAGRAPHS = [
    "Administrative note: this section contains non-clinical placeholder text for document length control.",
    "The quick brown fox jumps over the lazy dog. This sentence is repeated for length matching only.",
    "Policy reminder: Always verify patient identity using two identifiers per standard procedure.",
    "Scheduling information: Follow-up appointments may be arranged through the clinic front desk.",
]


def build_constant_length_control(
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


def compute_variance_metrics(semantic_df: pd.DataFrame, structural_df: pd.DataFrame) -> pd.DataFrame:
    merged = semantic_df.merge(
        structural_df[
            ["patient_id", "repetition", "run", "structural_drift_score", "raw_valid_json", "repair_needed"]
        ],
        on=["patient_id", "repetition", "run"],
        how="left",
    )

    rows = []
    for (pid, rep), g in merged.groupby(["patient_id", "repetition"]):
        if len(g) < 2:
            continue
        # Semantic stability proxy: variability of drift_vs_1x across runs.
        sem_var = float(g["drift_vs_1x"].std(ddof=0) or 0.0)
        rows.append(
            {
                "patient_id": pid,
                "repetition": int(rep),
                "n_runs": int(len(g)),
                "semantic_pairwise_jaccard_distance_mean": sem_var,
                "hallucination_std": float(g["hallucination_count"].std(ddof=0) or 0.0),
                "omission_std": float(g["omission_count"].std(ddof=0) or 0.0),
                "sds_std": float(g["structural_drift_score"].std(ddof=0) or 0.0),
                "raw_json_valid_rate": float(g["raw_valid_json"].mean()),
                "repair_rate": float(g["repair_needed"].mean()),
            }
        )

    return pd.DataFrame(rows)


def detect_early_collapse(by_rep_sem: pd.DataFrame, by_rep_str: pd.DataFrame) -> list[str]:
    flags: list[str] = []
    s = by_rep_sem.merge(by_rep_str, on="repetition", how="left").sort_values("repetition")
    if s.empty:
        return flags
    for i in range(1, len(s)):
        prev = float(s.iloc[i - 1]["raw_json_valid_rate"])
        cur = float(s.iloc[i]["raw_json_valid_rate"])
        if prev - cur >= 0.30:
            flags.append(
                f"JSON validity collapse: {int(s.iloc[i-1]['repetition'])}x -> {int(s.iloc[i]['repetition'])}x "
                f"({prev:.2f} -> {cur:.2f})"
            )
    for metric, name in [("hallucination_mean", "hallucinations"), ("omission_mean", "omissions")]:
        for i in range(1, len(s)):
            prev = float(s.iloc[i - 1][metric])
            cur = float(s.iloc[i][metric])
            if prev > 0 and (cur / prev) >= 2.0 and (cur - prev) >= 1.0:
                flags.append(
                    f"Sharp {name} increase: {int(s.iloc[i-1]['repetition'])}x -> {int(s.iloc[i]['repetition'])}x "
                    f"({prev:.2f} -> {cur:.2f})"
                )
    return flags


def generate_synthetic_patients(settings):
    """
    Creates N ~one-page synthetic clinical documents plus ground truth JSON.
    """
    patients = []
    base_texts = [
        {
            "patient_id": "patient_01",
            "text": """DISCHARGE SUMMARY
Name: Alex Rivera    MRN: 001-88421    DOB: 1978-04-12
Admit Date: 2026-04-03   Discharge Date: 2026-04-05

CHIEF COMPLAINT
Shortness of breath and wheezing.

HPI
47-year-old with history of asthma presents with 2 days of cough, wheeze, and dyspnea after URI symptoms.

PAST MEDICAL HISTORY
- Asthma
- Seasonal allergic rhinitis

MEDICATIONS ON DISCHARGE
- Albuterol inhaler 90 mcg: 2 puffs inhaled q4-6h PRN wheeze
- Prednisone 40 mg PO daily x 5 days
- Cetirizine 10 mg PO daily

OBSERVATIONS / VITALS
- SpO2 94% on room air
- Peak flow 320 L/min

PROCEDURES
- Nebulized bronchodilator treatment in ED

ASSESSMENT & PLAN
Asthma exacerbation: continue steroid burst and rescue inhaler; follow up with PCP in 1 week.
""",
            "gt": {
                "conditions": ["Asthma", "Seasonal allergic rhinitis", "Asthma exacerbation"],
                "medications": ["Albuterol inhaler 90 mcg 2 puffs q4-6h PRN", "Prednisone 40 mg daily x 5 days", "Cetirizine 10 mg daily"],
                "observations": ["SpO2 94% on room air", "Peak flow 320 L/min"],
                "procedures": ["Nebulized bronchodilator treatment"],
            },
        },
        {
            "patient_id": "patient_02",
            "text": """ENCOUNTER NOTE (ED)
Name: Priya Shah   MRN: 002-11290   DOB: 1990-11-03
Date: 2026-03-18

CHIEF COMPLAINT
Right lower quadrant abdominal pain.

HPI
35-year-old with 12 hours of RLQ pain, nausea, and low-grade fever.

ASSESSMENT
Acute appendicitis.

PROCEDURES
- Laparoscopic appendectomy performed 2026-03-18

MEDICATIONS
- Ceftriaxone 1 g IV pre-op
- Metronidazole 500 mg IV pre-op
- Acetaminophen 650 mg PO q6h PRN pain

OBSERVATIONS
- Temp 38.1 C
- WBC 14.2 K/uL

PLAN
Post-op care, advance diet as tolerated, follow up in surgery clinic in 2 weeks.
""",
            "gt": {
                "conditions": ["Acute appendicitis"],
                "medications": ["Ceftriaxone 1 g IV pre-op", "Metronidazole 500 mg IV pre-op", "Acetaminophen 650 mg q6h PRN"],
                "observations": ["Temp 38.1 C", "WBC 14.2 K/uL"],
                "procedures": ["Laparoscopic appendectomy"],
            },
        },
        {
            "patient_id": "patient_03",
            "text": """DISCHARGE INSTRUCTIONS
Name: Maria Gomez  MRN: 003-77211  DOB: 1962-02-22
Admit: 2026-02-10  Discharge: 2026-02-12

DIAGNOSES
- Type 2 diabetes mellitus
- Hypertension
- Diabetic foot ulcer (left)

HOSPITAL COURSE
Treated for infected diabetic foot ulcer with IV antibiotics; improved.

MEDICATIONS
- Metformin 1000 mg PO BID with meals
- Lisinopril 10 mg PO daily
- Amoxicillin-clavulanate 875/125 mg PO BID x 7 days

OBSERVATIONS
- A1c 8.7%
- BP 152/92 mmHg

PROCEDURES
- Wound debridement (left foot) 2026-02-11

PLAN
Wound care follow up, glucose monitoring, PCP follow up in 1 week.
""",
            "gt": {
                "conditions": ["Type 2 diabetes mellitus", "Hypertension", "Diabetic foot ulcer"],
                "medications": ["Metformin 1000 mg BID", "Lisinopril 10 mg daily", "Amoxicillin-clavulanate 875/125 mg BID x 7 days"],
                "observations": ["A1c 8.7%", "BP 152/92 mmHg"],
                "procedures": ["Wound debridement"],
            },
        },
        {
            "patient_id": "patient_04",
            "text": """CLINIC VISIT NOTE
Name: Jordan Lee  MRN: 004-44321  DOB: 1985-07-09
Date: 2026-01-27

REASON FOR VISIT
Follow-up for depression and insomnia.

ASSESSMENT
- Major depressive disorder
- Insomnia

MEDICATIONS
- Sertraline 50 mg PO daily
- Trazodone 50 mg PO at bedtime PRN sleep

OBSERVATIONS
- PHQ-9 score 16
- Weight 78.4 kg

PLAN
Continue sertraline; sleep hygiene counseling; follow up in 4 weeks.
""",
            "gt": {
                "conditions": ["Major depressive disorder", "Insomnia"],
                "medications": ["Sertraline 50 mg daily", "Trazodone 50 mg at bedtime PRN"],
                "observations": ["PHQ-9 score 16", "Weight 78.4 kg"],
                "procedures": [],
            },
        },
        {
            "patient_id": "patient_05",
            "text": """HOSPITAL DISCHARGE SUMMARY
Name: Sam Nguyen  MRN: 005-90122  DOB: 1955-05-30
Admit: 2026-04-21  Discharge: 2026-04-24

DIAGNOSES
- Heart failure with reduced ejection fraction (HFrEF)
- Atrial fibrillation

ECHO
LVEF 30%.

MEDICATIONS ON DISCHARGE
- Furosemide 40 mg PO daily
- Metoprolol succinate 50 mg PO daily
- Apixaban 5 mg PO BID

OBSERVATIONS
- BNP 820 pg/mL
- HR 110 bpm irregular

PROCEDURES
- Electrical cardioversion 2026-04-22

PLAN
Daily weights; low-sodium diet; cardiology follow up in 1 week.
""",
            "gt": {
                "conditions": ["Heart failure with reduced ejection fraction", "Atrial fibrillation"],
                "medications": ["Furosemide 40 mg daily", "Metoprolol succinate 50 mg daily", "Apixaban 5 mg BID"],
                "observations": ["LVEF 30%", "BNP 820 pg/mL", "HR 110 bpm irregular"],
                "procedures": ["Electrical cardioversion"],
            },
        },
        {
            "patient_id": "patient_06",
            "text": """URGENT CARE NOTE
Name: Taylor Brown  MRN: 006-55211  DOB: 2001-09-14
Date: 2026-05-02

CHIEF COMPLAINT
Sore throat and fever.

ASSESSMENT
Streptococcal pharyngitis (rapid strep positive).

MEDICATIONS
- Amoxicillin 500 mg PO BID x 10 days
- Ibuprofen 400 mg PO q6h PRN pain/fever

OBSERVATIONS
- Temp 39.0 C
- Rapid strep test: positive

PLAN
Complete antibiotics; return precautions discussed.
""",
            "gt": {
                "conditions": ["Streptococcal pharyngitis"],
                "medications": ["Amoxicillin 500 mg BID x 10 days", "Ibuprofen 400 mg q6h PRN"],
                "observations": ["Temp 39.0 C", "Rapid strep test positive"],
                "procedures": [],
            },
        },
        {
            "patient_id": "patient_07",
            "text": """PRE-OP HISTORY & PHYSICAL
Name: Evelyn Chen  MRN: 007-22018  DOB: 1971-12-01
Date: 2026-03-02

PLANNED PROCEDURE
Right total knee arthroplasty.

PAST MEDICAL HISTORY
- Osteoarthritis (right knee)
- Hyperlipidemia

MEDICATIONS
- Atorvastatin 20 mg PO nightly
- Naproxen 500 mg PO BID PRN pain (hold 7 days prior to surgery)

OBSERVATIONS
- BMI 31.2 kg/m2
- LDL 168 mg/dL

ASSESSMENT & PLAN
Proceed with surgery; DVT prophylaxis plan reviewed.
""",
            "gt": {
                "conditions": ["Osteoarthritis", "Hyperlipidemia"],
                "medications": ["Atorvastatin 20 mg nightly", "Naproxen 500 mg BID PRN"],
                "observations": ["BMI 31.2 kg/m2", "LDL 168 mg/dL"],
                "procedures": ["Right total knee arthroplasty"],
            },
        },
        {
            "patient_id": "patient_08",
            "text": """DISCHARGE SUMMARY
Name: Omar Haddad  MRN: 008-33009  DOB: 1948-08-19
Admit: 2026-02-28  Discharge: 2026-03-03

DIAGNOSES
- Community-acquired pneumonia
- Chronic obstructive pulmonary disease (COPD)

IMAGING
Chest X-ray: right lower lobe infiltrate.

MEDICATIONS
- Azithromycin 500 mg PO day 1 then 250 mg daily days 2-5
- Prednisone 40 mg PO daily x 5 days
- Tiotropium inhaler: 2 puffs inhaled daily

OBSERVATIONS
- SpO2 91% on room air
- RR 24 /min

PROCEDURES
- Supplemental oxygen therapy

PLAN
Complete antibiotics; pulmonary follow up in 2 weeks.
""",
            "gt": {
                "conditions": ["Community-acquired pneumonia", "Chronic obstructive pulmonary disease"],
                "medications": ["Azithromycin 500 mg day 1 then 250 mg daily days 2-5", "Prednisone 40 mg daily x 5 days", "Tiotropium inhaler daily"],
                "observations": ["SpO2 91% on room air", "RR 24 /min", "Chest X-ray right lower lobe infiltrate"],
                "procedures": ["Supplemental oxygen therapy"],
            },
        },
        {
            "patient_id": "patient_09",
            "text": """OUTPATIENT NOTE
Name: Aisha Johnson  MRN: 009-99110  DOB: 1988-06-05
Date: 2026-04-08

ASSESSMENT
- Migraine without aura

MEDICATIONS
- Sumatriptan 50 mg PO at onset of headache; may repeat once in 2 hours
- Propranolol 20 mg PO BID for migraine prevention

OBSERVATIONS
- BP 118/74 mmHg
- Neuro exam: normal

PLAN
Trigger avoidance; headache diary; follow up in 6 weeks.
""",
            "gt": {
                "conditions": ["Migraine without aura"],
                "medications": ["Sumatriptan 50 mg at onset may repeat once", "Propranolol 20 mg BID"],
                "observations": ["BP 118/74 mmHg", "Neuro exam normal"],
                "procedures": [],
            },
        },
        {
            "patient_id": "patient_10",
            "text": """DISCHARGE SUMMARY
Name: Robert King  MRN: 010-77345  DOB: 1969-10-28
Admit: 2026-05-10  Discharge: 2026-05-11

DIAGNOSES
- Acute kidney injury (pre-renal)
- Dehydration

HOSPITAL COURSE
Improved after IV fluids.

MEDICATIONS
- Normal saline IV fluids (in hospital)
- Ondansetron 4 mg ODT q8h PRN nausea

OBSERVATIONS
- Creatinine 2.1 mg/dL on admission, improved to 1.4 mg/dL at discharge
- BUN 38 mg/dL

PROCEDURES
- IV fluid resuscitation

PLAN
Oral hydration; avoid NSAIDs; repeat BMP with PCP in 3 days.
""",
            "gt": {
                "conditions": ["Acute kidney injury", "Dehydration"],
                "medications": ["Normal saline IV fluids", "Ondansetron 4 mg ODT q8h PRN"],
                "observations": ["Creatinine 2.1 mg/dL improved to 1.4 mg/dL", "BUN 38 mg/dL"],
                "procedures": ["IV fluid resuscitation"],
            },
        },
    ]

    # Base templates define 10 canonical notes. If more patients are requested, we cycle templates
    # (keeping the same semantic content) to increase N for statistical stability experiments.
    import copy

    n = int(getattr(settings, "num_patients", 10) or 10)
    for i in range(1, n + 1):
        tmpl = base_texts[(i - 1) % len(base_texts)]
        pid = f"patient_{i:02d}"
        gt = copy.deepcopy(tmpl["gt"])
        patients.append({"patient_id": pid, "text": tmpl["text"], "gt": gt})
    return patients


def write_patient_files(settings, patients):
    for p in patients:
        pid = p["patient_id"]
        base_dir = settings.data_dir / pid
        raw_dir = base_dir / "raw"
        pdf_dir = base_dir / "pdfs"
        gt_dir = base_dir / "ground_truth"

        base_text = p["text"].strip() + "\n"
        (raw_dir / f"{pid}_base.txt").write_text(base_text, encoding="utf-8")

        gt = {
            "patient_id": pid,
            "conditions": p["gt"]["conditions"],
            "medications": p["gt"]["medications"],
            "observations": p["gt"]["observations"],
            "procedures": p["gt"]["procedures"],
        }
        (gt_dir / f"{pid}.json").write_text(json.dumps(gt, indent=2), encoding="utf-8")

        for rep in settings.repetition_levels:
            rep_text = (base_text * rep).strip() + "\n"
            raw_path = raw_dir / f"{pid}_rep_{rep}x.txt"
            pdf_path = pdf_dir / f"{pid}_rep_{rep}x.pdf"
            raw_path.write_text(rep_text, encoding="utf-8")
            if not pdf_path.exists():
                render_pdf(rep_text, pdf_path)


def run(*, run_root: Path | None = None) -> int:
    settings = get_settings()
    load_dotenv(settings.project_root / ".env")
    ensure_dir_structure(settings)

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_root = run_root or (settings.data_dir / "runs" / f"run_{run_id}")
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "raw_outputs").mkdir(parents=True, exist_ok=True)
    (run_root / "repaired_outputs").mkdir(parents=True, exist_ok=True)
    (run_root / "outputs").mkdir(parents=True, exist_ok=True)
    setup_logging(run_root / "run.log")
    logging.info("Starting Redundancy Drift pilot run_id=%s", run_id)
    random.seed(settings.random_seed)
    rng = random.Random(settings.random_seed)
    write_json(run_root / "config.json", settings.__dict__)

    patients = generate_synthetic_patients(settings)
    write_patient_files(settings, patients)

    try:
        client = DeepInfraClient(settings)
    except DeepInfraAuthError as e:
        logging.error(str(e))
        logging.error("Aborting before any API calls.")
        return 2

    semantic_rows: list[dict] = []
    structural_rows: list[dict] = []
    context_rows: list[dict] = []
    agg_rows = []

    for p in tqdm(patients, desc="Patients"):
        pid = p["patient_id"]
        gt_path = settings.data_dir / pid / "ground_truth" / f"{pid}.json"
        gold = json.loads(gt_path.read_text(encoding="utf-8"))

        one_x_norm: dict | None = None

        for rep in settings.repetition_levels:
            pdf_path = settings.data_dir / pid / "pdfs" / f"{pid}_rep_{rep}x.pdf"
            doc_text = extract_pdf_text(pdf_path)
            pages = pdf_page_count(pdf_path)
            char_count = len(doc_text)
            est_toks = estimate_tokens(char_count, settings.est_chars_per_token)

            for run_idx in range(1, settings.runs_per_condition + 1):
                ts = datetime.now().isoformat()
                call_id = f"{run_id}__{pid}__rep_{rep}x__run_{run_idx:02d}"
                out_dir = run_root / "outputs" / pid / f"rep_{rep}x" / f"run_{run_idx:02d}"
                out_dir.mkdir(parents=True, exist_ok=True)

                prompt = settings.extraction_prompt_template.format(document_text=doc_text)
                (out_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
                (out_dir / "document_source.txt").write_text(doc_text, encoding="utf-8")

                result = client.chat_completions(
                    user_prompt=settings.extraction_prompt_template, document_text=doc_text
                )

                # Always persist response metadata for post-hoc debugging.
                (out_dir / "response_meta.json").write_text(
                    json.dumps(
                        {
                            "ok": result.ok,
                            "status_code": result.status_code,
                            "latency_s": result.latency_s,
                            "error": result.error,
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )

                # Fail fast on upstream API failures to avoid silently producing empty outputs/metrics.
                if not result.ok:
                    (out_dir / "response_error.txt").write_text(result.error or "unknown_error", encoding="utf-8")
                    raise RuntimeError(
                        f"DeepInfra call failed for {call_id}: {result.status_code} {result.error}"
                    )

                (out_dir / "latency_s.txt").write_text(f"{result.latency_s:.6f}\n", encoding="utf-8")
                if result.usage is not None:
                    (out_dir / "usage.json").write_text(
                        json.dumps(result.usage, indent=2), encoding="utf-8"
                    )

                raw_text = result.content_text
                if raw_text is None or not raw_text.strip():
                    (out_dir / "response_error.txt").write_text(
                        "empty_or_missing_message_content", encoding="utf-8"
                    )
                    raise RuntimeError(f"Empty model content for {call_id} (ok={result.ok})")
                (out_dir / "raw_response.txt").write_text(raw_text, encoding="utf-8")
                if result.response_json is not None:
                    (out_dir / "response.json").write_text(
                        json.dumps(result.response_json, indent=2), encoding="utf-8"
                    )

                # Save benchmark-wide raw + repaired outputs (separate from per-call folder)
                raw_out_path = run_root / "raw_outputs" / f"{call_id}.txt"
                raw_out_path.write_text(raw_text, encoding="utf-8")

                repair = repair_and_analyze(raw_text, patient_id=pid)
                repaired_obj = repair.repaired_obj or {
                    "patient_id": pid,
                    "conditions": [],
                    "medications": [],
                    "observations": [],
                    "procedures": [],
                }

                # Fail-fast enforcement: do not silently "repair" malformed outputs into empty arrays.
                if not repair.raw_valid_json:
                    (out_dir / "response_error.txt").write_text("raw_json_parse_failed", encoding="utf-8")
                    raise RuntimeError(f"Raw JSON parsing failed for {call_id}")
                if not repair.schema_match:
                    (out_dir / "response_error.txt").write_text("raw_schema_mismatch", encoding="utf-8")
                    raise RuntimeError(f"Raw JSON schema mismatch for {call_id}")

                extracted_entities_n = sum(
                    len(repaired_obj.get(k) or []) for k in ("conditions", "medications", "observations", "procedures")
                )
                if extracted_entities_n == 0:
                    (out_dir / "response_error.txt").write_text("repaired_entities_empty", encoding="utf-8")
                    raise RuntimeError(f"Repaired extraction empty for {call_id}")

                repaired_out_path = run_root / "repaired_outputs" / f"{call_id}.json"
                repaired_out_path.write_text(json.dumps(repaired_obj, indent=2), encoding="utf-8")

                # Log repair events with operations applied
                if repair.repair_needed:
                    (out_dir / "repair_event.json").write_text(
                        json.dumps(
                            {
                                "call_id": call_id,
                                "patient_id": pid,
                                "repetition": rep,
                                "run": run_idx,
                                "markdown_fence_present": repair.markdown_fence_present,
                                "raw_valid_json": repair.raw_valid_json,
                                "schema_match": repair.schema_match,
                                "missing_keys": repair.missing_keys,
                                "extra_keys": repair.extra_keys,
                                "operations": repair.operations,
                            },
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                (out_dir / "repaired.json").write_text(
                    json.dumps(repaired_obj, indent=2), encoding="utf-8"
                )

                # Semantic scoring uses normalized repaired object to keep schema fixed while still measuring repair frequency.
                norm_pred = normalize_extraction(repaired_obj, patient_id=pid)
                norm_gold = normalize_extraction(gold, patient_id=pid)

                gold_scores = score_against_gold(norm_pred, norm_gold)

                if rep == 1 and run_idx == 1:
                    one_x_norm = norm_pred

                drift_vs_1x = (
                    divergence_score(norm_pred, one_x_norm)
                    if one_x_norm is not None
                    else {"jaccard_distance": 0.0, "jaccard_similarity": 1.0, "a_size": 0, "b_size": 0}
                )
                drift_vs_gold = divergence_score(norm_pred, norm_gold)

                drift_score = 0.5 * drift_vs_1x["jaccard_distance"] + 0.5 * drift_vs_gold[
                    "jaccard_distance"
                ]

                sds = structural_drift_score(
                    malformed_json=repair.malformed_json,
                    missing_keys_count=repair.missing_keys_count,
                    extra_keys_count=repair.extra_keys_count,
                    schema_match=repair.schema_match,
                    markdown_fence_present=repair.markdown_fence_present,
                )

                semantic_row = {
                    "run_id": run_id,
                    "patient_id": pid,
                    "repetition": rep,
                    "run": run_idx,
                    "model": settings.model,
                    "timestamp": ts,
                    "ok": int(result.ok),
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
                }
                semantic_rows.append(semantic_row)

                structural_row = {
                    "run_id": run_id,
                    "patient_id": pid,
                    "repetition": rep,
                    "run": run_idx,
                    "model": settings.model,
                    "timestamp": ts,
                    "ok": int(result.ok),
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
                }
                structural_rows.append(structural_row)

                # Per-call metrics snapshots (human-debuggable).
                (out_dir / "semantic_metrics.json").write_text(
                    json.dumps({**semantic_row, "extracted_entities_n": extracted_entities_n}, indent=2),
                    encoding="utf-8",
                )
                (out_dir / "structural_metrics.json").write_text(
                    json.dumps({**structural_row, "extracted_entities_n": extracted_entities_n}, indent=2),
                    encoding="utf-8",
                )

                context_rows.append(
                    {
                        "run_id": run_id,
                        "patient_id": pid,
                        "repetition": rep,
                        "run": run_idx,
                        "model": settings.model,
                        "timestamp": ts,
                        "pdf_pages": pages,
                        "character_count": char_count,
                        "estimated_tokens": est_toks,
                        "repetition_factor": rep,
                        "mode": "redundancy",
                    }
                )

            # aggregated per patient + repetition across runs
            df_rep = pd.DataFrame(
                [r for r in semantic_rows if r["patient_id"] == pid and r["repetition"] == rep]
            )
            if len(df_rep) == settings.runs_per_condition:
                agg = {
                    "run_id": run_id,
                    "patient_id": pid,
                    "repetition": rep,
                    "micro_f1_mean": float(df_rep["micro_f1"].mean()),
                    "micro_f1_std": float(df_rep["micro_f1"].std(ddof=0)),
                    "hallucination_mean": float(df_rep["hallucination_count"].mean()),
                    "omission_mean": float(df_rep["omission_count"].mean()),
                    "drift_score_mean": float(df_rep["drift_score"].mean()),
                    "latency_mean_s": float(df_rep["latency_s"].mean()),
                }
                agg_rows.append(agg)

    metrics_dir = run_root / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)

    semantic_csv = metrics_dir / "semantic_metrics.csv"
    semantic_df = pd.DataFrame(semantic_rows)
    semantic_df.to_csv(semantic_csv, index=False)

    structural_csv = metrics_dir / "structural_metrics.csv"
    structural_df = pd.DataFrame(structural_rows)
    structural_df.to_csv(structural_csv, index=False)

    context_csv = metrics_dir / "context_metrics.csv"
    pd.DataFrame(context_rows).to_csv(context_csv, index=False)

    aggregated_csv = metrics_dir / "aggregated_results.csv"
    pd.DataFrame(agg_rows).to_csv(aggregated_csv, index=False)

    plots_dir = run_root / "plots"
    generate_plots(semantic_csv, plots_dir)
    generate_structural_plots(structural_csv, plots_dir)

    # Narrative summary across all patients/runs
    df_sem = semantic_df
    df_str = structural_df

    by_rep_sem = (
        df_sem.groupby("repetition", as_index=False)
        .agg(
            micro_f1_mean=("micro_f1", "mean"),
            micro_f1_std=("micro_f1", "std"),
            hallucination_mean=("hallucination_count", "mean"),
            omission_mean=("omission_count", "mean"),
            drift_mean=("drift_score", "mean"),
        )
        .sort_values("repetition")
    )

    by_rep_str = (
        df_str.groupby("repetition", as_index=False)
        .agg(
            raw_json_valid_rate=("raw_valid_json", "mean"),
            repair_frequency=("repair_needed", "mean"),
            sds_mean=("structural_drift_score", "mean"),
            schema_match_rate=("schema_match", "mean"),
        )
        .sort_values("repetition")
    )

    collapse_flags = detect_early_collapse(by_rep_sem, by_rep_str)
    if collapse_flags:
        (run_root / "collapse_flags.txt").write_text("\n".join(collapse_flags) + "\n", encoding="utf-8")

    f1_1x = float(by_rep_sem.loc[by_rep_sem["repetition"] == 1, "micro_f1_mean"].iloc[0])
    high_rep = int(max(by_rep_sem["repetition"].astype(int).tolist()))
    f1_high = float(by_rep_sem.loc[by_rep_sem["repetition"] == high_rep, "micro_f1_mean"].iloc[0])
    drift_high = float(by_rep_sem.loc[by_rep_sem["repetition"] == high_rep, "drift_mean"].iloc[0])
    sds_1x = float(by_rep_str.loc[by_rep_str["repetition"] == 1, "sds_mean"].iloc[0])
    sds_high = float(by_rep_str.loc[by_rep_str["repetition"] == high_rep, "sds_mean"].iloc[0])
    repair_1x = float(by_rep_str.loc[by_rep_str["repetition"] == 1, "repair_frequency"].iloc[0])
    repair_high = float(by_rep_str.loc[by_rep_str["repetition"] == high_rep, "repair_frequency"].iloc[0])

    improved = f1_high > f1_1x + 1e-6
    degraded = f1_high < f1_1x - 1e-6
    trend_line = "improved" if improved else ("degraded" if degraded else "was similar")

    # Variance metrics + plot
    variance_df = compute_variance_metrics(df_sem, df_str)
    variance_csv = metrics_dir / "variance_metrics.csv"
    variance_df.to_csv(variance_csv, index=False)
    if not variance_df.empty:
        generate_variance_plots(variance_csv, plots_dir)

    summary_md = run_root / "redundancy_drift_summary.md"
    collapse_section = (
        "## Early collapse flags\n- " + "\n- ".join(collapse_flags) + "\n\n" if collapse_flags else ""
    )
    summary_md.write_text(
        "# Redundancy Drift Pilot Summary\n\n"
        f"- run_id: `{run_id}`\n"
        f"- patients: {settings.num_patients}\n"
        f"- repetitions: {list(settings.repetition_levels)}\n"
        f"- runs_per_condition: {settings.runs_per_condition}\n\n"
        "## Key findings (aggregate)\n"
        f"- F1 at 1x: `{f1_1x:.3f}`; F1 at {high_rep}x: `{f1_high:.3f}` (overall {trend_line}).\n"
        f"- Drift at {high_rep}x (vs gold + vs 1x): `{drift_high:.3f}` (higher means less invariant).\n"
        f"- Structural Drift Score (SDS) at 1x: `{sds_1x:.3f}`; SDS at {high_rep}x: `{sds_high:.3f}`.\n"
        f"- Repair frequency at 1x: `{repair_1x:.3f}`; at {high_rep}x: `{repair_high:.3f}`.\n\n"
        "## Structural instability under redundancy\n"
        "- Inspect `plots/repetition_vs_raw_json_validity.png`, `plots/repetition_vs_repair_frequency.png`, and `plots/repetition_vs_structural_drift_score.png`.\n"
        "- Raw outputs: `raw_outputs/`; repaired outputs: `repaired_outputs/`.\n\n"
        f"{collapse_section}"
        "## Semantic drift under redundancy\n"
        "- Inspect `plots/repetition_vs_f1.png`, `plots/repetition_vs_hallucination_rate.png`, and `plots/repetition_vs_omission_rate.png`.\n\n"
        "## Tables\n"
        "- `metrics/semantic_metrics.csv`: precision/recall/F1 + omission/hallucination + drift.\n"
        "- `metrics/structural_metrics.csv`: JSON validity, schema adherence, repair frequency, SDS.\n"
        "- `metrics/context_metrics.csv`: page count, chars, estimated tokens.\n"
        "- `metrics/variance_metrics.csv`: run-to-run variance within condition.\n"
        "- `metrics/aggregated_results.csv`: per-patient semantic aggregates.\n\n"
        "## Interpretation checklist\n"
        "- Redundancy increases structural instability if SDS and repair frequency increase with repetition.\n"
        "- Semantic drift correlates with structural drift if high-SDS conditions also show worse F1 or higher omissions/hallucinations.\n"
        "- Schema adherence degradation shows up as lower schema_match_rate and higher missing/extra keys.\n"
        "- Performance saturated if curves flatten after moderate repetition (e.g., 5x–10x).\n"
        "- Performance degraded at high redundancy if F1 drops or omissions/hallucinations rise at 16x–32x.\n",
        encoding="utf-8",
    )

    logging.info("Done. Wrote %s, %s, %s, %s", semantic_csv, structural_csv, context_csv, variance_csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
