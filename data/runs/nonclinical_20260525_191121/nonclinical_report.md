# Non-Clinical Generalization Experiment Report

- run_id: `20260525_191121`
- model: `meta-llama/Meta-Llama-3.1-8B-Instruct`
- task: News article structured extraction
- schema: `{doc_id, events[], persons[], organizations[], locations[]}`
- documents: 10
- repetitions: [1, 5, 10, 16]
- runs_per_condition: 1

## Key findings

- F1 at 1×: `0.664` | F1 at 16×: `0.665`
- JSON validity at 1×: `1.000` | at 16×: `1.000`
- Max SDS across all conditions: `0.000` (0 = no structural drift)

## DRE summary

```
 repetition  mean_dre  mean_drop_red  mean_drop_fill   f1_red  f1_fill  n
          5  0.061707       0.058557       -0.003150 0.605018 0.669492 10
         10  0.044710       0.039447       -0.005262 0.624128 0.671604 10
         16 -0.007924      -0.001902        0.006022 0.665477 0.660320 10
```

## Redundancy scaling

```
 repetition  f1_mean   f1_std  fp_mean  fn_mean  json_valid_rate  sds_mean
          1 0.663575 0.126075      3.1      4.7              1.0       0.0
          5 0.605018 0.130216      4.4      5.1              1.0       0.0
         10 0.624128 0.114655      4.7      4.7              1.0       0.0
         16 0.665477 0.096615      3.9      4.3              1.0       0.0
```

## Interpretation

- Positive DRE at midrange repetitions = representation drift present in news domain
- JSON validity and SDS = how close to 1.00 and 0.00 throughout
- Entity-type breakdown: see metrics/entity_type_breakdown.csv
  (expect 'events' to collapse like 'medications' — rich nested-dict alternatives)
