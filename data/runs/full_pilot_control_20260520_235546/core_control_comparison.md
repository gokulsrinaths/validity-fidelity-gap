# Core Control Comparison Findings (Conservative)

Question: does repeated identical evidence degrade extraction more than equally long unrelated filler context?

This comparison uses:
- redundancy run: `data\runs\full_pilot_20260520_192127`
- length-matched filler control: `data\runs\full_pilot_control_20260520_235546`

## By-repetition table (means)
```
 repetition  redundancy_f1_mean  redundancy_omission_mean  redundancy_halluc_mean  redundancy_raw_json_valid_rate  redundancy_sds_mean  redundancy_repair_rate  redundancy_output_variance_mean  control_f1_mean  control_omission_mean  control_halluc_mean  control_raw_json_valid_rate  control_sds_mean  control_repair_rate  control_output_variance_mean
          1            0.499010                  3.833333                3.533333                             1.0                  0.0                     0.0                     5.237828e-02         0.493520               3.833333             3.533333                     1.000000          0.000000             0.000000                      0.052378
          2            0.457393                  4.100000                3.700000                             1.0                  0.0                     0.0                     0.000000e+00         0.522393               3.700000             3.300000                     1.000000          0.000000             0.000000                      0.010476
          5            0.324956                  5.000000                4.600000                             1.0                  0.0                     0.0                     2.761764e-02         0.509893               3.800000             3.400000                     1.000000          0.000000             0.000000                      0.000000
         10            0.311006                  5.066667                4.766667                             1.0                  0.0                     0.0                     2.249885e-02         0.509893               3.800000             3.400000                     1.000000          0.000000             0.000000                      0.000000
         16            0.291958                  5.200000                4.900000                             1.0                  0.0                     0.0                     1.469313e-02         0.481706               4.033333             3.366667                     0.966667          0.166667             0.033333                      0.036665
         32            0.258625                  5.400000                5.100000                             1.0                  0.0                     0.0                     3.330669e-17         0.253839               5.466667             5.066667                     1.000000          0.000000             0.000000                      0.020203
```

