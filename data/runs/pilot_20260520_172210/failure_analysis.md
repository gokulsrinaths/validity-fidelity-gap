# Failure Analysis (Low Redundancy)

Scope: `repetition=1x`, `run_01`, `patient_01..patient_03`.

Legend:
- A: structurally correct + semantically correct
- B: structurally wrong + semantically correct
- C: structurally correct + semantically wrong
- D: structurally wrong + semantically wrong

## patient_01 (rep_1x/run_01) — Class D

- `raw_response.txt` bytes: `0`
- `repaired.json` schema_ok: `True` (missing=[], extra=[])
- `ground_truth.json` schema_ok: `True` (missing=[], extra=[])

### Ground truth vs repaired (per field)

#### `conditions`

| Ground truth | Repaired output | Missing (vs GT) | Hallucinated (vs GT) |
|---|---|---|---|
| asthma, seasonal allergic rhinitis, asthma exacerbation | (empty) | asthma, asthma exacerbation, seasonal allergic rhinitis | (none) |

#### `medications`

| Ground truth | Repaired output | Missing (vs GT) | Hallucinated (vs GT) |
|---|---|---|---|
| albuterol inhaler 90 mcg 2 puffs q4-6h prn, prednisone 40 mg daily x 5 days, cetirizine 10 mg daily | (empty) | albuterol inhaler 90 mcg 2 puffs q4-6h prn, cetirizine 10 mg daily, prednisone 40 mg daily x 5 days | (none) |

#### `observations`

| Ground truth | Repaired output | Missing (vs GT) | Hallucinated (vs GT) |
|---|---|---|---|
| spo2 94% on room air, peak flow 320 l/min | (empty) | peak flow 320 l/min, spo2 94% on room air | (none) |

#### `procedures`

| Ground truth | Repaired output | Missing (vs GT) | Hallucinated (vs GT) |
|---|---|---|---|
| nebulized bronchodilator treatment | (empty) | nebulized bronchodilator treatment | (none) |

## patient_02 (rep_1x/run_01) — Class D

- `raw_response.txt` bytes: `0`
- `repaired.json` schema_ok: `True` (missing=[], extra=[])
- `ground_truth.json` schema_ok: `True` (missing=[], extra=[])

### Ground truth vs repaired (per field)

#### `conditions`

| Ground truth | Repaired output | Missing (vs GT) | Hallucinated (vs GT) |
|---|---|---|---|
| acute appendicitis | (empty) | acute appendicitis | (none) |

#### `medications`

| Ground truth | Repaired output | Missing (vs GT) | Hallucinated (vs GT) |
|---|---|---|---|
| ceftriaxone 1 g iv pre-op, metronidazole 500 mg iv pre-op, acetaminophen 650 mg q6h prn | (empty) | acetaminophen 650 mg q6h prn, ceftriaxone 1 g iv pre-op, metronidazole 500 mg iv pre-op | (none) |

#### `observations`

| Ground truth | Repaired output | Missing (vs GT) | Hallucinated (vs GT) |
|---|---|---|---|
| temp 38.1 c, wbc 14.2 k/ul | (empty) | temp 38.1 c, wbc 14.2 k/ul | (none) |

#### `procedures`

| Ground truth | Repaired output | Missing (vs GT) | Hallucinated (vs GT) |
|---|---|---|---|
| laparoscopic appendectomy | (empty) | laparoscopic appendectomy | (none) |

## patient_03 (rep_1x/run_01) — Class D

- `raw_response.txt` bytes: `0`
- `repaired.json` schema_ok: `True` (missing=[], extra=[])
- `ground_truth.json` schema_ok: `True` (missing=[], extra=[])

### Ground truth vs repaired (per field)

#### `conditions`

| Ground truth | Repaired output | Missing (vs GT) | Hallucinated (vs GT) |
|---|---|---|---|
| type 2 diabetes mellitus, hypertension, diabetic foot ulcer | (empty) | diabetic foot ulcer, hypertension, type 2 diabetes mellitus | (none) |

#### `medications`

| Ground truth | Repaired output | Missing (vs GT) | Hallucinated (vs GT) |
|---|---|---|---|
| metformin 1000 mg bid, lisinopril 10 mg daily, amoxicillin-clavulanate 875/125 mg bid x 7 days | (empty) | amoxicillin-clavulanate 875/125 mg bid x 7 days, lisinopril 10 mg daily, metformin 1000 mg bid | (none) |

#### `observations`

| Ground truth | Repaired output | Missing (vs GT) | Hallucinated (vs GT) |
|---|---|---|---|
| a1c 8.7%, bp 152/92 mmhg | (empty) | a1c 8.7%, bp 152/92 mmhg | (none) |

#### `procedures`

| Ground truth | Repaired output | Missing (vs GT) | Hallucinated (vs GT) |
|---|---|---|---|
| wound debridement | (empty) | wound debridement | (none) |

