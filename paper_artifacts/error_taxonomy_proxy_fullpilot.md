# Error taxonomy (proxy by entity type)

- run_root: `data\runs\full_pilot_20260520_192127`
- comparison: 1x vs 32x (run_01 only)

This is a coarse proxy taxonomy: TP/FP/FN broken down by entity type. It supports statements like “medications accrue more FN under redundancy than conditions”.

```
 repetition  entity_type  tp  fp  fn  pred_n  gold_n  precision   recall
          1   conditions  13   5   6      18      19   0.722222 0.684211
          1  medications   2  23  23      25      25   0.080000 0.080000
          1 observations  15   5   7      20      22   0.750000 0.681818
          1   procedures   3   4   4       7       7   0.428571 0.428571
         32   conditions  12   5   7      17      19   0.705882 0.631579
         32  medications   0  25  25      25      25   0.000000 0.000000
         32 observations   4  17  18      21      22   0.190476 0.181818
         32   procedures   3   4   4       7       7   0.428571 0.428571
```
