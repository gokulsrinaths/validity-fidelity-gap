# Statistical Analysis (Conservative)

This analysis is descriptive only (no causality claims).

## Spearman correlations (bootstrap percentile CI)
- repetition vs F1: rho=`-0.326` CI=`[-0.410, -0.237]`
- repetition vs omission_count: rho=`0.236` CI=`[0.141, 0.327]`

Notes:
- Bootstrap resamples calls with replacement (paired).
- Interpret with caution; dependencies exist within patient/runs.

