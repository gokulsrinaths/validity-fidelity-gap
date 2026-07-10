# Statistical Interpretation (Conservative)

This interpretation follows the precomputed `statistical_analysis.md` (Spearman correlations with bootstrap CIs).

Key points (descriptive):
- Repetition is **negatively associated** with F1 in this pilot (Spearman rho < 0).
- Repetition is **positively associated** with omission count (Spearman rho > 0).
- These are associations within a single model/provider setting; they do not imply causality.

Details:

# Statistical Analysis (Conservative)

This analysis is descriptive only (no causality claims).

## Spearman correlations (bootstrap percentile CI)
- repetition vs F1: rho=`-0.417` CI=`[-0.523, -0.294]`
- repetition vs omission_count: rho=`0.290` CI=`[0.158, 0.420]`

Notes:
- Bootstrap resamples calls with replacement (paired).
- Interpret with caution; dependencies exist within patient/runs.

