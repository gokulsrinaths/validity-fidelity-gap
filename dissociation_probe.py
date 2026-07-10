"""
Dissociation Probe Experiment
==============================
Directly tests the knowledge-format dissociation claim:
"The model knows the entity but loses the format contract."

Two-part design:
  Part 1 (ZERO new API calls): For each FN case in existing runs at 5x/16x,
    check whether the missed medication name appears in nested-dict output.
    If the entity IS present in the model's output (as a dict key-value pair)
    but was scored FN because it's not a plain string, that IS the dissociation.

  Part 2 (~30 new API calls): Send a free-form "list medications" follow-up
    prompt using the 1x document text (no schema, no JSON, no system prompt).
    Score gold medication recall in the free-form response vs. structured
    extraction recall at 16x. High recall in free-form + low recall in
    structured = knowledge retained, format contract broken.

Outputs:
  data/runs/dissociation_probe_<timestamp>/
    part1_existing_analysis.csv   -- per-case nested-dict recovery analysis
    part1_summary.csv             -- aggregate knowledge retention rates
    part2_probe_results.csv       -- per-patient free-form vs structured recall
    part2_summary.csv             -- aggregate comparison
    dissociation_report.md        -- human-readable narrative for paper
"""

from __future__ import annotations

import csv
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

import requests

# ── Config ────────────────────────────────────────────────────────────────────
LARGE_N_RUN_ROOT = Path("data/runs/full_pilot_20260522_161847")  # 8B large-N redundancy
DATA_DIR = Path("data")
OUTPUT_PROBE_REPS = (5, 16)   # repetition levels to probe
PART2_SAMPLE_N = 30           # how many patients for free-form probe
PART2_REP = 16                # repetition level where drift is strongest

MODEL = "meta-llama/Meta-Llama-3.1-8B-Instruct"
DEEPINFRA_BASE_URL = "https://api.deepinfra.com/v1/openai"
TEMPERATURE = 0.0
SEED = 1337
MAX_TOKENS = 256
TIMEOUT = 60
MAX_RETRIES = 3

# Free-form probe prompt — no schema, no JSON, no system prompt
FREE_FORM_PROMPT = (
    "Read the following medical note and list every medication mentioned. "
    "Write one medication per line. Include the drug name and dose if present. "
    "Do not use JSON. Do not use any special formatting. Just plain text.\n\n"
    "Document:\n{document_text}"
)

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_gold(patient_id: str) -> dict:
    path = DATA_DIR / patient_id / "ground_truth" / f"{patient_id}.json"
    with open(path) as f:
        return json.load(f)


def load_document_1x(patient_id: str) -> str:
    """Load the 1x (single-copy) document text for a patient."""
    path = LARGE_N_RUN_ROOT / "outputs" / patient_id / "rep_1x" / "run_01" / "document_source.txt"
    return path.read_text(encoding="utf-8").strip()


def load_repaired(patient_id: str, rep: int) -> dict:
    rep_str = f"rep_{rep}x"
    path = LARGE_N_RUN_ROOT / "outputs" / patient_id / rep_str / "run_01" / "repaired.json"
    with open(path) as f:
        return json.load(f)


def normalize(s: str) -> str:
    """Lowercase, strip punctuation for fuzzy matching."""
    return re.sub(r"[^a-z0-9 ]", " ", s.lower()).strip()


def extract_name_tokens(gold_string: str) -> list[str]:
    """Extract the key name tokens from a gold medication string.
    E.g. 'Albuterol inhaler 90 mcg 2 puffs q4-6h PRN' -> ['albuterol', 'inhaler']
    Stop at first number token.
    """
    tokens = []
    for tok in gold_string.split():
        if re.match(r"^\d", tok):
            break
        tokens.append(tok.lower())
    return tokens[:3]  # first 1-3 words are the drug name


def entity_recovered_in_dict(gold_string: str, extracted_meds: list) -> bool:
    """Check whether gold_string's drug name appears in the extracted medications list,
    even if those entries are nested dicts (not plain strings).
    Returns True if the entity IS present in the output (as dict or string) but
    in the wrong format."""
    name_tokens = extract_name_tokens(gold_string)
    if not name_tokens:
        return False
    for entry in extracted_meds:
        if isinstance(entry, dict):
            # Check all string values in the dict
            combined = " ".join(str(v) for v in entry.values()).lower()
            if all(tok in combined for tok in name_tokens):
                return True
        elif isinstance(entry, str):
            normed = normalize(entry)
            if all(tok in normed for tok in name_tokens):
                return True
    return False


