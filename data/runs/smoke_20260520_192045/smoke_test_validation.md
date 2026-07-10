# Smoke Test Validation

- patient_id: `patient_01`
- repetition: `1x`
- run: `01`
- api_ok: `True` status_code=`200` latency_s=`6.938`
- pdf pages: `1` chars: `719`
- raw content length: `559`
- repaired entity count: `8`

## Evaluator (strict) results
- micro_precision: `0.333`
- micro_recall: `0.375`
- micro_f1: `0.353`
- omissions: `5`
- hallucinations: `6`

## Where to inspect
- raw response object: `<project_root>\data\runs\smoke_20260520_192045\debug_raw_api_response.json`
- response structure: `<project_root>\data\runs\smoke_20260520_192045\response_structure_debug.txt`
- JSON mode debug: `<project_root>\data\runs\smoke_20260520_192045\json_mode_debug.md`
- extracted pdf preview: `<project_root>\data\runs\smoke_20260520_192045\debug_extracted_pdf_text.txt`
- raw model content: `<project_root>\data\runs\smoke_20260520_192045\debug_raw_content.txt`
- repaired output: `<project_root>\data\runs\smoke_20260520_192045\repaired.json`

