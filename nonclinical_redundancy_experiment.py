"""
Non-Clinical Generalization Experiment
=======================================
Runs the same redundancy + filler-control design on synthetic NEWS ARTICLE
structured extraction.  Schema: {doc_id, events[], persons[], organizations[], locations[]}

This directly tests whether representation drift is specific to clinical NER
or is a general instruction-following failure under semantic load.

Usage:
    python nonclinical_redundancy_experiment.py

Outputs (in data/runs/nonclinical_<timestamp>/):
    metrics/semantic_metrics.csv
    metrics/structural_metrics.csv
    metrics/redundancy_scaling_statistics.csv
    nonclinical_dre_statistics.csv   ← main paper table
    nonclinical_report.md
"""

from __future__ import annotations

import copy
import json
import logging
import os
import random
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from deepinfra_client import DeepInfraClient, DeepInfraAuthError
from analysis import estimate_tokens, write_json
from repair_json import strip_markdown_fences, extract_first_json_object

# ── Experiment configuration ──────────────────────────────────────────────────

REPETITION_LEVELS = (1, 5, 10, 16)
RUNS_PER_CONDITION = 1          # 1 run; generalization check, not main replication
RANDOM_SEED = 1337
MODEL = os.getenv("ATTNDRIFT_MODEL", "meta-llama/Meta-Llama-3.1-8B-Instruct")
TEMPERATURE = 0.0
TOP_P = 1.0
MAX_TOKENS = 512
SEED = 1337
EST_CHARS_PER_TOKEN = 4.0

SCHEMA_KEYS = ["doc_id", "events", "persons", "organizations", "locations"]

SYSTEM_PROMPT = (
    "You are a backend news information extraction service.\n"
    "Return ONLY valid JSON.\n"
    "Do not use markdown. Do not use code fences.\n"
    "Do not explain. Do not add commentary.\n"
    "If information is missing, return empty arrays.\n"
    "Follow the exact schema."
)

EXTRACTION_PROMPT_TEMPLATE = (
    'Extract all information from the news article into this EXACT schema:\n\n'
    '{{\n'
    '"doc_id": "",\n'
    '"events": [],\n'
    '"persons": [],\n'
    '"organizations": [],\n'
    '"locations": []\n'
    '}}\n\n'
    'Rules:\n'
    '* Return ONLY valid JSON\n'
    '* Do not wrap in markdown\n'
    '* Do not add extra keys\n'
    '* Arrays must always exist; if empty use []\n'
    '* Each array element must be a plain string\n\n'
    'Article:\n'
    '{document_text}\n'
)

FILLER_PARAGRAPHS = [
    "Editor's note: this section contains placeholder administrative text for document length control purposes only.",
    "Subscription information: visit our website to manage your newsletter preferences and subscription settings.",
    "Weather update: partly cloudy skies are expected throughout the region with temperatures near seasonal averages.",
    "Sports roundup: local teams competed in weekend fixtures with results available on the sports section of our website.",
    "Market data: commodity indices closed mixed in thin trading ahead of the upcoming holiday weekend.",
    "Traffic advisory: road maintenance is scheduled on several arterial routes; motorists are advised to allow extra travel time.",
]

# ── Synthetic news articles with ground truth ─────────────────────────────────

