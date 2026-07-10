# Reproducibility (Artifact Map)

This repo contains all runs and postprocessing artifacts needed to reproduce the plots/tables in the ACL LaTeX paper.

## Paper entrypoint
- LaTeX: `Paper/Association_for_Computational_Linguistics__ACL__conference__3_/latex/redundancy_drift.tex`
- Bib: `Paper/Association_for_Computational_Linguistics__ACL__conference__3_/latex/redundancy_drift.bib`
- Figures directory: `Paper/Association_for_Computational_Linguistics__ACL__conference__3_/latex/figures/`

## Canonical run roots (do not rerun API calls)
- 8B redundancy pilot: `data/runs/full_pilot_20260520_192127/`
- 8B filler control: `data/runs/full_pilot_control_20260520_235546/`
- Large-N redundancy (synthetic): `data/runs/full_pilot_20260522_161847/`
- Large-N filler control (synthetic): `data/runs/full_pilot_control_20260522_165338/`
- Shuffled redundancy (midrange, rep3): `data/runs/full_pilot_shuffled_20260522_155750/`
- Section-level redundancy vs filler (Large-N): `data/runs/section_redundancy_20260522_224913/`
- Prompt robustness (A/B/C): `data/runs/prompt_robustness_20260523_134838/`

## Offline recomputation scripts (no network)
- Strict vs soft recompute: `recompute_semantic_metrics_with_soft_norm.py`
- Strict/soft/canonical recompute: `recompute_semantic_metrics_with_canonical_norm.py`
- Large-N paired effects + DRE with CIs: `paired_effects_and_dre_analysis.py`
- Section-level DRE with CIs: `section_redundancy_analysis.py`
- Entity-type persistence with CIs: `entity_type_persistence_analysis.py`
- Qualitative sampler: `qualitative_case_sampler.py`
- Position diagnostic: `position_sensitivity_analysis.py`
- Usage/latency extraction: `latency_cost_analysis.py`
- Hash manifest: `reproducibility_manifest.py`

## Checksums
- Manifest with SHA256 hashes for key CSVs: `paper_artifacts/reproducibility_manifest.json`

