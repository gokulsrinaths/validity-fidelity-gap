# Qualitative Cases (auto-sampled)

- redundancy_root: `data\runs\full_pilot_20260520_192127`
- selection: run_01, reps 1x vs 32x

## Worst degradation cases (lowest F1 delta)

## patient_02

- rep_hi: `32x`

### conditions
- missing@1x: `0`; halluc@1x: `0`
- missing@32x: `0`; halluc@32x: `0`

### medications
- missing@1x: `1`; halluc@1x: `1`
- missing@32x: `3`; halluc@32x: `3`
- example missing@32x: `['acetaminophen 650 mg q6h prn', 'ceftriaxone 1 g iv pre-op', 'metronidazole 500 mg iv pre-op']`
- example halluc@32x: `["{'name': 'acetaminophen', 'dose': '650 mg', 'route': 'po', 'frequency': 'q6h', 'prn': true}", "{'name': 'ceftriaxone', 'dose': '1 g', 'route': 'iv', 'pre_op': true}", "{'name': 'metronidazole', 'dose': '500 mg', 'route': 'iv', 'pre_op': true}"]`

### observations
- missing@1x: `0`; halluc@1x: `0`
- missing@32x: `2`; halluc@32x: `2`
- example missing@32x: `['temp 38.1 c', 'wbc 14.2 k/ul']`
- example halluc@32x: `["{'name': 'temp', 'value': '38.1 c'}", "{'name': 'wbc', 'value': '14.2 k/ul'}"]`

### procedures
- missing@1x: `1`; halluc@1x: `1`
- missing@32x: `1`; halluc@32x: `1`
- example missing@32x: `['laparoscopic appendectomy']`
- example halluc@32x: `["{'name': 'laparoscopic appendectomy', 'date': '2026-03-18'}"]`

## patient_06

- rep_hi: `32x`

### conditions
- missing@1x: `0`; halluc@1x: `0`
- missing@32x: `0`; halluc@32x: `0`

### medications
- missing@1x: `2`; halluc@1x: `2`
- missing@32x: `2`; halluc@32x: `2`
- example missing@32x: `['amoxicillin 500 mg bid x 10 days', 'ibuprofen 400 mg q6h prn']`
- example halluc@32x: `["{'name': 'amoxicillin', 'dosage': '500 mg', 'route': 'po', 'frequency': 'bid', 'duration': '10 days'}", "{'name': 'ibuprofen', 'dosage': '400 mg', 'route': 'po', 'frequency': 'q6h', 'duration': 'prn pain/fever'}"]`

### observations
- missing@1x: `1`; halluc@1x: `1`
- missing@32x: `2`; halluc@32x: `2`
- example missing@32x: `['rapid strep test positive', 'temp 39.0 c']`
- example halluc@32x: `["{'name': 'rapid strep test', 'value': 'positive'}", "{'name': 'temp', 'value': '39.0 c'}"]`

### procedures
- missing@1x: `0`; halluc@1x: `0`
- missing@32x: `0`; halluc@32x: `0`

## patient_09

- rep_hi: `32x`

### conditions
- missing@1x: `0`; halluc@1x: `0`
- missing@32x: `0`; halluc@32x: `0`

### medications
- missing@1x: `2`; halluc@1x: `2`
- missing@32x: `2`; halluc@32x: `2`
- example missing@32x: `['propranolol 20 mg bid', 'sumatriptan 50 mg at onset may repeat once']`
- example halluc@32x: `["{'name': 'propranolol', 'dosage': '20 mg', 'route': 'po', 'frequency': 'bid for migraine prevention'}", "{'name': 'sumatriptan', 'dosage': '50 mg', 'route': 'po', 'frequency': 'at onset of headache; may repeat once in 2 hours'}"]`

### observations
- missing@1x: `1`; halluc@1x: `1`
- missing@32x: `2`; halluc@32x: `2`
- example missing@32x: `['bp 118/74 mmhg', 'neuro exam normal']`
- example halluc@32x: `["{'name': 'bp', 'value': '118/74 mmhg'}", "{'name': 'neuro exam', 'value': 'normal'}"]`

### procedures
- missing@1x: `0`; halluc@1x: `0`
- missing@32x: `0`; halluc@32x: `0`

