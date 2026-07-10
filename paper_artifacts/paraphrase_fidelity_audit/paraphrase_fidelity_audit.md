# Paraphrase Fidelity Audit (Heuristic)

- run_root: `data\runs\paraphrased_redundancy_20260523_150000`

This audit checks whether ground-truth entity strings (normalized) appear as substrings in the generated paraphrases.
It is a conservative *mention-preservation* diagnostic (not a semantic equivalence proof).

## Summary by entity type
```
entity_type  paraphrase_items  gold_total  missing_total  missing_rate
 conditions                40          76              8      0.105263
medications                40         100             48      0.480000
 procedures                40          28              2      0.071429
```

## Worst paraphrases (highest missing-mention counts)
```
patient_id                                                                                paraphrase_file  missing_mentions_n
patient_01 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_01/paraphrases/paraphrase_01.txt                   2
patient_01 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_01/paraphrases/paraphrase_02.txt                   2
patient_01 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_01/paraphrases/paraphrase_03.txt                   2
patient_01 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_01/paraphrases/paraphrase_04.txt                   2
patient_02 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_02/paraphrases/paraphrase_01.txt                   2
patient_02 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_02/paraphrases/paraphrase_02.txt                   2
patient_02 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_02/paraphrases/paraphrase_03.txt                   2
patient_02 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_02/paraphrases/paraphrase_04.txt                   2
patient_09 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_09/paraphrases/paraphrase_01.txt                   2
patient_09 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_09/paraphrases/paraphrase_02.txt                   2
patient_09 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_09/paraphrases/paraphrase_03.txt                   2
patient_09 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_09/paraphrases/paraphrase_04.txt                   2
patient_08 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_08/paraphrases/paraphrase_01.txt                   2
patient_08 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_08/paraphrases/paraphrase_02.txt                   2
patient_10 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_10/paraphrases/paraphrase_04.txt                   2
patient_10 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_10/paraphrases/paraphrase_02.txt                   2
patient_08 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_08/paraphrases/paraphrase_03.txt                   2
patient_08 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_08/paraphrases/paraphrase_04.txt                   2
patient_03 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_03/paraphrases/paraphrase_01.txt                   1
patient_03 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_03/paraphrases/paraphrase_02.txt                   1
patient_04 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_04/paraphrases/paraphrase_01.txt                   1
patient_04 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_04/paraphrases/paraphrase_02.txt                   1
patient_03 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_03/paraphrases/paraphrase_03.txt                   1
patient_03 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_03/paraphrases/paraphrase_04.txt                   1
patient_06 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_06/paraphrases/paraphrase_04.txt                   1
patient_06 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_06/paraphrases/paraphrase_03.txt                   1
patient_06 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_06/paraphrases/paraphrase_02.txt                   1
patient_06 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_06/paraphrases/paraphrase_01.txt                   1
patient_05 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_05/paraphrases/paraphrase_04.txt                   1
patient_05 data/runs/paraphrased_redundancy_20260523_150000/docs/patient_05/paraphrases/paraphrase_03.txt                   1
```

Artifacts:
- `paper_artifacts/paraphrase_fidelity_audit/paraphrase_fidelity_mentions.csv`
- `paper_artifacts/paraphrase_fidelity_audit/paraphrase_fidelity_summary.csv`
- `paper_artifacts/paraphrase_fidelity_audit/paraphrase_fidelity_worst.csv`
