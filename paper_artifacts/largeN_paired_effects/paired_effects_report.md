# Paired effects + DRE (large-N synthetic replication)

- redundancy_root: `data\runs\full_pilot_20260522_161847`
- control_root: `data\runs\full_pilot_control_20260522_165338`
- reps: `[1, 5, 10, 16]`

## Mean DRE with 95% bootstrap CI (paired by patient)

```
 repetition  mean_dre  dre_ci_low  dre_ci_high  sign_n  sign_n_pos  sign_n_neg  sign_n_zero
          5  0.186378    0.144043     0.230091     100          48           0           52
         10  0.173754    0.132576     0.217458     100          53           6           41
         16  0.173578    0.132453     0.216049     100          55           9           36
```

## Mean paired F1 drop with 95% bootstrap CI (redundancy condition)

```
 repetition     mean   ci_low  ci_high  sign_n  sign_n_pos  sign_n_neg  sign_n_zero
          5 0.155775 0.116012 0.197091   100.0        41.0         0.0         59.0
         10 0.169875 0.132913 0.208219   100.0        54.0         0.0         46.0
         16 0.189875 0.153527 0.226627   100.0        61.0         0.0         39.0
```

