# Effect Directionality Summary (Conservative)

Direction is evaluated at the patient level using mean F1 at 1x vs mean F1 at 32x (averaged over 3 runs each).

- degrade (Δ<0): `8`
- stable (Δ=0): `2`
- improve (Δ>0): `0`

Per-patient deltas:
```
patient_id    F1_1x   F1_32x  delta_32x_minus_1x
patient_01 0.274510 0.125000           -0.149510
patient_02 0.714286 0.142857           -0.571429
patient_03 0.444444 0.444444            0.000000
patient_04 0.666667 0.333333           -0.333333
patient_05 0.352941 0.117647           -0.235294
patient_06 0.600000 0.200000           -0.400000
patient_07 0.571429 0.285714           -0.285714
patient_08 0.470588 0.470588            0.000000
patient_09 0.466667 0.200000           -0.266667
patient_10 0.428571 0.266667           -0.161905
```

