param(
  [string]$FullPilotRoot = "data\runs\full_pilot_20260520_192127",
  [string]$ControlRoot   = "data\runs\full_pilot_control_20260520_235546"
)

$ErrorActionPreference = "Stop"

py -3 recompute_semantic_metrics_with_soft_norm.py --run_root $FullPilotRoot
py -3 recompute_semantic_metrics_with_soft_norm.py --run_root $ControlRoot

py -3 recompute_semantic_metrics_with_canonical_norm.py --run_root $FullPilotRoot
py -3 recompute_semantic_metrics_with_canonical_norm.py --run_root $ControlRoot

py -3 compute_dre_strict_vs_soft.py --redundancy_root $FullPilotRoot --control_root $ControlRoot
py -3 compute_dre_strict_soft_canonical.py --redundancy_root $FullPilotRoot --control_root $ControlRoot

py -3 entity_type_persistence_analysis.py --run_root $FullPilotRoot --out_dir paper_artifacts\entity_persistence_fullpilot
py -3 qualitative_case_sampler.py --redundancy_root $FullPilotRoot --reps 1,2,5,10,16,32 --out paper_artifacts\qualitative_cases_fullpilot.md --n 6
py -3 position_sensitivity_analysis.py --run_root $FullPilotRoot --out paper_artifacts\position_sensitivity_fullpilot.md
py -3 error_taxonomy_proxy.py --run_root $FullPilotRoot --out paper_artifacts\error_taxonomy_proxy_fullpilot.md

py -3 reproducibility_manifest.py

Write-Output "Offline recomputation complete."

