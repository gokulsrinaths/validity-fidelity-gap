# Dissociation Probe: Results
Generated: 2026-05-25T23:36:12.775732

## Part 1: Existing-data analysis (zero new API calls)

For each medication entity scored as FN (false negative) in existing structured
extraction runs at 5x and 16x redundancy, we checked whether the medication NAME
was nevertheless present in the model's output — encoded as a nested dict entry
rather than the required plain string.

| Rep | FN cases | Entity present as nested dict | Knowledge retention rate |
|-----|----------|-------------------------------|--------------------------|
| 5x  |  130  |  130                          | 100.0%                   |
| 16x |  150  |  150                          | 100.0%                   |
| **Overall** | **280** | **280** | **100.0%** |

**Interpretation:** 100% of all FN cases are NOT missing entities —
the model extracted the correct medication into a nested dict object
(e.g., {"name": "Albuterol inhaler", "dosage": "90 mcg", "frequency": "q4-6h", ...})
rather than the required plain string ("Albuterol inhaler 90 mcg q4-6h PRN").
The entity knowledge is intact; what fails is the format contract.

## Part 2: Free-form follow-up probe (30 patients)

For 30 patients, we sent a free-form "list medications" prompt using the
single-copy (1x) document — no schema, no JSON mode, no system prompt.
We compared medication recall in the free-form response against structured
extraction recall at 1x and 16x.

| Condition | Mean recall |
|-----------|-------------|
| Structured extraction at 1x | 0.833 |
| Structured extraction at 16x | 0.400 |
| Free-form probe (1x doc) | 0.967 |
| **Gap (free-form − structured 16x)** | **+0.567** |

**Interpretation:** When asked in free-form (no schema constraint), the model
recalls medications at rate 0.967, close to the 1x structured baseline (0.833).
Under structured extraction at 16x, recall drops to 0.400.
The gap of +0.567 confirms: the entity knowledge is accessible under a
different prompting regime; what is lost is adherence to the schema format
contract under high semantic load.

## Combined conclusion

Both analyses confirm the same claim: representation drift is a
**format-contract failure, not a knowledge failure**.

- Part 1: 100% of FN cases are entities present in the output as nested dicts —
  the model knows and extracts the entity, but emits it in the wrong format.
- Part 2: Free-form recall (0.967) >> structured recall at 16x (0.400) —
  the entity is accessible via a format-unconstrained probe.

These two independent lines of evidence satisfy the dissociation criterion:
knowledge of what to extract is preserved; adherence to how to format it is not.
