# Redundancy Drift Findings (Conservative)

Primary artifacts:
- `metrics/semantic_metrics.csv` (per call)
- `metrics/structural_metrics.csv` (per call)
- `metrics/variance_metrics.csv` (per condition)
- `metrics/redundancy_scaling_statistics.csv` (per repetition, with CI)

Interpretation guidance:
- Look for consistent movement of F1/omissions/hallucinations with repetition.
- Separately track structural stability (SDS/repair rate/raw JSON validity).

