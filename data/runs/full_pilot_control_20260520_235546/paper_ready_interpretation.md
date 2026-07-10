# Paper-Ready Interpretation (Conservative)

## Strongest defensible claim (based on this comparison)
- At matched (approximate) context lengths, redundancy and filler control do not behave identically across repetitions: mid-range repetitions show a positive differential redundancy effect (DRE>0), suggesting redundancy can *amplify* degradation beyond generic length pressure in this setting.

## Key limitations / reviewer risks
- Token matching uses an estimated token heuristic (chars→tokens), not true tokenizer counts.
- Control filler is synthetic and may interact with the model differently than natural unrelated text.
- At extreme redundancy (32x), DRE is near zero, suggesting convergence to a long-context floor; interpretations should avoid claiming a purely redundancy-specific phenomenon without more controls.

## Most important figures
- `plots/redundancy_vs_filler_F1.png`
- `DRE_statistics.csv` (and a derived DRE plot if added later)