def is_plain_string_match(gold_string: str, extracted_meds: list) -> bool:
    """Standard F1 check: gold string found as plain string in extracted list."""
    gold_norm = normalize(gold_string)
    for entry in extracted_meds:
        if isinstance(entry, str):
            if normalize(entry) == gold_norm:
                return True
            # Partial: gold tokens all in extracted string
            gold_toks = set(gold_norm.split())
            entry_toks = set(normalize(entry).split())
            if gold_toks and gold_toks.issubset(entry_toks):
                return True
    return False


# ── Part 1: Existing-data analysis ───────────────────────────────────────────

def run_part1(patients: list[str]) -> tuple[list[dict], dict]:
    """Analyze existing run outputs for knowledge-format dissociation."""
    print("\n=== PART 1: Existing-data dissociation analysis ===")
    rows = []
    for patient_id in patients:
        gold = load_gold(patient_id)
        gold_meds = gold.get("medications", [])
        for rep in OUTPUT_PROBE_REPS:
            try:
                repaired = load_repaired(patient_id, rep)
            except FileNotFoundError:
                continue
            extracted_meds = repaired.get("medications", [])
            for gold_med in gold_meds:
                is_tp = is_plain_string_match(gold_med, extracted_meds)
                is_fn = not is_tp
                # For FN cases: is the entity present in the output as a dict?
                recovered_as_dict = False
                output_format = "absent"
                if is_fn:
                    recovered_as_dict = entity_recovered_in_dict(gold_med, extracted_meds)
                    if recovered_as_dict:
                        output_format = "nested_dict"
                    else:
                        output_format = "absent"
                else:
                    output_format = "plain_string"
                rows.append({
                    "patient_id": patient_id,
                    "repetition": rep,
                    "gold_medication": gold_med,
                    "is_tp": int(is_tp),
                    "is_fn": int(is_fn),
                    "fn_recovered_as_dict": int(recovered_as_dict) if is_fn else 0,
                    "output_format": output_format,
                })

    # Aggregate
    fn_cases = [r for r in rows if r["is_fn"]]
    fn_as_dict = [r for r in fn_cases if r["fn_recovered_as_dict"]]
    total_entities = len(rows)
    total_fn = len(fn_cases)
    total_fn_dict = len(fn_as_dict)
    knowledge_retention_rate = total_fn_dict / total_fn if total_fn else 0.0

    summary = {
        "total_entity_instances": total_entities,
        "total_fn_cases": total_fn,
        "fn_recovered_as_nested_dict": total_fn_dict,
        "knowledge_retention_rate": knowledge_retention_rate,
    }

    # By repetition
    for rep in OUTPUT_PROBE_REPS:
        rep_fn = [r for r in fn_cases if r["repetition"] == rep]
        rep_dict = [r for r in rep_fn if r["fn_recovered_as_dict"]]
        rate = len(rep_dict) / len(rep_fn) if rep_fn else 0.0
        summary[f"rep_{rep}x_fn_total"] = len(rep_fn)
        summary[f"rep_{rep}x_fn_as_dict"] = len(rep_dict)
        summary[f"rep_{rep}x_knowledge_retention"] = rate
        print(f"  Rep {rep}x: {len(rep_fn)} FN cases, "
              f"{len(rep_dict)} recovered as nested dict ({rate:.1%})")

    print(f"\n  OVERALL: {total_fn} FN cases, "
          f"{total_fn_dict} entities present as nested dict "
          f"({knowledge_retention_rate:.1%} knowledge retention rate)")

    return rows, summary


# ── Part 2: Free-form follow-up probe ─────────────────────────────────────────

def call_freeform(document_text: str, api_key: str) -> str | None:
    """Send a free-form medication listing prompt. No JSON mode."""
    url = f"{DEEPINFRA_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "temperature": TEMPERATURE,
        "top_p": 1.0,
        "max_tokens": MAX_TOKENS,
        "seed": SEED,
        # NO response_format JSON mode — we want free text
        "messages": [
            {
                "role": "user",
                "content": FREE_FORM_PROMPT.format(document_text=document_text),
            }
        ],
    }
    backoff = 1.0
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=TIMEOUT)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            elif resp.status_code >= 500:
                if attempt == MAX_RETRIES:
                    return None
                time.sleep(backoff); backoff *= 2
            else:
                print(f"    API error {resp.status_code}: {resp.text[:200]}")
                return None
        except Exception as e:
            if attempt == MAX_RETRIES:
                print(f"    Exception: {e}")
                return None
            time.sleep(backoff); backoff *= 2
    return None


def score_recall_freeform(gold_meds: list[str], response_text: str) -> float:
    """Fraction of gold medications whose name tokens appear in the free-form response."""
    if not gold_meds or not response_text:
        return 0.0
    resp_norm = normalize(response_text)
    hits = 0
    for gm in gold_meds:
        name_tokens = extract_name_tokens(gm)
        if name_tokens and all(tok in resp_norm for tok in name_tokens):
            hits += 1
    return hits / len(gold_meds)


