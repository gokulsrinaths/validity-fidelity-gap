# Normalization Issues

Current normalization (strict evaluator) is essentially:
- lowercase + whitespace collapse
- punctuation stripping
- exact string match after normalization

Likely issues:
- Does not treat common medical variants as equivalent (e.g., `T2D` vs `Type 2 diabetes mellitus`).

Pilot synonym examples (implemented for relaxed scoring in `pipeline_failure_analysis.py`):
- `Type 2 Diabetes` / `Diabetes Mellitus Type II` / `T2D` → `type 2 diabetes mellitus`

Important note for this specific run:
- Predictions are empty across calls, so normalization improvements will not change F1 unless upstream output capture is fixed.

