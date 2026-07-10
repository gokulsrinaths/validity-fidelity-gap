# Patient-Level Consistency (Conservative)

- patients: `10`
- degrade (F1_32x < F1_1x): `8`
- stable (F1_32x == F1_1x): `2`
- improve (F1_32x > F1_1x): `0`
- monotonic decrease across repetitions (per patient): `7`

## RSS distribution at 32x (RSS_32x = F1_1x - F1_32x)
- mean: `0.240`
- std: `0.175`
- min/max: `0.000` / `0.571`

## Per-patient table
```
patient_id    F1_1x   F1_32x  RSS_32x  monotonic_decrease  monotonic_increase
patient_01 0.274510 0.125000 0.149510                   1                   0
patient_02 0.714286 0.142857 0.571429                   1                   0
patient_03 0.444444 0.444444 0.000000                   0                   0
patient_04 0.666667 0.333333 0.333333                   1                   0
patient_05 0.352941 0.117647 0.235294                   0                   0
patient_06 0.600000 0.200000 0.400000                   1                   0
patient_07 0.571429 0.285714 0.285714                   1                   0
patient_08 0.470588 0.470588 0.000000                   0                   0
patient_09 0.466667 0.200000 0.266667                   1                   0
patient_10 0.428571 0.266667 0.161905                   1                   0
```