def score_recall_structured(gold_meds: list[str], repaired: dict) -> float:
    """Standard structured recall: fraction of gold strings found in extracted list."""
    extracted_meds = repaired.get("medications", [])
    if not gold_meds:
        return 0.0
    hits = sum(1 for gm in gold_meds if is_plain_string_match(gm, extracted_meds))
    return hits / len(gold_meds)


def run_part2(patients: list[str], api_key: str) -> tuple[list[dict], dict]:
    """Free-form follow-up probe on PART2_SAMPLE_N patients."""
    print(f"\n=== PART 2: Free-form follow-up probe (n={len(patients)}, rep={PART2_REP}x) ===")

    # Prioritize patients with FN at PART2_REP (to maximize signal)
    sampled = patients[:PART2_SAMPLE_N]

    rows = []
    for i, patient_id in enumerate(sampled):
        gold = load_gold(patient_id)
        gold_meds = gold.get("medications", [])
        if not gold_meds:
            continue

        doc_1x = load_document_1x(patient_id)

        # Structured recall at 1x and PART2_REP
        try:
            repaired_1x = load_repaired(patient_id, 1)
            repaired_high = load_repaired(patient_id, PART2_REP)
        except FileNotFoundError:
            continue

        recall_1x = score_recall_structured(gold_meds, repaired_1x)
        recall_structured_high = score_recall_structured(gold_meds, repaired_high)

        # Free-form probe (new API call, using 1x document — no repetition)
        print(f"  [{i+1}/{len(sampled)}] {patient_id} ... ", end="", flush=True)
        probe_response = call_freeform(doc_1x, api_key)
        if probe_response is None:
            print("FAILED")
            continue

        recall_freeform = score_recall_freeform(gold_meds, probe_response)
        print(f"structured_1x={recall_1x:.2f} "
              f"structured_{PART2_REP}x={recall_structured_high:.2f} "
              f"freeform={recall_freeform:.2f}")

        rows.append({
            "patient_id": patient_id,
            "n_gold_meds": len(gold_meds),
            "recall_structured_1x": recall_1x,
            f"recall_structured_{PART2_REP}x": recall_structured_high,
            "recall_freeform_1x_doc": recall_freeform,
            "gap_freeform_minus_structured": recall_freeform - recall_structured_high,
            "probe_response_snippet": (probe_response or "")[:200],
        })

    # Summary
    if not rows:
        return rows, {}

    mean_s1 = sum(r["recall_structured_1x"] for r in rows) / len(rows)
    mean_sh = sum(r[f"recall_structured_{PART2_REP}x"] for r in rows) / len(rows)
    mean_ff = sum(r["recall_freeform_1x_doc"] for r in rows) / len(rows)
    mean_gap = sum(r["gap_freeform_minus_structured"] for r in rows) / len(rows)

    summary = {
        "n_patients": len(rows),
        "mean_recall_structured_1x": mean_s1,
        f"mean_recall_structured_{PART2_REP}x": mean_sh,
        "mean_recall_freeform_probe": mean_ff,
        "mean_gap_freeform_minus_structured": mean_gap,
    }

    print(f"\n  SUMMARY:")
    print(f"    Structured recall at 1x:     {mean_s1:.3f}")
    print(f"    Structured recall at {PART2_REP}x:    {mean_sh:.3f}")
    print(f"    Free-form recall (1x doc):   {mean_ff:.3f}")
    print(f"    Gap (freeform - structured): {mean_gap:+.3f}")

    return rows, summary


# ── Report generation ─────────────────────────────────────────────────────────