DOCUMENTS = [
    {
        "doc_id": "news_01",
        "text": """CITY COUNCIL APPROVES NEW TRANSIT EXPANSION PLAN

The Metropolitan City Council voted 7-2 on Tuesday to approve a $2.4 billion transit
expansion plan that will extend the Green Line subway by 12 miles and add three new
stations in the downtown corridor.

Mayor Sandra Liu called the vote a historic milestone. Council member James Okonkwo,
who sponsored the bill, said construction would begin in spring 2027. The project is
funded through a federal infrastructure grant secured by Representative Maria Torres.

The Metropolitan Transit Authority will oversee construction. Critics including
Councilwoman Ellen Park warned of cost overruns. The first new station, at Harbor
Boulevard, is scheduled to open in late 2029.
""",
        "gt": {
            "events": [
                "City Council vote 7-2 approving transit expansion",
                "Green Line subway extension 12 miles adding three stations",
                "Construction beginning spring 2027",
                "Harbor Boulevard station opening late 2029",
            ],
            "persons": ["Sandra Liu", "James Okonkwo", "Maria Torres", "Ellen Park"],
            "organizations": ["Metropolitan City Council", "Metropolitan Transit Authority"],
            "locations": ["downtown corridor", "Harbor Boulevard"],
        },
    },
    {
        "doc_id": "news_02",
        "text": """TECH GIANT ACQUIRES AI STARTUP FOR $800 MILLION

Apex Technologies announced Monday it will acquire NeuralPath Inc., an artificial
intelligence startup based in Austin, Texas, for approximately $800 million in cash
and stock.

The deal, expected to close in Q3 2026 pending regulatory approval by the Federal
Trade Commission, will bring NeuralPath's 140-person team under the Apex umbrella.
NeuralPath CEO David Chen will join Apex as Senior Vice President of AI Products.

Apex CEO Rachel Goldstein said the acquisition accelerates the company's AI roadmap.
NeuralPath, founded in 2021 by Chen and co-founder Priya Anand, raised $95 million
in Series B funding from Sequoia Capital and Andreessen Horowitz before the buyout.
""",
        "gt": {
            "events": [
                "Apex Technologies acquires NeuralPath Inc for $800 million",
                "Deal closing Q3 2026 pending FTC approval",
                "NeuralPath Series B funding $95 million",
            ],
            "persons": ["David Chen", "Rachel Goldstein", "Priya Anand"],
            "organizations": [
                "Apex Technologies", "NeuralPath Inc", "Federal Trade Commission",
                "Sequoia Capital", "Andreessen Horowitz",
            ],
            "locations": ["Austin Texas"],
        },
    },
    {
        "doc_id": "news_03",
        "text": """WILDFIRE FORCES EVACUATIONS IN THREE COUNTIES

A fast-moving wildfire driven by strong winds has forced the evacuation of approximately
15,000 residents across Riverside, San Bernardino, and Orange counties in Southern
California, fire officials said Wednesday.

The Clearwater Fire, as it has been named, has burned more than 8,400 acres since
igniting Tuesday evening near the town of Hemet. Cal Fire spokesperson Andrea Ruiz
said containment stands at 15 percent. Two firefighters from the Hemet Fire Department
were treated for smoke inhalation; no civilian injuries have been reported.

Governor Thomas Walsh declared a state of emergency for the affected counties.
The National Weather Service has issued a Red Flag Warning through Friday evening.
""",
        "gt": {
            "events": [
                "Clearwater Fire burns 8400 acres in Southern California",
                "Evacuation of 15000 residents across three counties",
                "Governor declares state of emergency",
                "Red Flag Warning issued through Friday",
            ],
            "persons": ["Andrea Ruiz", "Thomas Walsh"],
            "organizations": [
                "Cal Fire", "Hemet Fire Department", "National Weather Service",
            ],
            "locations": ["Riverside", "San Bernardino", "Orange counties", "Hemet"],
        },
    },
    {
        "doc_id": "news_04",
        "text": """INTERNATIONAL SUMMIT REACHES CLIMATE ACCORD

Representatives from 47 nations signed the Geneva Climate Accord on Friday, pledging
to reduce carbon emissions by 40 percent by 2035 relative to 2005 levels.

UN Secretary-General Fatima Al-Rashid called it the most significant climate agreement
since the Paris Agreement. The accord was brokered over three days of negotiations led
by Swiss diplomat Klaus Weber and US climate envoy Patricia Osei.

China and India both signed after late-night concessions on technology transfer
provisions. The European Union pledged to front 60 billion euros in green energy
financing for developing nations. The International Energy Agency will monitor
compliance beginning in 2027.
""",
        "gt": {
            "events": [
                "Geneva Climate Accord signed by 47 nations",
                "40 percent carbon emissions reduction pledge by 2035",
                "EU pledges 60 billion euros green energy financing",
                "International Energy Agency monitoring from 2027",
            ],
            "persons": ["Fatima Al-Rashid", "Klaus Weber", "Patricia Osei"],
            "organizations": [
                "United Nations", "European Union", "International Energy Agency",
            ],
            "locations": ["Geneva", "China", "India"],
        },
    },
    {
        "doc_id": "news_05",
        "text": """BANK REPORTS RECORD QUARTERLY EARNINGS

First National Bank posted record quarterly earnings of $3.8 billion on Thursday,
beating analyst expectations by 12 percent, driven by strong performance in its
commercial lending and wealth management divisions.

CEO Michael Park announced the bank will increase its quarterly dividend from $0.45
to $0.52 per share, effective next quarter. CFO Laura Hendricks said loan loss
provisions declined 18 percent year over year.

The results come despite broader economic uncertainty flagged by the Federal Reserve.
First National also announced plans to acquire Community Savings Bank of Ohio for
$240 million in an all-cash deal subject to FDIC approval. The acquisition will add
23 branches across the Midwest.
""",
        "gt": {
            "events": [
                "First National Bank posts $3.8 billion quarterly earnings",
                "Quarterly dividend increase from $0.45 to $0.52",
                "Acquisition of Community Savings Bank of Ohio for $240 million",
            ],
            "persons": ["Michael Park", "Laura Hendricks"],
            "organizations": [
                "First National Bank", "Federal Reserve",
                "Community Savings Bank of Ohio", "FDIC",
            ],
            "locations": ["Ohio", "Midwest"],
        },
    },
    {
        "doc_id": "news_06",
        "text": """CHAMPIONSHIP TEAM CELEBRATES VICTORY PARADE

Hundreds of thousands of fans lined the streets of Boston on Sunday for a victory
parade celebrating the Boston Celtics' NBA championship win over the Golden State
Warriors in six games.

Coach Brian Stevens thanked the city and praised star players Marcus Webb and
Yuki Tanaka, who was named Finals MVP. Team president Dana Alvarez announced plans
for a championship banner ceremony at TD Garden on opening night of next season.

Mayor Carlos Reyes declared Sunday a city holiday. Boston police estimated the crowd
at 1.2 million people. The parade route ran from Copley Square through Downtown
Crossing to City Hall Plaza.
""",
        "gt": {
            "events": [
                "Boston Celtics win NBA championship over Golden State Warriors in six games",
                "Victory parade drawing 1.2 million people",
                "Championship banner ceremony at TD Garden on opening night",
            ],
            "persons": ["Brian Stevens", "Marcus Webb", "Yuki Tanaka", "Dana Alvarez", "Carlos Reyes"],
            "organizations": ["Boston Celtics", "Golden State Warriors"],
            "locations": ["Boston", "Copley Square", "Downtown Crossing", "City Hall Plaza", "TD Garden"],
        },
    },
    {
        "doc_id": "news_07",
        "text": """UNIVERSITY LAUNCHES QUANTUM COMPUTING CENTER

MIT announced Tuesday the opening of the Quantum Innovation Center, a $150 million
facility dedicated to quantum computing research, funded jointly by the Department of
Energy and a consortium of technology companies including IBM and Google.

Center director Professor Aisha Oduya said the facility houses a 512-qubit processor,
currently the largest in any university setting. The center will partner with
Massachusetts General Hospital to explore quantum algorithms for drug discovery.

Senator Paul Kim, who secured federal funding for the project, attended the ribbon
cutting. MIT President Elena Rodriguez said the center positions Massachusetts as
a global leader in quantum technology. The first research cohort of 40 doctoral
students begins in September.
""",
        "gt": {
            "events": [
                "MIT opens Quantum Innovation Center with $150 million funding",
                "512-qubit processor operational at the center",
                "Partnership with Massachusetts General Hospital for drug discovery",
                "First doctoral research cohort beginning in September",
            ],
            "persons": ["Aisha Oduya", "Paul Kim", "Elena Rodriguez"],
            "organizations": [
                "MIT", "Department of Energy", "IBM", "Google",
                "Massachusetts General Hospital",
            ],
            "locations": ["Massachusetts"],
        },
    },
    {
        "doc_id": "news_08",
        "text": """AIRLINE ANNOUNCES NEW TRANSATLANTIC ROUTES

Horizon Airlines announced Wednesday the launch of five new nonstop transatlantic
routes from its Chicago hub beginning in May 2027, including flights to Dublin,
Lisbon, and Athens.

CEO Vanessa Okafor said the expansion reflects strong post-pandemic demand. The
airline will use its new fleet of Airbus A321XLR aircraft for the routes. Horizon
expects to hire 600 additional pilots and 1,400 cabin crew ahead of the expansion.

The announcement coincides with a fare war between Horizon and rival carrier
TransAtlantic Airways, which last month filed a complaint with the Department of
Transportation alleging predatory pricing. DOT spokesperson Renata Cruz said the
agency is reviewing the complaint.
""",
        "gt": {
            "events": [
                "Horizon Airlines launches five new transatlantic routes from Chicago in May 2027",
                "Airline hiring 600 pilots and 1400 cabin crew",
                "TransAtlantic Airways files pricing complaint with DOT",
            ],
            "persons": ["Vanessa Okafor", "Renata Cruz"],
            "organizations": [
                "Horizon Airlines", "TransAtlantic Airways",
                "Department of Transportation", "Airbus",
            ],
            "locations": ["Chicago", "Dublin", "Lisbon", "Athens"],
        },
    },
    {
        "doc_id": "news_09",
        "text": """PHARMACEUTICAL COMPANY WINS FDA APPROVAL FOR NEW DRUG

BioMed Solutions received FDA approval Thursday for Nexavir, a once-daily oral
treatment for moderate-to-severe rheumatoid arthritis, following a Phase 3 trial
that showed a 67 percent reduction in disease activity scores compared to placebo.

BioMed CEO Hiroshi Tanaka said the company plans to launch Nexavir in the US by
Q1 2027 at a list price of $2,800 per month. Chief Medical Officer Dr. Samantha
Ortiz noted the drug showed a favorable safety profile in 2,400 trial participants.

Patient advocacy group Arthritis Foundation praised the approval. Insurance
companies including UnitedHealth expressed concern about the pricing. The drug
will compete with existing biologics including AbbVie's Humira in a market
estimated at $28 billion annually.
""",
        "gt": {
            "events": [
                "FDA approves Nexavir for rheumatoid arthritis",
                "Nexavir US launch planned Q1 2027 at $2800 per month",
                "Phase 3 trial showing 67 percent reduction in disease activity",
            ],
            "persons": ["Hiroshi Tanaka", "Samantha Ortiz"],
            "organizations": [
                "BioMed Solutions", "FDA", "Arthritis Foundation",
                "UnitedHealth", "AbbVie",
            ],
            "locations": [],
        },
    },
    {
        "doc_id": "news_10",
        "text": """CITY SCHOOL DISTRICT ADOPTS AI TUTORING PROGRAM

The Los Angeles Unified School District announced Monday a partnership with
EduAI Corp to deploy an AI tutoring platform across all 900 of its schools,
serving approximately 420,000 students beginning with the 2026-2027 academic year.

Superintendent Angela Morales said the platform will provide personalized reading
and math support. The three-year contract is valued at $78 million, funded through
the state's Education Technology Initiative. EduAI CEO James Fowler said the
system has shown a 22 percent improvement in test scores in pilot districts.

Parent group Families for Public Education expressed data privacy concerns. State
Senator Diane Wong said the legislature would hold hearings on AI in classrooms.
The ACLU of California has requested details on student data handling practices.
""",
        "gt": {
            "events": [
                "LAUSD partners with EduAI Corp for AI tutoring across 900 schools",
                "Platform deployment beginning 2026-2027 academic year",
                "Three-year contract valued at $78 million",
                "Legislature to hold hearings on AI in classrooms",
            ],
            "persons": ["Angela Morales", "James Fowler", "Diane Wong"],
            "organizations": [
                "Los Angeles Unified School District", "EduAI Corp",
                "Families for Public Education", "ACLU of California",
            ],
            "locations": ["Los Angeles"],
        },
    },
]

