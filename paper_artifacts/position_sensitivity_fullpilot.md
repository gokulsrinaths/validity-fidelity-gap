# Position sensitivity (descriptive)

- run_root: `data\runs\full_pilot_20260520_192127`
- high repetition: `32x` (run_01 only)

This is a coarse diagnostic: we locate gold entity strings in the 1x document via substring match and measure whether the entity is omitted at the highest repetition.

```
 entity_type pos_bin  n  miss_rate
  conditions   early 11   0.454545
  conditions  middle  7   0.285714
  conditions    late  1   0.000000
 medications  middle  4   1.000000
observations  middle  1   1.000000
observations    late 17   0.764706
  procedures   early  1   0.000000
  procedures  middle  1   1.000000
  procedures    late  5   0.600000
```
