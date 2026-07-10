# Comparison Integrity Check

Control run root: `data/runs/full_pilot_control_20260520_235546/`

Redundancy run root: `data/runs/full_pilot_20260520_192127/`

## Outputs generated (no API calls)

- `control_vs_redundancy.csv` ✅
- `DRE_statistics.csv` ✅
- `redundancy_specificity_analysis.md` ✅
- `plots/` ✅
  - `redundancy_vs_filler_F1.png`
  - `redundancy_vs_filler_omissions.png`
  - `redundancy_vs_filler_hallucinations.png`

## Notes

- This stage only reads existing `metrics/redundancy_scaling_statistics.csv` files from both runs and writes derived comparisons/plots.
- No network calls are performed by `--compare`.

