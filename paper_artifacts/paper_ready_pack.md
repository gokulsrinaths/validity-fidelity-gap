# Paper-Ready Pack (Conservative)

This repository now contains:

## Core completed experiments

1. **Redundancy pilot (180 calls, 8B)**  
   - Run root: `data/runs/full_pilot_20260520_192127/`
   - Key outputs: `metrics/redundancy_scaling_statistics.csv`, `plots/repetition_vs_F1.png`, `statistical_analysis.md`

2. **Length-matched filler control (180 calls) + direct comparison**  
   - Run root: `data/runs/full_pilot_control_20260520_235546/`
   - Key outputs: `control_vs_redundancy.csv`, `DRE_statistics.csv`, `plots/redundancy_vs_filler_F1.png`

3. **Cross-model validation (1 run/condition; 10 pts; 6 reps; both conditions)**  
   - `data/runs/cross_model_llama70b/`
   - `data/runs/cross_model_qwen72b/`

4. **Cross-model replication (midrange reps; 3 runs/condition; both conditions)**  
   - `data/runs/cross_model_llama70b_rep3_midrange/`
   - `data/runs/cross_model_qwen72b_rep3_midrange/`

## Key paper figures (grayscale-safe)

- Cross-model DRE overview: `paper_artifacts/model_comparison_DRE.png`
- Redundancy vs filler F1 curve (8B): `data/runs/full_pilot_control_20260520_235546/plots/redundancy_vs_filler_F1.png`
- Redundancy scaling (8B): `data/runs/full_pilot_20260520_192127/plots/repetition_vs_F1.png`

## Reviewer-critical audits

- Token matching (true prompt tokens from `usage.json`):  
  `data/runs/full_pilot_control_20260520_235546/token_matching_audit_true_tokens.md`
- Filler overlap check (lexical overlap vs GT entities):  
  `data/runs/full_pilot_control_20260520_235546/filler_quality_audit.md`

## DRE distributions

- Per-patient DRE (8B, patient×rep): `paper_artifacts/per_patient_DRE_llama8b.csv`
- Per-rep DRE summary (8B): `paper_artifacts/per_rep_DRE_llama8b.csv`

## Conservative claim framing (suggested)

- Primary claim: semantic extraction quality degrades with increasing redundancy while structural JSON validity remains stable (8B pilot).
- Control result: at matched lengths, mid-range repetition levels show positive DRE (redundancy-amplified degradation), with convergence at extreme repetition.
- Cross-model result: redundancy amplification appears smaller and model-dependent; replication midrange shows small positive DRE for both 70B and Qwen-72B.

## Key limitations (must state)

- Token matching uses backend `prompt_tokens` (includes prompt wrapper); not pure document-only token matching.
- Filler is synthetic; a curated external corpus could strengthen control purity.
- Cross-model replication uses midrange repetitions; additional runs could tighten uncertainty further.

