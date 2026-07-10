# Change-point (step-drop) summary (descriptive)

- source: `data\runs\full_pilot_20260520_192127\metrics\redundancy_scaling_statistics.csv`

## Largest step drop in mean F1
- span: `2x -> 5x`
- delta_F1: `-0.1324` (more negative = larger drop)

## Step deltas table

```
 from_rep  to_rep  delta_f1
        1       2 -0.041618
        2       5 -0.132437
        5      10 -0.013950
       10      16 -0.019048
       16      32 -0.033333
```

Interpretation: this is a simple descriptive diagnostic, not a formal statistical change-point test.
