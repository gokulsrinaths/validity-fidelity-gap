# Redundancy Specificity Analysis (Conservative)

This compares the redundancy condition vs a constant-length unrelated-filler control.

Primary outputs:
- `control_vs_redundancy.csv`
- `DRE_statistics.csv`
- plots in `plots/`

Interpretation guidance:
- If filler-control shows similar degradation to redundancy, the effect may be largely generic long-context pressure.
- If redundancy degrades more than filler at matched length (positive DRE), that supports a redundancy-specific component (still not causality-proof).

