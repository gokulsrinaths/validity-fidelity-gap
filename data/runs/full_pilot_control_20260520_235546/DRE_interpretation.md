# DRE Interpretation (Conservative)

Definition:
- `DRE = (F1_drop_redundancy) − (F1_drop_filler_control)`.
- Positive DRE suggests redundancy causes more degradation than length-matched unrelated filler (still not causal proof).

## DRE by repetition (from `DRE_statistics.csv`)
```
 repetition  F1_drop_redundancy  F1_drop_control      DRE
          1            0.000000         0.000000 0.000000
          2            0.041618        -0.028873 0.070490
          5            0.174055        -0.016373 0.190427
         10            0.188004        -0.016373 0.204377
         16            0.207052         0.011814 0.195238
         32            0.240385         0.239681 0.000704
```

## Aggregate DRE (excluding 1x baseline)
- mean DRE: `0.132` (bootstrap 95% CI: `[0.054, 0.198]`) across repetition levels [2, 5, 10, 16, 32]

Interpretation guidance:
- If mean DRE > 0 and consistently positive across mid-range repetitions, that is suggestive of redundancy-amplified degradation.
- If DRE ≈ 0 at high repetition (e.g., 32x), that suggests convergence to a shared long-context floor where filler and redundancy both degrade similarly.