## patient_04

- rep_hi: `32x`

### conditions
- missing@1x: `0`; halluc@1x: `0`
- missing@32x: `0`; halluc@32x: `0`

### medications
- missing@1x: `2`; halluc@1x: `2`
- missing@32x: `2`; halluc@32x: `2`
- example missing@32x: `['sertraline 50 mg daily', 'trazodone 50 mg at bedtime prn']`
- example halluc@32x: `["{'name': 'sertraline', 'dosage': '50 mg', 'route': 'po', 'frequency': 'daily'}", "{'name': 'trazodone', 'dosage': '50 mg', 'route': 'po', 'frequency': 'at bedtime prn sleep'}"]`

### observations
- missing@1x: `0`; halluc@1x: `0`
- missing@32x: `2`; halluc@32x: `2`
- example missing@32x: `['phq-9 score 16', 'weight 78.4 kg']`
- example halluc@32x: `["{'name': 'phq-9 score', 'value': 16}", "{'name': 'weight', 'value': 78.4}"]`

### procedures
- missing@1x: `0`; halluc@1x: `0`
- missing@32x: `0`; halluc@32x: `0`

## patient_07

- rep_hi: `32x`

### conditions
- missing@1x: `1`; halluc@1x: `1`
- missing@32x: `1`; halluc@32x: `1`
- example missing@32x: `['osteoarthritis']`
- example halluc@32x: `['osteoarthritis (right knee)']`

### medications
- missing@1x: `2`; halluc@1x: `2`
- missing@32x: `2`; halluc@32x: `2`
- example missing@32x: `['atorvastatin 20 mg nightly', 'naproxen 500 mg bid prn']`
- example halluc@32x: `["{'name': 'atorvastatin', 'dosage': '20 mg', 'route': 'po', 'frequency': 'nightly'}", "{'name': 'naproxen', 'dosage': '500 mg', 'route': 'po', 'frequency': 'bid prn pain', 'precaution': 'hold 7 days prior to surgery'}"]`

### observations
- missing@1x: `0`; halluc@1x: `0`
- missing@32x: `2`; halluc@32x: `2`
- example missing@32x: `['bmi 31.2 kg/m2', 'ldl 168 mg/dl']`
- example halluc@32x: `["{'name': 'bmi', 'value': 31.2, 'unit': 'kg/m2'}", "{'name': 'ldl', 'value': 168, 'unit': 'mg/dl'}"]`

### procedures
- missing@1x: `0`; halluc@1x: `0`
- missing@32x: `0`; halluc@32x: `0`

## patient_05

- rep_hi: `32x`

### conditions
- missing@1x: `1`; halluc@1x: `1`
- missing@32x: `1`; halluc@32x: `1`
- example missing@32x: `['heart failure with reduced ejection fraction']`
- example halluc@32x: `['heart failure with reduced ejection fraction (hfref)']`

### medications
- missing@1x: `3`; halluc@1x: `3`
- missing@32x: `3`; halluc@32x: `3`
- example missing@32x: `['apixaban 5 mg bid', 'furosemide 40 mg daily', 'metoprolol succinate 50 mg daily']`
- example halluc@32x: `["{'name': 'apixaban', 'dosage': '5 mg', 'frequency': 'bid', 'route': 'po'}", "{'name': 'furosemide', 'dosage': '40 mg', 'frequency': 'daily', 'route': 'po'}", "{'name': 'metoprolol succinate', 'dosage': '50 mg', 'frequency': 'daily', 'route': 'po'}"]`

### observations
- missing@1x: `1`; halluc@1x: `0`
- missing@32x: `3`; halluc@32x: `2`
- example missing@32x: `['bnp 820 pg/ml', 'hr 110 bpm irregular', 'lvef 30%']`
- example halluc@32x: `["{'name': 'bnp', 'value': '820 pg/ml'}", "{'name': 'hr', 'value': '110 bpm irregular'}"]`

### procedures
- missing@1x: `1`; halluc@1x: `1`
- missing@32x: `1`; halluc@32x: `1`
- example missing@32x: `['electrical cardioversion']`
- example halluc@32x: `["{'name': 'electrical cardioversion', 'date': '2026-04-22'}"]`


