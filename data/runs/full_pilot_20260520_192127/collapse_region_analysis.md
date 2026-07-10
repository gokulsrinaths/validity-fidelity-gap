# Collapse Region Analysis (Conservative)

This identifies where the *largest step changes* occur in the repetition scaling curve. It is descriptive only.

- Largest step drop in mean F1: `2x -> 5x` (ΔF1=`-0.132`)
- Largest step rise in mean omissions: `2x -> 5x` (Δomissions=`0.90`)
- Largest step rise in mean hallucinations: `2x -> 5x` (Δhallucinations=`0.90`)

## Step-change table
```
 from_rep  to_rep  delta_f1  delta_omission  delta_hallucination
        1       2 -0.041618        0.266667             0.166667
        2       5 -0.132437        0.900000             0.900000
        5      10 -0.013950        0.066667             0.166667
       10      16 -0.019048        0.133333             0.133333
       16      32 -0.033333        0.200000             0.200000
```

Interpretation guidance:
- A large step change suggests a potential threshold region (not proof of a phase transition).
- Confirm with additional runs/controls before over-interpreting thresholds.