# ─────────────────────────────────────────────────────────────────────────────
# Custom repair + scoring for the news schema (no dependency on clinical keys)
# ─────────────────────────────────────────────────────────────────────────────

NEWS_REQUIRED_KEYS = ("doc_id", "events", "persons", "organizations", "locations")


def repair_news_json(raw_text: str, *, doc_id: str) -> dict:
    """
    Parse and normalize raw model output to the news schema.
    Returns a dict with all required keys; missing arrays default to [].
    Also returns metadata flags as a second value.
    """
    stripped, fence = strip_markdown_fences(raw_text or "")
    extracted = extract_first_json_object(stripped)
    candidate = extracted if extracted else stripped

    import json as _json
    parsed = {}
    raw_valid = False
    try:
        obj = _json.loads(candidate)
        if isinstance(obj, dict):
            parsed = obj
            raw_valid = True
    except Exception:
        pass

    # Normalize: force required keys, coerce arrays
    out = {"doc_id": doc_id}
    for key in ("events", "persons", "organizations", "locations"):
        val = parsed.get(key, [])
        if val is None:
            val = []
        if not isinstance(val, list):
            val = [val]
        out[key] = val

    missing = [k for k in NEWS_REQUIRED_KEYS if k not in parsed]
    extra = [k for k in parsed if k not in NEWS_REQUIRED_KEYS]
    schema_match = (len(missing) == 0) and (len(extra) == 0)

    # SDS: 1 if schema broken, else 0 (mirroring the clinical SDS definition)
    sds = 0.0 if (raw_valid and schema_match) else 1.0

    return out, {
        "raw_valid_json": int(raw_valid),
        "schema_match": int(schema_match),
        "sds": sds,
        "missing_keys_count": len(missing),
        "extra_keys_count": len(extra),
    }


