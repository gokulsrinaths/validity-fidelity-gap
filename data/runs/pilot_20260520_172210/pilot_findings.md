# Pilot Findings (Conservative)

## Questions answered
- Does redundancy improve extraction initially?
- Does performance saturate or degrade at high redundancy?
- Does structural instability increase (SDS / repair rate / raw JSON validity)?
- Does redundancy increase output variance?

## Summary (aggregate)
- F1: 1x `0.000`, 2x `0.000`, 32x `0.000`.
- Structural drift (SDS): 1x `5.000`, 32x `5.000`.
- Repair frequency: 1x `1.000`, 32x `1.000`.

## Interpretation guidance
- Evidence for a redundancy-driven phenomenon is strongest if structural instability increases with repetition while prompts/params are fixed.
- Treat correlations as exploratory; confirm with larger N or additional controls.

See `correlation_summary.md` and the figures in `plots/`.
