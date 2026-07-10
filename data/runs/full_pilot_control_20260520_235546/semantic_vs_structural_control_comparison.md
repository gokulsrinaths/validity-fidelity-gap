# Semantic vs Structural Control Comparison (Conservative)

Key observation pattern to check:
- semantic metrics (F1 / omissions / hallucinations) may diverge between redundancy and filler control at matched length,
- while structural metrics (raw JSON validity / repair / SDS) remain mostly stable.

## Structural summary
```
 repetition  redundancy_raw_json_valid_rate  redundancy_repair_rate  redundancy_sds_mean  control_raw_json_valid_rate  control_repair_rate  control_sds_mean
          1                             1.0                     0.0                  0.0                     1.000000             0.000000          0.000000
          2                             1.0                     0.0                  0.0                     1.000000             0.000000          0.000000
          5                             1.0                     0.0                  0.0                     1.000000             0.000000          0.000000
         10                             1.0                     0.0                  0.0                     1.000000             0.000000          0.000000
         16                             1.0                     0.0                  0.0                     0.966667             0.033333          0.166667
         32                             1.0                     0.0                  0.0                     1.000000             0.000000          0.000000
```

## Semantic summary
```
 repetition  redundancy_f1_mean  control_f1_mean  redundancy_omission_mean  control_omission_mean  redundancy_halluc_mean  control_halluc_mean
          1            0.499010         0.493520                  3.833333               3.833333                3.533333             3.533333
          2            0.457393         0.522393                  4.100000               3.700000                3.700000             3.300000
          5            0.324956         0.509893                  5.000000               3.800000                4.600000             3.400000
         10            0.311006         0.509893                  5.066667               3.800000                4.766667             3.400000
         16            0.291958         0.481706                  5.200000               4.033333                4.900000             3.366667
         32            0.258625         0.253839                  5.400000               5.466667                5.100000             5.066667
```

