# Interpretation Limitations (Conservative)

This pilot demonstrates an association between redundancy factor and semantic extraction quality for a single model/provider setup.

What we cannot conclude yet:
- Causality (redundancy *causes* degradation).
- Generalization to other models, providers, or document distributions.
- Whether the effect is redundancy-specific vs generic long-context degradation.

Why redundancy-specific vs long-context remains unresolved:
- Redundancy increases context length *and* repeats content; without a length-matched unrelated-filler control, the two are confounded.

Most important missing control:
- Constant-length control: match token length across repetition levels by inserting unrelated filler (same model/prompt/schema).