def setup_logging(log_path: Path):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8"), logging.StreamHandler()],
    )


def normalize_nonclinical(obj: dict, doc_id: str) -> dict:
    """Map nonclinical schema to the same format normalize_extraction expects."""
    # Reuse evaluator's set-based comparison by treating each field as a flat list
    out = {"patient_id": doc_id}
    for key in ("events", "persons", "organizations", "locations"):
        raw = obj.get(key) or []
        out[key] = sorted({str(v).strip().lower() for v in raw if v})
    return out


def score_nonclinical(pred: dict, gold: dict) -> dict:
    """Compute micro F1, FP, FN across all fields."""
    pred_set: set[str] = set()
    gold_set: set[str] = set()
    for key in ("events", "persons", "organizations", "locations"):
        pred_set |= set(pred.get(key) or [])
        gold_set |= set(gold.get(key) or [])

    tp = len(pred_set & gold_set)
    fp = len(pred_set - gold_set)
    fn = len(gold_set - pred_set)
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    return {"micro_f1": f1, "micro_precision": prec, "micro_recall": rec,
            "fp_count": fp, "fn_count": fn, "tp_count": tp}


def build_filler_text(base_text: str, target_chars: int, rng: random.Random) -> str:
    text = base_text.rstrip() + "\n"
    while len(text) < target_chars:
        text += "\n" + rng.choice(FILLER_PARAGRAPHS) + "\n"
    return text.strip() + "\n"


