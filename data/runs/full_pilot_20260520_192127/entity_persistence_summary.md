# Entity Persistence Summary (Conservative)

This summarizes entity persistence relative to each run’s 1x extraction (set overlap / baseline set size).

Key qualitative pattern from the persistence table:
- `conditions` persistence remains relatively high through 32x in this pilot.
- `medications` and `observations` show the largest persistence drops by high redundancy.
- `procedures` persistence is intermediate in this dataset.

Full table:

# Entity Persistence Analysis (Conservative)

Persistence is measured relative to the 1x extraction for the same patient/run (set overlap / baseline set size).

```
 repetition  run  persistence_overall  persistence_conditions  persistence_medications  persistence_observations  persistence_procedures
          1  2.0             1.000000                1.000000                 1.000000                  1.000000                1.000000
          2  2.0             0.896548                0.900000                 0.866667                  0.933333                0.966667
          5  2.0             0.568333                0.766667                 0.500000                  0.550000                0.700000
         10  2.0             0.522976                0.850000                 0.433333                  0.400000                0.700000
         16  2.0             0.518571                0.900000                 0.433333                  0.350000                0.700000
         32  2.0             0.452738                0.900000                 0.300000                  0.283333                0.700000
```

