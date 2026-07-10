# Mini-Pilot Analysis (Conservative)

Question: Does semantic redundancy measurably alter structured extraction behavior?

## What varied
- Redundancy factor only: `1x`, `2x`, `5x`

## What was fixed
- Prompt, schema, model/provider, generation params, repair logic, evaluator logic

## Aggregate trends (mean ± std across 3 patients)

### F1
```
 repetition_level     mean      std  count
                1 0.503890 0.187864      3
                2 0.427910 0.294991      3
                5 0.332672 0.180024      3
```

### Structural Drift Score (SDS)
```
 repetition_level  mean  std  count
                1   0.0  0.0      3
                2   0.0  0.0      3
                5   0.0  0.0      3
```

### Repair frequency
```
 repetition_level  mean  std  count
                1   0.0  0.0      3
                2   0.0  0.0      3
                5   0.0  0.0      3
```

### Omission rate
```
 repetition_level     mean      std  count
                1 0.502646 0.195910      3
                2 0.576720 0.302144      3
                5 0.671958 0.188036      3
```

### Hallucination rate
```
 repetition_level     mean      std  count
                1 0.465608 0.155793      3
                2 0.502646 0.195910      3
                5 0.597884 0.060094      3
```

## Conservative interpretation guidance
- With N=3 patients and 1 run/condition, treat any movement as *suggestive* only.
- Prefer looking for monotonic trends (1x→2x→5x) or sharp discontinuities.

## Artifacts
- Per-condition comparisons in `comparisons/`.
- Plots in `plots/`.

