# Redundancy Drift Pilot Summary

- run_id: `20260520_152150`
- patients: 10
- repetitions: [1, 2, 5, 10, 16, 32]
- runs_per_condition: 3

## Key findings (aggregate)
- F1 at 1x: `0.464`; F1 at 32x: `0.258` (overall degraded).
- Drift at 32x (vs gold + vs 1x): `0.731` (higher means less invariant).
- Structural Drift Score (SDS) at 1x: `0.167`; SDS at 32x: `0.167`.
- Repair frequency at 1x: `0.033`; at 32x: `0.033`.

## Structural instability under redundancy
- Inspect `plots/repetition_vs_raw_json_validity.png`, `plots/repetition_vs_repair_frequency.png`, and `plots/repetition_vs_structural_drift_score.png`.
- Raw outputs: `raw_outputs/`; repaired outputs: `repaired_outputs/`.

## Semantic drift under redundancy
- Inspect `plots/repetition_vs_f1.png`, `plots/repetition_vs_hallucination_rate.png`, and `plots/repetition_vs_omission_rate.png`.

## Tables
- `metrics/semantic_metrics.csv`: precision/recall/F1 + omission/hallucination + drift.
- `metrics/structural_metrics.csv`: JSON validity, schema adherence, repair frequency, SDS.
- `metrics/context_metrics.csv`: page count, chars, estimated tokens.
- `metrics/variance_metrics.csv`: run-to-run variance within condition.
- `metrics/aggregated_results.csv`: per-patient semantic aggregates.

## Interpretation checklist
- Redundancy increases structural instability if SDS and repair frequency increase with repetition.
- Semantic drift correlates with structural drift if high-SDS conditions also show worse F1 or higher omissions/hallucinations.
- Schema adherence degradation shows up as lower schema_match_rate and higher missing/extra keys.
- Performance saturated if curves flatten after moderate repetition (e.g., 5x–10x).
- Performance degraded at high redundancy if F1 drops or omissions/hallucinations rise at 16x–32x.
