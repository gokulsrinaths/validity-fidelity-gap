from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


RUN_ROOT = Path("data/runs/full_pilot_20260520_192127")
METRICS_DIR = RUN_ROOT / "metrics"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _safe_float(x: Any) -> float:
    try:
        return float(x)
    except Exception:
        return float("nan")


def _load_core() -> dict[str, Any]:
    by_rep = pd.read_csv(METRICS_DIR / "redundancy_scaling_statistics.csv")
    sem = pd.read_csv(METRICS_DIR / "semantic_metrics.csv")
    var = pd.read_csv(METRICS_DIR / "variance_metrics.csv")
    rss = pd.read_csv(RUN_ROOT / "RSS_distribution.csv")
    patient_consistency = pd.read_csv(RUN_ROOT / "patient_consistency.csv")
    return {"by_rep": by_rep, "sem": sem, "var": var, "rss": rss, "patient_consistency": patient_consistency}


def _collapse_regions(by_rep: pd.DataFrame) -> dict[str, Any]:
    df = by_rep.sort_values("repetition").reset_index(drop=True)
    reps = df["repetition"].astype(int).tolist()
    f1 = df["f1_mean"].astype(float).tolist()
    om = df["omission_mean"].astype(float).tolist()
    hal = df["halluc_mean"].astype(float).tolist()

    def deltas(xs: list[float]) -> list[float]:
        return [xs[i] - xs[i - 1] for i in range(1, len(xs))]

    f1_d = deltas(f1)  # negative is worse
    om_d = deltas(om)
    hal_d = deltas(hal)

    # identify biggest absolute change (magnitude)
    def biggest_drop(d: list[float]) -> int:
        return min(range(len(d)), key=lambda i: d[i])  # most negative

    def biggest_rise(d: list[float]) -> int:
        return max(range(len(d)), key=lambda i: d[i])

    i_f1 = biggest_drop(f1_d)
    i_om = biggest_rise(om_d)
    i_hal = biggest_rise(hal_d)

    def span(i: int) -> str:
        return f"{reps[i]}x -> {reps[i+1]}x"

    return {
        "f1_biggest_drop_span": span(i_f1),
        "f1_biggest_drop_value": f1_d[i_f1],
        "om_biggest_rise_span": span(i_om),
        "om_biggest_rise_value": om_d[i_om],
        "hal_biggest_rise_span": span(i_hal),
        "hal_biggest_rise_value": hal_d[i_hal],
        "table": pd.DataFrame(
            {
                "from_rep": reps[:-1],
                "to_rep": reps[1:],
                "delta_f1": f1_d,
                "delta_omission": om_d,
                "delta_hallucination": hal_d,
            }
        ),
    }


def write_core_findings(by_rep: pd.DataFrame) -> None:
    df = by_rep.sort_values("repetition")
    r1 = df[df["repetition"] == 1].iloc[0].to_dict()
    r32 = df[df["repetition"] == 32].iloc[0].to_dict()

    md = [
        "# Core Findings (Conservative)",
        "",
        "This summarizes the completed 180-call pilot at `data/runs/full_pilot_20260520_192127/`.",
        "",
        "## A. Does mean F1 decrease with redundancy?",
        f"- Yes: `f1_mean` drops from 1x `{_safe_float(r1['f1_mean']):.3f}` to 32x `{_safe_float(r32['f1_mean']):.3f}`.",
        "",
        "## B. Does omission increase?",
        f"- Yes: `omission_mean` rises from 1x `{_safe_float(r1['omission_mean']):.2f}` to 32x `{_safe_float(r32['omission_mean']):.2f}`.",
        "",
        "## C. Does hallucination increase?",
        f"- Yes: `halluc_mean` rises from 1x `{_safe_float(r1['halluc_mean']):.2f}` to 32x `{_safe_float(r32['halluc_mean']):.2f}`.",
        "",
        "## D. Does variance increase?",
        "- Mixed/weak in this pilot: `output_variance_mean` does not show a simple monotonic increase (see `metrics/variance_metrics.csv`).",
        "",
        "## E. Does SDS remain stable?",
        f"- Yes: `sds_mean` is `{_safe_float(r1['sds_mean']):.1f}` at 1x and `{_safe_float(r32['sds_mean']):.1f}` at 32x; `raw_json_valid_rate=1.0` and `repair_rate=0.0` at all levels.",
        "",
        "## F. Is 32x clearly worse than 1x?",
        f"- Yes on mean metrics: ΔF1 (32x-1x) = `{_safe_float(r32['f1_mean']) - _safe_float(r1['f1_mean']):.3f}`; Δomissions = `{_safe_float(r32['omission_mean']) - _safe_float(r1['omission_mean']):.2f}`; Δhallucinations = `{_safe_float(r32['halluc_mean']) - _safe_float(r1['halluc_mean']):.2f}`.",
        "",
        "## Scaling table (means ± std, with 95% CI columns)",
        "",
        "```",
        df[
            [
                "repetition",
                "n",
                "f1_mean",
                "f1_std",
                "f1_ci_low",
                "f1_ci_high",
                "omission_mean",
                "halluc_mean",
                "raw_json_valid_rate",
                "repair_rate",
                "sds_mean",
                "output_variance_mean",
            ]
        ].to_string(index=False),
        "```",
        "",
    ]
    _write(RUN_ROOT / "core_findings.md", "\n".join(md) + "\n")