def run_condition(
    *,
    client,
    documents: list[dict],
    condition: str,          # "redundancy" | "filler"
    run_root: Path,
    rng: random.Random,
) -> list[dict]:
    """Run all patients × reps × runs for one condition. Returns metric rows."""
    rows = []
    for doc in documents:
        doc_id = doc["doc_id"]
        base_text = doc["text"].strip() + "\n"
        gold_norm = normalize_nonclinical(
            {"doc_id": doc_id, **doc["gt"]}, doc_id
        )

        for rep in REPETITION_LEVELS:
            if condition == "redundancy":
                doc_text = (base_text * rep).strip() + "\n"
            else:
                target_chars = len(base_text) * rep
                doc_text = build_filler_text(base_text, target_chars, rng)

            for run_idx in range(1, RUNS_PER_CONDITION + 1):
                out_dir = (
                    run_root / "outputs" / doc_id
                    / condition / f"rep_{rep}x" / f"run_{run_idx:02d}"
                )
                out_dir.mkdir(parents=True, exist_ok=True)

                prompt = EXTRACTION_PROMPT_TEMPLATE.format(document_text=doc_text)

                result = client.chat_completions(
                    user_prompt=EXTRACTION_PROMPT_TEMPLATE,
                    document_text=doc_text,
                )

                if not result.ok or not result.content_text:
                    logging.error("API error doc=%s rep=%s run=%s", doc_id, rep, run_idx)
                    continue

                raw_text = result.content_text
                (out_dir / "raw_response.txt").write_text(raw_text, encoding="utf-8")

                repaired, meta = repair_news_json(raw_text, doc_id=doc_id)

                pred_norm = normalize_nonclinical(repaired, doc_id)
                scores = score_nonclinical(pred_norm, gold_norm)

                rows.append({
                    "doc_id": doc_id,
                    "condition": condition,
                    "repetition": rep,
                    "run": run_idx,
                    "micro_f1": scores["micro_f1"],
                    "fp_count": scores["fp_count"],
                    "fn_count": scores["fn_count"],
                    "tp_count": scores["tp_count"],
                    "raw_valid_json": meta["raw_valid_json"],
                    "sds": meta["sds"],
                    "char_count": len(doc_text),
                    "est_tokens": estimate_tokens(len(doc_text), EST_CHARS_PER_TOKEN),
                })

                logging.info(
                    "[%s] %s rep=%sx run=%s F1=%.3f valid=%s sds=%.2f",
                    condition, doc_id, rep, run_idx,
                    scores["micro_f1"], meta["raw_valid_json"], meta["sds"],
                )

    return rows


