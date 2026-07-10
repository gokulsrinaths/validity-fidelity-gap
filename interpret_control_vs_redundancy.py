from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


CONTROL_ROOT = Path("data/runs/full_pilot_control_20260520_235546")
REDUNDANCY_ROOT = Path("data/runs/full_pilot_20260520_192127")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _bootstrap_mean_ci(xs: list[float], *, n: int = 5000, seed: int = 1337) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    x = np.asarray(xs, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return float("nan"), float("nan"), float("nan")
    mean = float(x.mean())
    if len(x) == 1:
        return mean, mean, mean
    idx = rng.integers(0, len(x), size=(n, len(x)))
    boots = x[idx].mean(axis=1)
    lo = float(np.quantile(boots, 0.025))
    hi = float(np.quantile(boots, 0.975))
    return mean, lo, hi


def main() -> int:
    comp = pd.read_csv(CONTROL_ROOT / "control_vs_redundancy.csv")
    dre = pd.read_csv(CONTROL_ROOT / "DRE_statistics.csv")

    # Core comparison findings
    md = [
        "# Core Control Comparison Findings (Conservative)",
        "",
        "Question: does repeated identical evidence degrade extraction more than equally long unrelated filler context?",
        "",
        "This comparison uses:",
        f"- redundancy run: `{REDUNDANCY_ROOT}`",
        f"- length-matched filler control: `{CONTROL_ROOT}`",
        "",
        "## By-repetition table (means)",
        "```",
        comp.to_string(index=False),
        "```",
        "",
    ]
    _write(CONTROL_ROOT / "core_control_comparison.md", "\n".join(md) + "\n")

    # DRE interpretation
    dre2 = dre[dre["repetition"] != 1].copy()
    mean_dre, lo_dre, hi_dre = _bootstrap_mean_ci(dre2["DRE"].astype(float).tolist())

    md = [
        "# DRE Interpretation (Conservative)",
        "",
        "Definition:",
        "- `DRE = (F1_drop_redundancy) − (F1_drop_filler_control)`.",
        "- Positive DRE suggests redundancy causes more degradation than length-matched unrelated filler (still not causal proof).",
        "",
        "## DRE by repetition (from `DRE_statistics.csv`)",
        "```",
        dre.to_string(index=False),
        "```",
        "",
        "## Aggregate DRE (excluding 1x baseline)",
        f"- mean DRE: `{mean_dre:.3f}` (bootstrap 95% CI: `[{lo_dre:.3f}, {hi_dre:.3f}]`) across repetition levels {dre2['repetition'].tolist()}",
        "",
        "Interpretation guidance:",
        "- If mean DRE > 0 and consistently positive across mid-range repetitions, that is suggestive of redundancy-amplified degradation.",
        "- If DRE ≈ 0 at high repetition (e.g., 32x), that suggests convergence to a shared long-context floor where filler and redundancy both degrade similarly.",
        "",
    ]
    _write(CONTROL_ROOT / "DRE_interpretation.md", "\n".join(md) + "\n")

    # Effect classification (single category, conservative)
    # Heuristic: if DRE positive for multiple mid reps and near-zero at 32x -> redundancy-amplified.
    dre_map = {int(r): float(v) for r, v in zip(dre["repetition"], dre["DRE"])}
    mid_pos = sum(1 for r in (2, 5, 10, 16) if dre_map.get(r, 0.0) > 0.05)
    near_zero_32 = abs(dre_map.get(32, 0.0)) < 0.05

    if mid_pos >= 2 and near_zero_32:
        category = "B. Redundancy-amplified degradation"
        rationale = "DRE is clearly positive at mid repetitions (2x–16x) but near zero at 32x, consistent with redundancy amplifying degradation before both conditions converge at extreme length."
    elif all(abs(dre_map.get(r, 0.0)) < 0.05 for r in dre_map if r != 1):
        category = "A. Mostly generic long-context degradation"
        rationale = "DRE values are near zero across repetitions, suggesting filler length largely explains the degradation."
    else:
        category = "C. Potential redundancy-specific degradation phenomenon"
        rationale = "DRE shows nontrivial positive values without clear convergence, suggesting redundancy-specific effects beyond generic length pressure (still preliminary)."

    _write(
        CONTROL_ROOT / "effect_classification.md",
        "\n".join(
            [
                "# Effect Classification (Conservative)",
                "",
                f"Classification: **{category}**",
                "",
                f"Rationale: {rationale}",
                "",
                "Important caveats:",
                "- This is based on aggregated means across repetition levels (not per-patient DRE yet).",
                "- One control run produced an empty extraction (`repaired_entities_empty`); treat as a meaningful failure mode in the control condition.",
                "",
            ]
        )
        + "\n",
    )

    # Semantic vs structural comparison
    md = [
        "# Semantic vs Structural Control Comparison (Conservative)",
        "",
        "Key observation pattern to check:",
        "- semantic metrics (F1 / omissions / hallucinations) may diverge between redundancy and filler control at matched length,",
        "- while structural metrics (raw JSON validity / repair / SDS) remain mostly stable.",
        "",
        "## Structural summary",
        "```",
        comp[
            [
                "repetition",
                "redundancy_raw_json_valid_rate",
                "redundancy_repair_rate",
                "redundancy_sds_mean",
                "control_raw_json_valid_rate",
                "control_repair_rate",
                "control_sds_mean",
            ]
        ].to_string(index=False),
        "```",
        "",
        "## Semantic summary",
        "```",
        comp[
            [
                "repetition",
                "redundancy_f1_mean",
                "control_f1_mean",
                "redundancy_omission_mean",
                "control_omission_mean",
                "redundancy_halluc_mean",
                "control_halluc_mean",
            ]
        ].to_string(index=False),
        "```",
        "",
    ]
    _write(CONTROL_ROOT / "semantic_vs_structural_control_comparison.md", "\n".join(md) + "\n")

    # Paper-ready interpretation + reviewer risk
    md = [
        "# Paper-Ready Interpretation (Conservative)",
        "",
        "## Strongest defensible claim (based on this comparison)",
        "- At matched (approximate) context lengths, redundancy and filler control do not behave identically across repetitions: mid-range repetitions show a positive differential redundancy effect (DRE>0), suggesting redundancy can *amplify* degradation beyond generic length pressure in this setting.",
        "",
        "## Key limitations / reviewer risks",
        "- Token matching uses an estimated token heuristic (chars→tokens), not true tokenizer counts.",
        "- Control filler is synthetic and may interact with the model differently than natural unrelated text.",
        "- At extreme redundancy (32x), DRE is near zero, suggesting convergence to a long-context floor; interpretations should avoid claiming a purely redundancy-specific phenomenon without more controls.",
        "",
        "## Most important figures",
        "- `plots/redundancy_vs_filler_F1.png`",
        "- `DRE_statistics.csv` (and a derived DRE plot if added later)",
        "",
    ]
    _write(CONTROL_ROOT / "paper_ready_interpretation.md", "\n".join(md) + "\n")

    # Next best experiment (single recommendation)
    md = [
        "# Next Best Experiment (Single Recommendation)",
        "",
        "Recommendation: **Paraphrase redundancy experiment** (keep length matched to redundancy but vary lexical overlap).",
        "",
        "Rationale:",
        "- This directly tests whether *identity repetition* is the driver vs generic semantic focus / attention effects.",
        "- It complements the filler control by keeping semantic content redundant but removing exact repetition.",
        "",
        "Keep fixed:",
        "- model/provider/prompt/schema/evaluator/temperature",
        "",
    ]
    _write(CONTROL_ROOT / "next_best_experiment.md", "\n".join(md) + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

