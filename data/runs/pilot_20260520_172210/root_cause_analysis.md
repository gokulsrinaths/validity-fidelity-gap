# Root Cause Analysis

## What happened
- All `raw_outputs/*.txt` are empty (`0` bytes) for this run (180/180).
- Sampled per-call `outputs/.../raw_response.txt` are empty.
- Repair then produces schema-valid JSON objects with empty arrays.
- Semantic evaluator therefore reports F1 = 0 and 100% omissions.

## Answers to the key questions
- Is the model semantically extracting correctly? **Not measurable** in this run because the pipeline captured no model text.
- Is structural extraction working? **Repair/schema-normalization works**, but it is operating on empty raw text.
- Is the evaluator invalid/too strict? **No evidence**: ground truth schema matches evaluator keys; predictions are empty.
- Is schema mismatch causing F1 collapse? **No** (schemas align at top-level).
- Is repair damaging outputs? **Unlikely here**; it is filling empties due to upstream failure.
- Is DeepInfra JSON mode unreliable? **Possible**, but not provable post-hoc because HTTP errors are not logged/stored.

## Most likely failure source
- Upstream API call failures and/or response parsing issues are being silently swallowed.
- `run_experiments.py` does not check `result.ok` and does not persist `result.error` when calls fail.

## Does the pilot measure redundancy drift yet?
- **No**. With empty predictions for all conditions, there is no signal to analyze for drift.