def compute_dre(df: pd.DataFrame) -> pd.DataFrame:
    """DRE = mean(drop_red) - mean(drop_filler), paired by doc_id."""
    # Compute per-doc F1 at 1× baseline for each condition
    base_red = (
        df[(df.condition == "redundancy") & (df.repetition == 1)]
        .groupby("doc_id")["micro_f1"].mean()
        .rename("f1_1x_red")
    )
    base_fill = (
        df[(df.condition == "filler") & (df.repetition == 1)]
        .groupby("doc_id")["micro_f1"].mean()
        .rename("f1_1x_fill")
    )

    rows = []
    for rep in sorted(df.repetition.unique()):
        if rep == 1:
            continue
        red_r = (
            df[(df.condition == "redundancy") & (df.repetition == rep)]
            .groupby("doc_id")["micro_f1"].mean()
        )
        fill_r = (
            df[(df.condition == "filler") & (df.repetition == rep)]
            .groupby("doc_id")["micro_f1"].mean()
        )
        paired = pd.concat([base_red, base_fill, red_r.rename("f1_r_red"),
                             fill_r.rename("f1_r_fill")], axis=1).dropna()
        paired["drop_red"] = paired["f1_1x_red"] - paired["f1_r_red"]
        paired["drop_fill"] = paired["f1_1x_fill"] - paired["f1_r_fill"]
        paired["dre"] = paired["drop_red"] - paired["drop_fill"]

        rows.append({
            "repetition": rep,
            "mean_dre": paired["dre"].mean(),
            "mean_drop_red": paired["drop_red"].mean(),
            "mean_drop_fill": paired["drop_fill"].mean(),
            "f1_red": paired["f1_r_red"].mean(),
            "f1_fill": paired["f1_r_fill"].mean(),
            "n": len(paired),
        })

    return pd.DataFrame(rows)


