# GT vs Repaired — patient_01 — 1x

- ground truth: `data\patient_01\ground_truth\patient_01.json`
- repaired: `data\runs\mini_pilot_20260520_190057\outputs\patient_01\rep_1x\run_01\repaired.json`

## conditions

### Missing (vs GT)
- Asthma exacerbation

### Hallucinated (vs GT)
- (none)

## medications

### Missing (vs GT)
- Albuterol inhaler 90 mcg 2 puffs q4-6h PRN
- Cetirizine 10 mg daily
- Prednisone 40 mg daily x 5 days

### Hallucinated (vs GT)
- {'name': 'Albuterol inhaler', 'dosage': '90 mcg', 'frequency': 'q4-6h', 'route': 'inhaled', 'prn': 'wheeze'}
- {'name': 'Cetirizine', 'dosage': '10 mg', 'frequency': 'daily', 'route': 'PO'}
- {'name': 'Prednisone', 'dosage': '40 mg', 'frequency': 'daily', 'route': 'PO', 'duration': '5 days'}

## observations

### Missing (vs GT)
- Peak flow 320 L/min
- SpO2 94% on room air

### Hallucinated (vs GT)
- {'name': 'Peak flow', 'value': '320 L/min'}
- {'name': 'SpO2', 'value': '94%'}

## procedures

### Missing (vs GT)
- (none)

### Hallucinated (vs GT)
- (none)

