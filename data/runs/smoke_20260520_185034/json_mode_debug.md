# JSON Mode Debug

- `response_format` requested: `{type: json_object}` (see `deepinfra_client.py`).
- `finish_reason`: `'stop'`
- `usage` present: `True`
  - `prompt_tokens`: `396`
  - `completion_tokens`: `195`
  - `total_tokens`: `591`
- `message.content` type: `<class 'str'>`
- `message.content` length: `542`

## Content preview (first 400 chars)
```
{
"patient_id": "001-88421",
"conditions": ["Asthma exacerbation"],
"medications": [
  {"name": "Albuterol inhaler", "dosage": "90 mcg", "frequency": "q4-6h", "route": "inhaled", "prn": "wheeze"},
  {"name": "Prednisone", "dosage": "40 mg", "frequency": "daily", "route": "PO", "duration": "5 days"},
  {"name": "Cetirizine", "dosage": "10 mg", "frequency": "daily", "route": "PO"}
],
"observations":
```