## Best / most stable cases (highest F1 delta)

## patient_08

- rep_hi: `32x`

### conditions
- missing@1x: `1`; halluc@1x: `1`
- missing@32x: `1`; halluc@32x: `1`
- example missing@32x: `['chronic obstructive pulmonary disease']`
- example halluc@32x: `['chronic obstructive pulmonary disease (copd)']`

### medications
- missing@1x: `3`; halluc@1x: `3`
- missing@32x: `3`; halluc@32x: `3`
- example missing@32x: `['azithromycin 500 mg day 1 then 250 mg daily days 2-5', 'prednisone 40 mg daily x 5 days', 'tiotropium inhaler daily']`
- example halluc@32x: `['azithromycin 500 mg po day 1 then 250 mg daily days 2-5', 'prednisone 40 mg po daily x 5 days', 'tiotropium inhaler: 2 puffs inhaled daily']`

### observations
- missing@1x: `1`; halluc@1x: `0`
- missing@32x: `1`; halluc@32x: `0`
- example missing@32x: `['chest x-ray right lower lobe infiltrate']`

### procedures
- missing@1x: `0`; halluc@1x: `0`
- missing@32x: `0`; halluc@32x: `0`

## patient_03

- rep_hi: `32x`

### conditions
- missing@1x: `1`; halluc@1x: `1`
- missing@32x: `1`; halluc@32x: `1`
- example missing@32x: `['diabetic foot ulcer']`
- example halluc@32x: `['diabetic foot ulcer (left)']`

### medications
- missing@1x: `3`; halluc@1x: `3`
- missing@32x: `3`; halluc@32x: `3`
- example missing@32x: `['amoxicillin-clavulanate 875/125 mg bid x 7 days', 'lisinopril 10 mg daily', 'metformin 1000 mg bid']`
- example halluc@32x: `['amoxicillin-clavulanate 875/125 mg po bid x 7 days', 'lisinopril 10 mg po daily', 'metformin 1000 mg po bid with meals']`

### observations
- missing@1x: `0`; halluc@1x: `0`
- missing@32x: `0`; halluc@32x: `0`

### procedures
- missing@1x: `1`; halluc@1x: `1`
- missing@32x: `1`; halluc@32x: `1`
- example missing@32x: `['wound debridement']`
- example halluc@32x: `['wound debridement (left foot) 2026-02-11']`

## patient_01

- rep_hi: `32x`

### conditions
- missing@1x: `1`; halluc@1x: `0`
- missing@32x: `2`; halluc@32x: `0`
- example missing@32x: `['asthma', 'seasonal allergic rhinitis']`

### medications
- missing@1x: `3`; halluc@1x: `3`
- missing@32x: `3`; halluc@32x: `3`
- example missing@32x: `['albuterol inhaler 90 mcg 2 puffs q4-6h prn', 'cetirizine 10 mg daily', 'prednisone 40 mg daily x 5 days']`
- example halluc@32x: `["{'name': 'albuterol inhaler', 'dosage': '90 mcg', 'frequency': '2 puffs inhaled q4-6h', 'reason': 'prn wheeze'}", "{'name': 'cetirizine', 'dosage': '10 mg', 'frequency': 'daily'}", "{'name': 'prednisone', 'dosage': '40 mg', 'frequency': 'daily', 'reason': 'x 5 days'}"]`

### observations
- missing@1x: `2`; halluc@1x: `2`
- missing@32x: `2`; halluc@32x: `2`
- example missing@32x: `['peak flow 320 l/min', 'spo2 94% on room air']`
- example halluc@32x: `["{'name': 'peak flow', 'value': '320 l/min'}", "{'name': 'spo2', 'value': '94%', 'unit': 'on room air'}"]`

### procedures
- missing@1x: `1`; halluc@1x: `1`
- missing@32x: `1`; halluc@32x: `1`
- example missing@32x: `['nebulized bronchodilator treatment']`
- example halluc@32x: `["{'name': 'nebulized bronchodilator treatment', 'location': 'ed'}"]`

## patient_10

- rep_hi: `32x`

### conditions
- missing@1x: `1`; halluc@1x: `1`
- missing@32x: `1`; halluc@32x: `1`
- example missing@32x: `['acute kidney injury']`
- example halluc@32x: `['acute kidney injury (pre-renal)']`

