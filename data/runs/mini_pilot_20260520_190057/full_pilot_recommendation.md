# Full Pilot Recommendation (Conservative)

## Benchmark operational?
- Yes: mini-pilot produced non-empty outputs, nonzero entities, and computable semantic metrics.

## Is there measurable semantic movement with redundancy (1x→2x→5x)?
- Suggestive: mean F1 decreased across levels in this mini-pilot; mean RSS (F1_1x - F1_5x) = `0.171`.

## Is the trend direction consistent?
- Monotonic-decrease patients: `2/3` (N is tiny).

## Structural stability / JSON drift?
- No structural drift observed here: SDS=0 and repair_needed=0 for all 9 calls (does not rule out drift at higher redundancy or longer contexts).

## Recommendation
- Proceed to a larger pilot (e.g., 180 calls) is **scientifically reasonable** *if* you want to test whether this suggestive semantic trend persists with larger N and multiple runs/condition.
- Keep wording conservative: this mini-pilot alone does not establish a robust effect.