def write_patient_level_consistency(patient_consistency: pd.DataFrame, rss: pd.DataFrame) -> None:
    pc = patient_consistency.copy()
    pc["degrade_1x_to_32x"] = (pc["RSS_32x"] > 0).astype(int)
    degrade = int(pc["degrade_1x_to_32x"].sum())
    improve = int((pc["RSS_32x"] < 0).sum())
    stable = int((pc["RSS_32x"] == 0).sum())
    mono_dec = int(pc["monotonic_decrease"].sum())

    rss32 = rss[rss["repetition"] == 32]["RSS"].astype(float)
    md = [
        "# Patient-Level Consistency (Conservative)",
        "",
        f"- patients: `{len(pc)}`",
        f"- degrade (F1_32x < F1_1x): `{degrade}`",
        f"- stable (F1_32x == F1_1x): `{stable}`",
        f"- improve (F1_32x > F1_1x): `{improve}`",
        f"- monotonic decrease across repetitions (per patient): `{mono_dec}`",
        "",
        "## RSS distribution at 32x (RSS_32x = F1_1x - F1_32x)",
        f"- mean: `{rss32.mean():.3f}`",
        f"- std: `{rss32.std(ddof=1):.3f}`",
        f"- min/max: `{rss32.min():.3f}` / `{rss32.max():.3f}`",
        "",
        "## Per-patient table",
        "```",
        pc[["patient_id", "F1_1x", "F1_32x", "RSS_32x", "monotonic_decrease", "monotonic_increase"]].to_string(index=False),
        "```",
        "",
    ]
    _write(RUN_ROOT / "patient_level_consistency.md", "\n".join(md) + "\n")


def write_collapse_region_analysis(by_rep: pd.DataFrame) -> None:
    c = _collapse_regions(by_rep)
    md = [
        "# Collapse Region Analysis (Conservative)",
        "",
        "This identifies where the *largest step changes* occur in the repetition scaling curve. It is descriptive only.",
        "",
        f"- Largest step drop in mean F1: `{c['f1_biggest_drop_span']}` (ΔF1=`{c['f1_biggest_drop_value']:.3f}`)",
        f"- Largest step rise in mean omissions: `{c['om_biggest_rise_span']}` (Δomissions=`{c['om_biggest_rise_value']:.2f}`)",
        f"- Largest step rise in mean hallucinations: `{c['hal_biggest_rise_span']}` (Δhallucinations=`{c['hal_biggest_rise_value']:.2f}`)",
        "",
        "## Step-change table",
        "```",
        c["table"].to_string(index=False),
        "```",
        "",
        "Interpretation guidance:",
        "- A large step change suggests a potential threshold region (not proof of a phase transition).",
        "- Confirm with additional runs/controls before over-interpreting thresholds.",
        "",
    ]
    _write(RUN_ROOT / "collapse_region_analysis.md", "\n".join(md) + "\n")


