# Entity Degradation Analysis (By Entity Type)

This analyzes how many entities (by type) appear in repaired outputs as redundancy increases.
Counts are set-cardinalities of extracted strings (not normalized synonyms).

## Mean extracted entity counts by repetition (N=3 patients)

```
 repetition_level  conditions_n  medications_n  observations_n  procedures_n
                1      2.000000            3.0             2.0           1.0
                2      1.666667            3.0             2.0           1.0
                5      1.666667            3.0             2.0           1.0
```

## Deltas vs 1x baseline (means)

### 2x minus 1x

- conditions: `-0.333`
- medications: `+0.000`
- observations: `+0.000`
- procedures: `+0.000`

### 5x minus 1x

- conditions: `-0.333`
- medications: `+0.000`
- observations: `+0.000`
- procedures: `+0.000`

## Preliminary note (heuristic)
- Largest mean decrease at 5x (by count) appears in: `conditions` (pilot-scale; interpret cautiously).

