# Core Findings (Conservative)

This summarizes the completed 180-call pilot at `data/runs/full_pilot_20260520_192127/`.

## A. Does mean F1 decrease with redundancy?
- Yes: `f1_mean` drops from 1x `0.499` to 32x `0.259`.

## B. Does omission increase?
- Yes: `omission_mean` rises from 1x `3.83` to 32x `5.40`.

## C. Does hallucination increase?
- Yes: `halluc_mean` rises from 1x `3.53` to 32x `5.10`.

## D. Does variance increase?
- Mixed/weak in this pilot: `output_variance_mean` does not show a simple monotonic increase (see `metrics/variance_metrics.csv`).

## E. Does SDS remain stable?
- Yes: `sds_mean` is `0.0` at 1x and `0.0` at 32x; `raw_json_valid_rate=1.0` and `repair_rate=0.0` at all levels.

## F. Is 32x clearly worse than 1x?
- Yes on mean metrics: ΔF1 (32x-1x) = `-0.240`; Δomissions = `1.57`; Δhallucinations = `1.57`.

## Scaling table (means ± std, with 95% CI columns)

```
 repetition  n  f1_mean   f1_std  f1_ci_low  f1_ci_high  omission_mean  halluc_mean  raw_json_valid_rate  repair_rate  sds_mean  output_variance_mean
          1 30 0.499010 0.147411   0.446260    0.551761       3.833333     3.533333                  1.0          0.0       0.0          5.237828e-02
          2 30 0.457393 0.185309   0.391081    0.523705       4.100000     3.700000                  1.0          0.0       0.0          0.000000e+00
          5 30 0.324956 0.211816   0.249158    0.400753       5.000000     4.600000                  1.0          0.0       0.0          2.761764e-02
         10 30 0.311006 0.188111   0.243691    0.378321       5.066667     4.766667                  1.0          0.0       0.0          2.249885e-02
         16 30 0.291958 0.174291   0.229589    0.354328       5.200000     4.900000                  1.0          0.0       0.0          1.469313e-02
         32 30 0.258625 0.121985   0.214973    0.302277       5.400000     5.100000                  1.0          0.0       0.0          3.330669e-17
```

