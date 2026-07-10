# Next Experiment Recommendation (Single Step)

## Recommendation: Constant-length control (unrelated filler)

Rationale:
- Current design confounds redundancy with total context length.
- The most scientifically direct next step is to hold length constant while varying redundancy semantics (repeat vs filler).

Design sketch (keep everything else fixed):
- For each repetition level, build a length-matched document with unrelated filler so total tokens match the highest repetition condition.
- Compare extraction metrics against the redundancy condition at the same length.

What it would answer:
- Whether the observed degradation is primarily long-context length pressure (generic) or repetition/semantic redundancy specific.