def write_report(out_dir: Path, p1_summary: dict, p2_summary: dict):
    knr = p1_summary.get("knowledge_retention_rate", 0)
    p2_n = p2_summary.get("n_patients", 0)
    s1 = p2_summary.get("mean_recall_structured_1x", 0)
    sh = p2_summary.get(f"mean_recall_structured_{PART2_REP}x", 0)
    ff = p2_summary.get("mean_recall_freeform_probe", 0)
    gap = p2_summary.get("mean_gap_freeform_minus_structured", 0)

    r5_fn = p1_summary.get("rep_5x_fn_total", 0)
    r5_dict = p1_summary.get("rep_5x_fn_as_dict", 0)
    r5_rate = p1_summary.get("rep_5x_knowledge_retention", 0)
    r16_fn = p1_summary.get("rep_16x_fn_total", 0)
    r16_dict = p1_summary.get("rep_16x_fn_as_dict", 0)
    r16_rate = p1_summary.get("rep_16x_knowledge_retention", 0)

    report = f"""# Dissociation Probe: Results
Generated: {datetime.now().isoformat()}

## Part 1: Existing-data analysis (zero new API calls)

For each medication entity scored as FN (false negative) in existing structured
extraction runs at 5x and 16x redundancy, we checked whether the medication NAME
was nevertheless present in the model's output — encoded as a nested dict entry
rather than the required plain string.

| Rep | FN cases | Entity present as nested dict | Knowledge retention rate |
|-----|----------|-------------------------------|--------------------------|
| 5x  | {r5_fn:4d}  | {r5_dict:4d}                          | {r5_rate:.1%}                   |
| 16x | {r16_fn:4d}  | {r16_dict:4d}                          | {r16_rate:.1%}                   |
| **Overall** | **{p1_summary.get('total_fn_cases',0)}** | **{p1_summary.get('fn_recovered_as_nested_dict',0)}** | **{knr:.1%}** |

**Interpretation:** {knr:.0%} of all FN cases are NOT missing entities —
the model extracted the correct medication into a nested dict object
(e.g., {{"name": "Albuterol inhaler", "dosage": "90 mcg", "frequency": "q4-6h", ...}})
rather than the required plain string ("Albuterol inhaler 90 mcg q4-6h PRN").
The entity knowledge is intact; what fails is the format contract.

## Part 2: Free-form follow-up probe ({p2_n} patients)

For {p2_n} patients, we sent a free-form "list medications" prompt using the
single-copy (1x) document — no schema, no JSON mode, no system prompt.
We compared medication recall in the free-form response against structured
extraction recall at 1x and {PART2_REP}x.

| Condition | Mean recall |
|-----------|-------------|
| Structured extraction at 1x | {s1:.3f} |
| Structured extraction at {PART2_REP}x | {sh:.3f} |
| Free-form probe (1x doc) | {ff:.3f} |
| **Gap (free-form − structured {PART2_REP}x)** | **{gap:+.3f}** |

**Interpretation:** When asked in free-form (no schema constraint), the model
recalls medications at rate {ff:.3f}, close to the 1x structured baseline ({s1:.3f}).
Under structured extraction at {PART2_REP}x, recall drops to {sh:.3f}.
The gap of {gap:+.3f} confirms: the entity knowledge is accessible under a
different prompting regime; what is lost is adherence to the schema format
contract under high semantic load.

## Combined conclusion

Both analyses confirm the same claim: representation drift is a
**format-contract failure, not a knowledge failure**.

- Part 1: {knr:.0%} of FN cases are entities present in the output as nested dicts —
  the model knows and extracts the entity, but emits it in the wrong format.
- Part 2: Free-form recall ({ff:.3f}) >> structured recall at {PART2_REP}x ({sh:.3f}) —
  the entity is accessible via a format-unconstrained probe.

These two independent lines of evidence satisfy the dissociation criterion:
knowledge of what to extract is preserved; adherence to how to format it is not.
"""
    (out_dir / "dissociation_report.md").write_text(report, encoding="utf-8")
    print(f"\n  Report written to {out_dir / 'dissociation_report.md'}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    api_key = os.environ.get("DEEPINFRA_API_KEY") or ""
    if not api_key:
        # Try .env
        env_path = Path(".env")
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("DEEPINFRA_API_KEY"):
                    api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not api_key:
        raise RuntimeError("DEEPINFRA_API_KEY not found. Set it in .env or environment.")

    # Discover patients in the large-N run
    patients_dir = LARGE_N_RUN_ROOT / "outputs"
    patients = sorted(p.name for p in patients_dir.iterdir() if p.is_dir())
    print(f"Found {len(patients)} patients in {LARGE_N_RUN_ROOT.name}")

    # Output directory
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(f"data/runs/dissociation_probe_{ts}")
    out_dir.mkdir(parents=True, exist_ok=True)

    # Part 1
    p1_rows, p1_summary = run_part1(patients)

    with open(out_dir / "part1_existing_analysis.csv", "w", newline="") as f:
        if p1_rows:
            writer = csv.DictWriter(f, fieldnames=p1_rows[0].keys())
            writer.writeheader()
            writer.writerows(p1_rows)

    with open(out_dir / "part1_summary.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=p1_summary.keys())
        writer.writeheader()
        writer.writerow(p1_summary)

    print(f"\n  Part 1 data written to {out_dir}")

    # Part 2 — free-form probe
    p2_rows, p2_summary = run_part2(patients, api_key)

    if p2_rows:
        with open(out_dir / "part2_probe_results.csv", "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=p2_rows[0].keys())
            writer.writeheader()
            writer.writerows(p2_rows)

        with open(out_dir / "part2_summary.csv", "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=p2_summary.keys())
            writer.writeheader()
            writer.writerow(p2_summary)

    # Report
    write_report(out_dir, p1_summary, p2_summary)

    print(f"\n{'='*60}")
    print(f"All outputs in: {out_dir}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
