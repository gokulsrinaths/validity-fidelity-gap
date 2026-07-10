# Semantic vs Structural Stability (Conservative)

Observation:
- Semantic metrics degrade with redundancy (F1 down; omissions/hallucinations up).
- Structural metrics remain stable (raw JSON validity stays at 1.0; repair rate 0.0; SDS 0.0).

Why this matters:
- It suggests a regime where *format correctness* is preserved while *content fidelity* erodes under redundancy.
- This supports analyzing semantic redundancy drift separately from structural drift.

Supporting summary table:
```
 repetition  f1_mean  omission_mean  halluc_mean  raw_json_valid_rate  repair_rate  sds_mean
          1 0.499010       3.833333     3.533333                  1.0          0.0       0.0
          2 0.457393       4.100000     3.700000                  1.0          0.0       0.0
          5 0.324956       5.000000     4.600000                  1.0          0.0       0.0
         10 0.311006       5.066667     4.766667                  1.0          0.0       0.0
         16 0.291958       5.200000     4.900000                  1.0          0.0       0.0
         32 0.258625       5.400000     5.100000                  1.0          0.0       0.0
```

