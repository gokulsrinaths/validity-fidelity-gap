# Cross-Model Summary (DRE)

This report consolidates DRE across:
- LLaMA-8B full pilots (redundancy vs filler control)
- LLaMA-70B midrange replication (3 runs/condition)
- Qwen-72B midrange replication (3 runs/condition)

Primary files:
- `paper_artifacts/cross_model_DRE_combined.csv`
- `paper_artifacts/model_comparison_DRE.png`

Table:
```
                 model_label  repetition      DRE
LLaMA-70B (midrange, 3 runs)           2 0.000000
LLaMA-70B (midrange, 3 runs)           5 0.007629
LLaMA-70B (midrange, 3 runs)          10 0.029023
LLaMA-70B (midrange, 3 runs)          16 0.025765
LLaMA-8B (3-run full pilots)           1 0.000000
LLaMA-8B (3-run full pilots)           2 0.070490
LLaMA-8B (3-run full pilots)           5 0.190427
LLaMA-8B (3-run full pilots)          10 0.204377
LLaMA-8B (3-run full pilots)          16 0.195238
LLaMA-8B (3-run full pilots)          32 0.000704
 Qwen-72B (midrange, 3 runs)           2 0.000000
 Qwen-72B (midrange, 3 runs)           5 0.011675
 Qwen-72B (midrange, 3 runs)          10 0.017928
 Qwen-72B (midrange, 3 runs)          16 0.031091
```

