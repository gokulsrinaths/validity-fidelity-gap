# The Validity–Fidelity Gap: Code and Data

Anonymized artifact repository for the ARR submission *"The Validity–Fidelity Gap: A Controlled Study of Representation Drift in Structured Extraction Under Redundant Contexts."*

This repository contains the **complete experimental pipeline, all synthetic benchmark data, every raw model output, and all analysis scripts** used in the paper. All headline numbers can be recomputed from the logged artifacts without any API calls; rerunning inference requires only a DeepInfra API key.

## Contents

| Path | Description |
|---|---|
| `config.py` | All fixed experimental settings: prompts, schema, decoding parameters (temperature 0, seed 1337), repetition levels (1–32×), model IDs |
| `evaluator.py` | Formal metric implementations: JSON validity, schema match, repair rate, Structural Drift Score (SDS), micro-P/R/F1, strict/soft/canonical normalization |
| `run_pilot.py`, `control_experiment.py` | Main redundancy-scaling experiment and length-matched filler control |
| `cross_model_validation.py` + `run_*.bat` | LLaMA-3.1-70B and Qwen2.5-72B validation and midrange replications |
| `dissociation_probe.py` | Knowledge–format dissociation probe (nested-dict FN recovery + free-form recall) |
| `nonclinical_redundancy_experiment.py` | Non-clinical (news) generalization experiment |
| `shuffled_redundancy_control.py`, `section_redundancy_experiment.py`, `paraphrased_redundancy_experiment.py`, `prompt_robustness_experiment.py`, `position_sensitivity_analysis.py` | Ablations and robustness experiments |
| `data/patient_XX/` | Synthetic clinical notes (text + PDFs at each repetition level) and fixed-schema ground truth |
| `data/runs/` | **Every experimental run in the paper**: per-call prompts, raw model responses, usage/token accounting, repaired JSON, per-call metrics |
| `paper_artifacts/` | Consolidated tables/figures: per-patient and per-repetition DRE, cross-model DRE, error taxonomy, position sensitivity, token-matching audits, reproducibility manifest |

## Key artifacts for reviewers

- **Main pilot (180 calls, 8B):** `data/runs/full_pilot_20260520_192127/` — micro-F1 0.499 (1×) → 0.259 (32×) with JSON validity 1.00 throughout
- **Filler control + DRE:** `data/runs/full_pilot_control_20260520_235546/` including `token_matching_audit_true_tokens.md` (true `usage.prompt_tokens` audit) and `filler_quality_audit.md`
- **Dissociation probe:** `data/runs/dissociation_probe_20260525_233529/dissociation_report.md` — 100% of FN-scored medication entities present as nested-dict structures; free-form recall 0.967 vs 0.400 structured at 16×
- **Cross-model:** `paper_artifacts/cross_model_DRE_combined.csv`, `paper_artifacts/model_comparison_DRE.png`
- **Reproducibility manifest:** `paper_artifacts/reproducibility_manifest.json`

## Metric definitions (implemented in `evaluator.py`)

- **JSON validity** — `safe_json_loads`: raw response parses as JSON after extracting the outermost object (1/0 per call).
- **Repair rate** — fraction of calls requiring `repair_json.py` normalization before schema comparison.
- **Structural Drift Score (SDS)** — `structural_drift_score`: per-call weighted penalty score: +2.0 malformed JSON, +0.5 per missing schema key, +0.25 per extra key, +0.5 schema mismatch, +0.25 markdown fence present (0 = fully conformant).
- **Semantic micro-P/R/F1** — set-based exact match over normalized entity strings against ground truth (`prf1`), with strict / soft-synonym / canonical normalization variants reported.
- **Omissions / hallucinations** — per-call false negatives / false positives against ground truth.

## Reproducing

1. `cp .env.example .env` and add a DeepInfra API key.
2. `pip install -r requirements.txt` (Python 3.11+).
3. Recompute metrics from logged outputs (no API calls): `python postprocess_existing_run_root.py --run-root data/runs/full_pilot_20260520_192127`
4. Full rerun: `python run_pilot.py` (redundancy) and `python control_experiment.py` (filler control); cross-model via the `run_*.bat` scripts.

All experiments use temperature 0, fixed seed, fixed prompt and schema; per-call raw responses are logged before any post-processing, so scoring is fully auditable.

## License

Code: MIT. Synthetic data: CC BY 4.0. All clinical documents are fully synthetic; no real patient data is used or referenced.