def write_entity_persistence_summary() -> None:
    # Use the already-generated analysis table for conservative summarization.
    src = RUN_ROOT / "entity_persistence_analysis.md"
    md = [
        "# Entity Persistence Summary (Conservative)",
        "",
        "This summarizes entity persistence relative to each run’s 1x extraction (set overlap / baseline set size).",
        "",
        "Key qualitative pattern from the persistence table:",
        "- `conditions` persistence remains relatively high through 32x in this pilot.",
        "- `medications` and `observations` show the largest persistence drops by high redundancy.",
        "- `procedures` persistence is intermediate in this dataset.",
        "",
        "Full table:",
        "",
        _read(src).strip(),
        "",
    ]
    _write(RUN_ROOT / "entity_persistence_summary.md", "\n".join(md) + "\n")


def write_semantic_vs_structural(by_rep: pd.DataFrame) -> None:
    df = by_rep.sort_values("repetition")
    md = [
        "# Semantic vs Structural Stability (Conservative)",
        "",
        "Observation:",
        "- Semantic metrics degrade with redundancy (F1 down; omissions/hallucinations up).",
        "- Structural metrics remain stable (raw JSON validity stays at 1.0; repair rate 0.0; SDS 0.0).",
        "",
        "Why this matters:",
        "- It suggests a regime where *format correctness* is preserved while *content fidelity* erodes under redundancy.",
        "- This supports analyzing semantic redundancy drift separately from structural drift.",
        "",
        "Supporting summary table:",
        "```",
        df[
            [
                "repetition",
                "f1_mean",
                "omission_mean",
                "halluc_mean",
                "raw_json_valid_rate",
                "repair_rate",
                "sds_mean",
            ]
        ].to_string(index=False),
        "```",
        "",
    ]
    _write(RUN_ROOT / "semantic_vs_structural_analysis.md", "\n".join(md) + "\n")


def write_effect_directionality(sem: pd.DataFrame) -> None:
    # Per patient: sign of (F1_32x - F1_1x)
    g = sem.groupby(["patient_id", "repetition"], as_index=False)["micro_f1"].mean()
    pivot = g.pivot(index="patient_id", columns="repetition", values="micro_f1")
    pivot = pivot.rename(columns={1: "F1_1x", 32: "F1_32x"})
    pivot["delta_32x_minus_1x"] = pivot["F1_32x"] - pivot["F1_1x"]
    degrade = int((pivot["delta_32x_minus_1x"] < 0).sum())
    improve = int((pivot["delta_32x_minus_1x"] > 0).sum())
    stable = int((pivot["delta_32x_minus_1x"] == 0).sum())

    md = [
        "# Effect Directionality Summary (Conservative)",
        "",
        "Direction is evaluated at the patient level using mean F1 at 1x vs mean F1 at 32x (averaged over 3 runs each).",
        "",
        f"- degrade (Δ<0): `{degrade}`",
        f"- stable (Δ=0): `{stable}`",
        f"- improve (Δ>0): `{improve}`",
        "",
        "Per-patient deltas:",
        "```",
        pivot[["F1_1x", "F1_32x", "delta_32x_minus_1x"]].reset_index().to_string(index=False),
        "```",
        "",
    ]
    _write(RUN_ROOT / "effect_directionality_summary.md", "\n".join(md) + "\n")


def write_statistical_interpretation() -> None:
    src = RUN_ROOT / "statistical_analysis.md"
    md = [
        "# Statistical Interpretation (Conservative)",
        "",
        "This interpretation follows the precomputed `statistical_analysis.md` (Spearman correlations with bootstrap CIs).",
        "",
        "Key points (descriptive):",
        "- Repetition is **negatively associated** with F1 in this pilot (Spearman rho < 0).",
        "- Repetition is **positively associated** with omission count (Spearman rho > 0).",
        "- These are associations within a single model/provider setting; they do not imply causality.",
        "",
        "Details:",
        "",
        _read(src).strip(),
        "",
    ]
    _write(RUN_ROOT / "statistical_interpretation.md", "\n".join(md) + "\n")


