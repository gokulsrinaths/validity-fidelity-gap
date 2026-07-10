# Claim Candidates (Conservative)

## Weak claim
- In this pilot (single model/provider), higher repetition levels are associated with lower entity-extraction F1 and higher omission counts, while JSON validity remains stable.

## Moderate claim
- We observe preliminary evidence that exact semantic redundancy can degrade entity-level extraction fidelity without inducing structural JSON failures (SDS≈0; repair_rate≈0).

## Strongest defensible claim (still pilot-scale)
- Across 10 synthetic patients (180 calls; 6 redundancy levels; 3 runs/condition), repetition level shows a negative Spearman association with F1 and a positive association with omissions, consistent with a semantic redundancy drift phenomenon under fixed prompting and decoding settings.

