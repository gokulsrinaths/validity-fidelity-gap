# Schema Alignment Check

Expected schema keys:
- `['patient_id', 'conditions', 'medications', 'observations', 'procedures']`

Evidence:
- `data/patient_XX/ground_truth/patient_XX.json` uses the same top-level keys.
- `outputs/.../repaired.json` uses the same top-level keys (filled with empty arrays when raw output is invalid).

Conclusion:
- Top-level schema alignment is **not** the cause of F1=0 in this run.