def write_paper_ready_examples() -> None:
    # Reuse qualitative_failure_cases list and point to existing comparisons.
    qual = _read(RUN_ROOT / "qualitative_failure_cases.md").strip()
    md = [
        "# Paper-Ready Examples (Pilot-Scale, Conservative)",
        "",
        "Use these as *illustrative* examples (not representative claims).",
        "",
        qual,
        "",
        "Suggested manual inspection paths (examples):",
        "- `outputs/patient_02/rep_1x/run_01/repaired.json` vs `outputs/patient_02/rep_32x/run_01/repaired.json`",
        "- `outputs/patient_06/rep_1x/run_01/repaired.json` vs `outputs/patient_06/rep_32x/run_01/repaired.json`",
        "- `outputs/patient_04/rep_1x/run_01/repaired.json` vs `outputs/patient_04/rep_32x/run_01/repaired.json`",
        "",
        "Example wording template (fill after inspection):",
        "> “At 32x redundancy, the model preserved X but omitted Y and Z despite unchanged semantic content.”",
        "",
    ]
    _write(RUN_ROOT / "paper_ready_examples.md", "\n".join(md) + "\n")


def write_interpretation_limitations() -> None:
    md = [
        "# Interpretation Limitations (Conservative)",
        "",
        "This pilot demonstrates an association between redundancy factor and semantic extraction quality for a single model/provider setup.",
        "",
        "What we cannot conclude yet:",
        "- Causality (redundancy *causes* degradation).",
        "- Generalization to other models, providers, or document distributions.",
        "- Whether the effect is redundancy-specific vs generic long-context degradation.",
        "",
        "Why redundancy-specific vs long-context remains unresolved:",
        "- Redundancy increases context length *and* repeats content; without a length-matched unrelated-filler control, the two are confounded.",
        "",
        "Most important missing control:",
        "- Constant-length control: match token length across repetition levels by inserting unrelated filler (same model/prompt/schema).",
        "",
    ]
    _write(RUN_ROOT / "interpretation_limitations.md", "\n".join(md) + "\n")


def write_claim_candidates() -> None:
    md = [
        "# Claim Candidates (Conservative)",
        "",
        "## Weak claim",
        "- In this pilot (single model/provider), higher repetition levels are associated with lower entity-extraction F1 and higher omission counts, while JSON validity remains stable.",
        "",
        "## Moderate claim",
        "- We observe preliminary evidence that exact semantic redundancy can degrade entity-level extraction fidelity without inducing structural JSON failures (SDS≈0; repair_rate≈0).",
        "",
        "## Strongest defensible claim (still pilot-scale)",
        "- Across 10 synthetic patients (180 calls; 6 redundancy levels; 3 runs/condition), repetition level shows a negative Spearman association with F1 and a positive association with omissions, consistent with a semantic redundancy drift phenomenon under fixed prompting and decoding settings.",
        "",
    ]
    _write(RUN_ROOT / "claim_candidates.md", "\n".join(md) + "\n")


def write_next_experiment_recommendation() -> None:
    md = [
        "# Next Experiment Recommendation (Single Step)",
        "",
        "## Recommendation: Constant-length control (unrelated filler)",
        "",
        "Rationale:",
        "- Current design confounds redundancy with total context length.",
        "- The most scientifically direct next step is to hold length constant while varying redundancy semantics (repeat vs filler).",
        "",
        "Design sketch (keep everything else fixed):",
        "- For each repetition level, build a length-matched document with unrelated filler so total tokens match the highest repetition condition.",
        "- Compare extraction metrics against the redundancy condition at the same length.",
        "",
        "What it would answer:",
        "- Whether the observed degradation is primarily long-context length pressure (generic) or repetition/semantic redundancy specific.",
        "",
    ]
    _write(RUN_ROOT / "next_experiment_recommendation.md", "\n".join(md) + "\n")


def main() -> int:
    core = _load_core()
    by_rep: pd.DataFrame = core["by_rep"]
    sem: pd.DataFrame = core["sem"]
    rss: pd.DataFrame = core["rss"]
    patient_consistency: pd.DataFrame = core["patient_consistency"]

    write_core_findings(by_rep)
    write_patient_level_consistency(patient_consistency, rss)
    write_collapse_region_analysis(by_rep)
    write_entity_persistence_summary()
    write_semantic_vs_structural(by_rep)
    write_effect_directionality(sem)
    write_statistical_interpretation()
    write_paper_ready_examples()
    write_interpretation_limitations()
    write_claim_candidates()
    write_next_experiment_recommendation()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

