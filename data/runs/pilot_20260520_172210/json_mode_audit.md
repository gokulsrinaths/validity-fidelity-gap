# JSON Mode Audit (DeepInfra)

Findings from artifacts:
- `raw_outputs/*.txt` are all `0` bytes in this run (180/180).
- Per-call `outputs/.../raw_response.txt` are `0` bytes in sampled cases.
- Per-call `outputs/.../response.json` files are absent, implying `DeepInfraResult.response_json` was `None` for those calls.

Interpretation:
- The model is not producing usable content for the pipeline, either because requests are failing (4xx/5xx/timeouts) or because the client is not capturing returned content.
- The current pipeline does not check `DeepInfraResult.ok` and does not log `DeepInfraResult.error`, so failures silently look like empty model outputs.

Open questions (not answerable post-hoc with current logs):
- Whether `response_format={"type":"json_object"}` is supported by the chosen model/backend.
- Whether requests were rejected (400) due to JSON mode / schema / payload format.