### medications
- missing@1x: `2`; halluc@1x: `2`
- missing@32x: `2`; halluc@32x: `2`
- example missing@32x: `['normal saline iv fluids', 'ondansetron 4 mg odt q8h prn']`
- example halluc@32x: `['normal saline iv fluids (in hospital)', 'ondansetron 4 mg odt q8h prn nausea']`

### observations
- missing@1x: `1`; halluc@1x: `1`
- missing@32x: `2`; halluc@32x: `3`
- example missing@32x: `['bun 38 mg/dl', 'creatinine 2.1 mg/dl improved to 1.4 mg/dl']`
- example halluc@32x: `["{'value': '1.4', 'unit': 'mg/dl', 'date': 'discharge', 'measure': 'creatinine'}", "{'value': '2.1', 'unit': 'mg/dl', 'date': 'admission', 'measure': 'creatinine'}", "{'value': '38', 'unit': 'mg/dl', 'date': 'admission', 'measure': 'bun'}"]`

### procedures
- missing@1x: `0`; halluc@1x: `0`
- missing@32x: `0`; halluc@32x: `0`

## patient_05

- rep_hi: `32x`

### conditions
- missing@1x: `1`; halluc@1x: `1`
- missing@32x: `1`; halluc@32x: `1`
- example missing@32x: `['heart failure with reduced ejection fraction']`
- example halluc@32x: `['heart failure with reduced ejection fraction (hfref)']`

### medications
- missing@1x: `3`; halluc@1x: `3`
- missing@32x: `3`; halluc@32x: `3`
- example missing@32x: `['apixaban 5 mg bid', 'furosemide 40 mg daily', 'metoprolol succinate 50 mg daily']`
- example halluc@32x: `["{'name': 'apixaban', 'dosage': '5 mg', 'frequency': 'bid', 'route': 'po'}", "{'name': 'furosemide', 'dosage': '40 mg', 'frequency': 'daily', 'route': 'po'}", "{'name': 'metoprolol succinate', 'dosage': '50 mg', 'frequency': 'daily', 'route': 'po'}"]`

### observations
- missing@1x: `1`; halluc@1x: `0`
- missing@32x: `3`; halluc@32x: `2`
- example missing@32x: `['bnp 820 pg/ml', 'hr 110 bpm irregular', 'lvef 30%']`
- example halluc@32x: `["{'name': 'bnp', 'value': '820 pg/ml'}", "{'name': 'hr', 'value': '110 bpm irregular'}"]`

### procedures
- missing@1x: `1`; halluc@1x: `1`
- missing@32x: `1`; halluc@32x: `1`
- example missing@32x: `['electrical cardioversion']`
- example halluc@32x: `["{'name': 'electrical cardioversion', 'date': '2026-04-22'}"]`

## patient_07

- rep_hi: `32x`

### conditions
- missing@1x: `1`; halluc@1x: `1`
- missing@32x: `1`; halluc@32x: `1`
- example missing@32x: `['osteoarthritis']`
- example halluc@32x: `['osteoarthritis (right knee)']`

### medications
- missing@1x: `2`; halluc@1x: `2`
- missing@32x: `2`; halluc@32x: `2`
- example missing@32x: `['atorvastatin 20 mg nightly', 'naproxen 500 mg bid prn']`
- example halluc@32x: `["{'name': 'atorvastatin', 'dosage': '20 mg', 'route': 'po', 'frequency': 'nightly'}", "{'name': 'naproxen', 'dosage': '500 mg', 'route': 'po', 'frequency': 'bid prn pain', 'precaution': 'hold 7 days prior to surgery'}"]`

### observations
- missing@1x: `0`; halluc@1x: `0`
- missing@32x: `2`; halluc@32x: `2`
- example missing@32x: `['bmi 31.2 kg/m2', 'ldl 168 mg/dl']`
- example halluc@32x: `["{'name': 'bmi', 'value': 31.2, 'unit': 'kg/m2'}", "{'name': 'ldl', 'value': 168, 'unit': 'mg/dl'}"]`

### procedures
- missing@1x: `0`; halluc@1x: `0`
- missing@32x: `0`; halluc@32x: `0`
