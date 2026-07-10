# Pilot Findings (Conservative)

## Questions answered
- Does redundancy improve extraction initially?
- Does performance saturate or degrade at high redundancy?
- Does structural instability increase (SDS / repair rate / raw JSON validity)?
- Does redundancy increase output variance?

## Summary (aggregate)
- F1: 1x `0.464`, 2x `0.457`, 32x `0.258`.
- Structural drift (SDS): 1x `0.167`, 32x `0.167`.
- Repair frequency: 1x `0.033`, 32x `0.033`.

## Interpretation guidance
- Evidence for a redundancy-driven phenomenon is strongest if structural instability increases with repetition while prompts/params are fixed.
- Treat correlations as exploratory; confirm with larger N or additional controls.

See `correlation_summary.md` and the figures in `plots/`.
