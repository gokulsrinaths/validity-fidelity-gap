# Live Integrity Checks

Run root: `data/runs/full_pilot_control_20260520_235546/`

Timestamp: `2026-05-21 00:45` (America/Los_Angeles)

## Status snapshot

- completed `repaired.json`: `180/180`
- started run folders: `180/180`
- `response_error.txt` files: `1`
  - `outputs/patient_08/rep_16x/run_01/response_error.txt` = `repaired_entities_empty`
- last `repaired.json` write time: `2026-05-21 00:18:35`
- active `python/py` processes: `6` (expected to drop to 0 once the run process fully exits)

## Random sample checks (Python json.loads)

Sampled 5 completed runs; all checks passed:

- `outputs/patient_05/rep_2x/run_03`: `raw_response.txt` non-empty, `response_meta.json` present, `repaired.json` valid JSON
- `outputs/patient_05/rep_10x/run_03`: `raw_response.txt` non-empty, `response_meta.json` present, `repaired.json` valid JSON
- `outputs/patient_10/rep_1x/run_02`: `raw_response.txt` non-empty, `response_meta.json` present, `repaired.json` valid JSON
- `outputs/patient_07/rep_16x/run_01`: `raw_response.txt` non-empty, `response_meta.json` present, `repaired.json` valid JSON
- `outputs/patient_03/rep_32x/run_02`: `raw_response.txt` non-empty, `response_meta.json` present, `repaired.json` valid JSON

## Notes

- One recorded integrity issue exists (`repaired_entities_empty`) at `patient_08/rep_16x/run_01`. This should be treated as an outcome/failure mode in the control condition and must be accounted for in downstream comparisons.

