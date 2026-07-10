# Paper-Ready Examples (Pilot-Scale, Conservative)

Use these as *illustrative* examples (not representative claims).

# Qualitative Failure Cases (Conservative)

This section highlights a few patients with large RSS at 32x for manual inspection.
See `outputs/<patient>/rep_1x/run_01/repaired.json` vs `rep_32x/run_01/repaired.json` for details.

Top RSS (32x):
- patient_02: RSS_32x=`0.571` (F1_1x=`0.714`, F1_32x=`0.143`)
- patient_06: RSS_32x=`0.400` (F1_1x=`0.600`, F1_32x=`0.200`)
- patient_04: RSS_32x=`0.333` (F1_1x=`0.667`, F1_32x=`0.333`)

Suggested manual inspection paths (examples):
- `outputs/patient_02/rep_1x/run_01/repaired.json` vs `outputs/patient_02/rep_32x/run_01/repaired.json`
- `outputs/patient_06/rep_1x/run_01/repaired.json` vs `outputs/patient_06/rep_32x/run_01/repaired.json`
- `outputs/patient_04/rep_1x/run_01/repaired.json` vs `outputs/patient_04/rep_32x/run_01/repaired.json`

Example wording template (fill after inspection):
> “At 32x redundancy, the model preserved X but omitted Y and Z despite unchanged semantic content.”