def main():
    load_dotenv(Path(__file__).resolve().parent / ".env")

    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_root = Path(__file__).resolve().parent / "data" / "runs" / f"nonclinical_{run_id}"
    run_root.mkdir(parents=True, exist_ok=True)
    setup_logging(run_root / "run.log")
    logging.info("Non-clinical generalization experiment run_id=%s", run_id)

    rng = random.Random(RANDOM_SEED)

    # Build a minimal settings-like object for DeepInfraClient (duck-typed)
    class _Settings:
        deepinfra_base_url = "https://api.deepinfra.com/v1/openai"
        model = MODEL
        temperature = TEMPERATURE
        top_p = TOP_P
        max_tokens = MAX_TOKENS
        seed = SEED
        request_timeout_s = 120
        max_retries = 5
        initial_backoff_s = 1.0
        system_prompt = SYSTEM_PROMPT
        # repair_and_analyze needs patient_id; schema keys for field-level checks
        fixed_schema = {"doc_id": "", "events": [], "persons": [],
                        "organizations": [], "locations": []}

    settings = _Settings()

    try:
        client = DeepInfraClient(settings)
    except DeepInfraAuthError as e:
        logging.error("Auth error: %s — set DEEPINFRA_API_KEY in .env", e)
        return 1

    all_rows = []

    logging.info("Running REDUNDANCY condition (%d docs × %d reps × %d runs)…",
                 len(DOCUMENTS), len(REPETITION_LEVELS), RUNS_PER_CONDITION)
    red_rows = run_condition(
        client=client, documents=DOCUMENTS,
        condition="redundancy", run_root=run_root, rng=rng,
    )
    all_rows.extend(red_rows)

    logging.info("Running FILLER condition…")
    fill_rows = run_condition(
        client=client, documents=DOCUMENTS,
        condition="filler", run_root=run_root, rng=rng,
    )
    all_rows.extend(fill_rows)

    df = pd.DataFrame(all_rows)
    metrics_dir = run_root / "metrics"
    metrics_dir.mkdir(exist_ok=True)
    df.to_csv(metrics_dir / "all_metrics.csv", index=False)

    # ── Aggregate scaling table ───────────────────────────────────────────────
    scaling = (
        df[df.condition == "redundancy"]
        .groupby("repetition")
        .agg(
            f1_mean=("micro_f1", "mean"),
            f1_std=("micro_f1", "std"),
            fp_mean=("fp_count", "mean"),
            fn_mean=("fn_count", "mean"),
            json_valid_rate=("raw_valid_json", "mean"),
            sds_mean=("sds", "mean"),
        )
        .reset_index()
    )
    scaling.to_csv(metrics_dir / "redundancy_scaling_statistics.csv", index=False)

    # ── DRE table ─────────────────────────────────────────────────────────────
    dre_df = compute_dre(df)
    dre_path = run_root / "nonclinical_dre_statistics.csv"
    dre_df.to_csv(dre_path, index=False)

    # ── Entity-type breakdown (events vs persons vs organizations vs locations) ─
    type_rows = []
    for doc in DOCUMENTS:
        doc_id = doc["doc_id"]
        gold = doc["gt"]
        for rep in REPETITION_LEVELS:
            red_outs = df[(df.doc_id == doc_id) & (df.condition == "redundancy")
                          & (df.repetition == rep)]
            if red_outs.empty:
                continue
            # Re-read repaired output for entity-type breakdown
            out_dir = (run_root / "outputs" / doc_id / "redundancy"
                       / f"rep_{rep}x" / "run_01")
            raw_path = out_dir / "raw_response.txt"
            if not raw_path.exists():
                continue
            pred, _ = repair_news_json(raw_path.read_text(encoding="utf-8"),
                                       doc_id=doc_id)
            for field in ("events", "persons", "organizations", "locations"):
                pred_set = {str(v).strip().lower() for v in (pred.get(field) or [])}
                gold_set = {str(v).strip().lower() for v in (gold.get(field) or [])}
                tp = len(pred_set & gold_set)
                fp = len(pred_set - gold_set)
                fn = len(gold_set - pred_set)
                type_rows.append({
                    "doc_id": doc_id, "repetition": rep, "field": field,
                    "tp": tp, "fp": fp, "fn": fn,
                    "precision": tp / (tp + fp) if (tp + fp) > 0 else 0.0,
                    "recall": tp / (tp + fn) if (tp + fn) > 0 else 0.0,
                })
    if type_rows:
        type_df = pd.DataFrame(type_rows)
        # Aggregate by field and repetition
        type_agg = (
            type_df.groupby(["field", "repetition"])
            .agg(tp=("tp", "sum"), fp=("fp", "sum"), fn=("fn", "sum"))
            .reset_index()
        )
        type_agg["precision"] = type_agg["tp"] / (type_agg["tp"] + type_agg["fp"]).clip(lower=1)
        type_agg["recall"] = type_agg["tp"] / (type_agg["tp"] + type_agg["fn"]).clip(lower=1)
        type_agg.to_csv(metrics_dir / "entity_type_breakdown.csv", index=False)

    # ── Human-readable report ─────────────────────────────────────────────────
    f1_1x = float(scaling.loc[scaling.repetition == 1, "f1_mean"].iloc[0])
    f1_16x = float(scaling.loc[scaling.repetition == 16, "f1_mean"].iloc[0]) \
        if 16 in scaling.repetition.values else float("nan")
    valid_1x = float(scaling.loc[scaling.repetition == 1, "json_valid_rate"].iloc[0])
    valid_16x = float(scaling.loc[scaling.repetition == 16, "json_valid_rate"].iloc[0]) \
        if 16 in scaling.repetition.values else float("nan")
    sds_max = float(scaling["sds_mean"].max())

    report = run_root / "nonclinical_report.md"
    report.write_text(
        f"# Non-Clinical Generalization Experiment Report\n\n"
        f"- run_id: `{run_id}`\n"
        f"- model: `{MODEL}`\n"
        f"- task: News article structured extraction\n"
        f"- schema: `{{doc_id, events[], persons[], organizations[], locations[]}}`\n"
        f"- documents: {len(DOCUMENTS)}\n"
        f"- repetitions: {list(REPETITION_LEVELS)}\n"
        f"- runs_per_condition: {RUNS_PER_CONDITION}\n\n"
        f"## Key findings\n\n"
        f"- F1 at 1×: `{f1_1x:.3f}` | F1 at 16×: `{f1_16x:.3f}`\n"
        f"- JSON validity at 1×: `{valid_1x:.3f}` | at 16×: `{valid_16x:.3f}`\n"
        f"- Max SDS across all conditions: `{sds_max:.3f}` (0 = no structural drift)\n\n"
        f"## DRE summary\n\n"
        f"```\n{dre_df.to_string(index=False)}\n```\n\n"
        f"## Redundancy scaling\n\n"
        f"```\n{scaling.to_string(index=False)}\n```\n\n"
        f"## Interpretation\n\n"
        f"- Positive DRE at midrange repetitions = representation drift present in news domain\n"
        f"- JSON validity and SDS = how close to 1.00 and 0.00 throughout\n"
        f"- Entity-type breakdown: see metrics/entity_type_breakdown.csv\n"
        f"  (expect 'events' to collapse like 'medications' — rich nested-dict alternatives)\n",
        encoding="utf-8",
    )

    print("\n" + "=" * 60)
    print("NON-CLINICAL EXPERIMENT COMPLETE")
    print("=" * 60)
    print(f"Run root:    {run_root}")
    print(f"Report:      {report}")
    print(f"DRE table:   {dre_path}")
    print()
    print("REDUNDANCY SCALING:")
    print(scaling[["repetition", "f1_mean", "json_valid_rate", "sds_mean"]].to_string(index=False))
    print()
    print("DRE TABLE:")
    print(dre_df.to_string(index=False))
    print("=" * 60)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
