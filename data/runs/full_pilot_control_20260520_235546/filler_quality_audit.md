# Filler Quality Audit (Lexical Overlap Check)

This audits whether the filler-control documents contain lexical overlaps with ground-truth entity strings.
It is a conservative substring check on normalized text; it may undercount paraphrases and overcount incidental matches.

- control_root: `data\runs\full_pilot_control_20260520_235546`

## Overlap summary by repetition
```
 repetition  overlap_entities_mean  overlap_frac_mean  overlap_any_rate
          1                    5.1            0.69619               1.0
          2                    5.1            0.69619               1.0
          5                    5.1            0.69619               1.0
         10                    5.1            0.69619               1.0
         16                    5.1            0.69619               1.0
         32                    5.1            0.69619               1.0
```

## Notes
- Any nonzero overlap does not necessarily imply leakage of *facts*, but it is a red flag for control purity.
- If overlap is frequent, consider replacing filler with a curated external neutral corpus and re-running control.

