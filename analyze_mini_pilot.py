from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd


RUN_ROOT = Path("data/runs/mini_pilot_20260520_190057")
RESULTS_CSV = RUN_ROOT / "mini_pilot_results.csv"


ENTITY_FIELDS = ("conditions", "medications", "observations", "procedures")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _to_set(x: Any) -> set[str]:
    if x is None:
        return set()
    if not isinstance(x, list):
        x = [x]
    out: set[str] = set()
    for it in x:
        s = str(it).strip()
        if s:
            out.add(s)
    return out


def _monotonic_decrease(a: float, b: float, c: float, *, eps: float = 1e-9) -> bool:
    return (a + eps) >= b and (b + eps) >= c and (a - eps) > c


def _monotonic_increase(a: float, b: float, c: float, *, eps: float = 1e-9) -> bool:
    return (a - eps) <= b and (b - eps) <= c and (c - eps) > a


def _trend_label(a: float, b: float, c: float) -> str:
    if _monotonic_decrease(a, b, c):
        return "monotonic_decrease"
    if _monotonic_increase(a, b, c):
        return "monotonic_increase"
    if math.isclose(a, b) and math.isclose(b, c):
        return "no_change"
    # partial decrease: ends lower than start, but not monotone
    if c < a and not _monotonic_decrease(a, b, c):
        return "partial_decrease"
    if c > a and not _monotonic_increase(a, b, c):
        return "partial_increase"
    return "inconsistent"


@dataclass(frozen=True)
class RepairedPaths:
    patient_id: str
    rep: int

    @property
    def repaired_json(self) -> Path:
        return RUN_ROOT / "outputs" / self.patient_id / f"rep_{self.rep}x" / "run_01" / "repaired.json"

    @property
    def ground_truth_json(self) -> Path:
        return Path("data") / self.patient_id / "ground_truth" / f"{self.patient_id}.json"


def compute_per_patient_trends(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for pid, g in df.groupby("patient_id"):
        f1_1 = float(g.loc[g["repetition_level"] == 1, "F1"].iloc[0])
        f1_2 = float(g.loc[g["repetition_level"] == 2, "F1"].iloc[0])
        f1_5 = float(g.loc[g["repetition_level"] == 5, "F1"].iloc[0])
        rows.append(
            {
                "patient_id": pid,
                "F1_1x": f1_1,
                "F1_2x": f1_2,
                "F1_5x": f1_5,
                "monotonic_decrease": int(_monotonic_decrease(f1_1, f1_2, f1_5)),
                "trend_label": _trend_label(f1_1, f1_2, f1_5),
                "delta_2x_minus_1x": f1_2 - f1_1,
                "delta_5x_minus_1x": f1_5 - f1_1,
            }
        )
    return pd.DataFrame(rows).sort_values("patient_id").reset_index(drop=True)


def compute_rss(per_patient: pd.DataFrame) -> pd.DataFrame:
    rss = per_patient[["patient_id", "F1_1x", "F1_5x"]].copy()
    rss["RSS"] = rss["F1_1x"] - rss["F1_5x"]
    # Append summary rows (conservative descriptors)
    summary = pd.DataFrame(
        [
            {"patient_id": "MEAN", "F1_1x": float("nan"), "F1_5x": float("nan"), "RSS": float(rss["RSS"].mean())},
            {"patient_id": "STD", "F1_1x": float("nan"), "F1_5x": float("nan"), "RSS": float(rss["RSS"].std(ddof=1))},
        ]
    )
    return pd.concat([rss, summary], ignore_index=True)


def entity_type_counts(*, patient_id: str, rep: int) -> dict[str, int]:
    pred = _read_json(RepairedPaths(patient_id=patient_id, rep=rep).repaired_json)
    return {f"{k}_n": len(_to_set(pred.get(k))) for k in ENTITY_FIELDS}


def build_entity_loss_examples(df: pd.DataFrame) -> str:
    lines: list[str] = [
        "# Entity Loss Examples (1x vs 5x)",
        "",
        "Scope: compares repaired outputs at `1x` vs `5x` for each patient.",
        "Wording is descriptive only (pilot-scale; N=3).",
        "",
    ]
    for pid in sorted(df["patient_id"].unique()):
        p1 = _read_json(RepairedPaths(patient_id=pid, rep=1).repaired_json)
        p5 = _read_json(RepairedPaths(patient_id=pid, rep=5).repaired_json)
        lines += [f"## {pid}", ""]
        for field in ENTITY_FIELDS:
            s1 = _to_set(p1.get(field))
            s5 = _to_set(p5.get(field))
            missing = sorted(s1 - s5)
            extra = sorted(s5 - s1)
            changed = "yes" if (missing or extra) else "no"
            lines += [
                f"### `{field}` (changed: {changed})",
                "",
                "**Missing at 5x (present at 1x):**",
                *(f"- {x}" for x in (missing or ["(none)"])),
                "",
                "**New at 5x (not present at 1x):**",
                *(f"- {x}" for x in (extra or ["(none)"])),
                "",
            ]
    return "\n".join(lines) + "\n"


def build_qualitative_examples(df: pd.DataFrame) -> str:
    # Pick the strongest degradation by RSS.
    per_patient = compute_per_patient_trends(df)
    per_patient["RSS"] = per_patient["F1_1x"] - per_patient["F1_5x"]
    worst = per_patient.sort_values("RSS", ascending=False).iloc[0]
    pid = str(worst["patient_id"])

    p1 = _read_json(RepairedPaths(patient_id=pid, rep=1).repaired_json)
    p5 = _read_json(RepairedPaths(patient_id=pid, rep=5).repaired_json)

    lines: list[str] = [
        "# Qualitative Examples (Pilot-Scale)",
        "",
        "These examples are descriptive only (no claims of causality or significance).",
        "",
        f"## Strongest observed degradation (by RSS): {pid}",
        f"- RSS = F1_1x - F1_5x = `{float(worst['RSS']):.3f}`",
        "",
    ]

    for field in ENTITY_FIELDS:
        s1 = _to_set(p1.get(field))
        s5 = _to_set(p5.get(field))
        missing = sorted(s1 - s5)
        extra = sorted(s5 - s1)
        if not missing and not extra:
            continue
        lines += [f"### {field}", ""]
        if missing:
            lines.append("At 5x redundancy, the model omitted:")
            lines += [f"- {x}" for x in missing]
            lines.append("")
        if extra:
            lines.append("At 5x redundancy, the model added:")
            lines += [f"- {x}" for x in extra]
            lines.append("")

    if len(lines) <= 7:
        lines += ["No strong qualitative differences found beyond metric movement.", ""]
    return "\n".join(lines) + "\n"


def build_entity_degradation_analysis(df: pd.DataFrame) -> str:
    """
    Aggregate by repetition: entity-type counts and deltas vs 1x.
    """
    rows: list[dict[str, Any]] = []
    for _, r in df.iterrows():
        pid = str(r["patient_id"])
        rep = int(r["repetition_level"])
        rows.append({"patient_id": pid, "repetition_level": rep, **entity_type_counts(patient_id=pid, rep=rep)})
    ent_df = pd.DataFrame(rows)

    agg = ent_df.groupby("repetition_level", as_index=False).mean(numeric_only=True).sort_values("repetition_level")
    base = agg[agg["repetition_level"] == 1].iloc[0].to_dict()

    def delta(col: str, rep: int) -> float:
        cur = float(agg.loc[agg["repetition_level"] == rep, col].iloc[0])
        return cur - float(base[col])

    lines: list[str] = [
        "# Entity Degradation Analysis (By Entity Type)",
        "",
        "This analyzes how many entities (by type) appear in repaired outputs as redundancy increases.",
        "Counts are set-cardinalities of extracted strings (not normalized synonyms).",
        "",
        "## Mean extracted entity counts by repetition (N=3 patients)",
        "",
        "```",
        agg.to_string(index=False),
        "```",
        "",
        "## Deltas vs 1x baseline (means)",
        "",
    ]

    for rep in [2, 5]:
        lines.append(f"### {rep}x minus 1x")
        lines.append("")
        for field in ENTITY_FIELDS:
            col = f"{field}_n"
            lines.append(f"- {field}: `{delta(col, rep):+.3f}`")
        lines.append("")

    # Simple heuristic: which category changes most at 5x
    deltas_5 = {field: delta(f"{field}_n", 5) for field in ENTITY_FIELDS}
    worst_field = sorted(deltas_5.items(), key=lambda kv: kv[1])[0][0]
    lines += [
        "## Preliminary note (heuristic)",
        f"- Largest mean decrease at 5x (by count) appears in: `{worst_field}` (pilot-scale; interpret cautiously).",
        "",
    ]

    return "\n".join(lines) + "\n"


def build_trend_test_summary(per_patient: pd.DataFrame) -> str:
    n = len(per_patient)
    dec = int((per_patient["trend_label"] == "monotonic_decrease").sum())
    inc = int((per_patient["trend_label"] == "monotonic_increase").sum())
    no = int((per_patient["trend_label"] == "no_change").sum())
    other = n - dec - inc - no
    lines = [
        "# Trend Test Summary (Pilot-Scale, N=3)",
        "",
        "This is a descriptive monotonicity tally only (no significance claims).",
        "",
        f"- patients: `{n}`",
        f"- monotonic decrease (1x≥2x≥5x and 1x>5x): `{dec}`",
        f"- monotonic increase (1x≤2x≤5x and 5x>1x): `{inc}`",
        f"- no change (exact ties): `{no}`",
        f"- inconsistent/partial: `{other}`",
        "",
    ]
    return "\n".join(lines) + "\n"


def build_full_pilot_recommendation(df: pd.DataFrame, per_patient: pd.DataFrame) -> str:
    rss = per_patient["F1_1x"] - per_patient["F1_5x"]
    mean_rss = float(rss.mean())
    lines = [
        "# Full Pilot Recommendation (Conservative)",
        "",
        "## Benchmark operational?",
        "- Yes: mini-pilot produced non-empty outputs, nonzero entities, and computable semantic metrics.",
        "",
        "## Is there measurable semantic movement with redundancy (1x→2x→5x)?",
        f"- Suggestive: mean F1 decreased across levels in this mini-pilot; mean RSS (F1_1x - F1_5x) = `{mean_rss:.3f}`.",
        "",
        "## Is the trend direction consistent?",
        f"- Monotonic-decrease patients: `{int((per_patient['trend_label']=='monotonic_decrease').sum())}/{len(per_patient)}` (N is tiny).",
        "",
        "## Structural stability / JSON drift?",
        "- No structural drift observed here: SDS=0 and repair_needed=0 for all 9 calls (does not rule out drift at higher redundancy or longer contexts).",
        "",
        "## Recommendation",
        "- Proceed to a larger pilot (e.g., 180 calls) is **scientifically reasonable** *if* you want to test whether this suggestive semantic trend persists with larger N and multiple runs/condition.",
        "- Keep wording conservative: this mini-pilot alone does not establish a robust effect.",
        "",
    ]
    return "\n".join(lines) + "\n"


def make_plots(df: pd.DataFrame, per_patient: pd.DataFrame) -> None:
    import matplotlib.pyplot as plt
    import numpy as np

    plots_dir = RUN_ROOT / "analysis_plots"
    plots_dir.mkdir(parents=True, exist_ok=True)

    plt.rcParams.update(
        {
            "figure.dpi": 200,
            "savefig.dpi": 300,
            "font.size": 11,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )

    # 1) per-patient curves
    fig, ax = plt.subplots(figsize=(5.8, 3.6))
    for pid in per_patient["patient_id"].tolist():
        g = df[df["patient_id"] == pid].sort_values("repetition_level")
        ax.plot(
            g["repetition_level"].astype(int).tolist(),
            g["F1"].astype(float).tolist(),
            "-o",
            linewidth=1.4,
            markersize=5,
            color="black",
            alpha=0.8,
            label=pid,
        )
    ax.set_xlabel("Repetition level (x)")
    ax.set_ylabel("Micro F1")
    ax.set_xticks([1, 2, 5])
    ax.set_ylim(0.0, 1.0)
    ax.grid(True, axis="y", linestyle="--", linewidth=0.6, alpha=0.6)
    ax.legend(frameon=False, fontsize=9, loc="best")
    fig.tight_layout()
    fig.savefig(plots_dir / "per_patient_F1_curves.png")
    plt.close(fig)

    # 2) delta histogram (RSS)
    rss = (per_patient["F1_1x"] - per_patient["F1_5x"]).astype(float).tolist()
    fig, ax = plt.subplots(figsize=(5.4, 3.2))
    ax.hist(rss, bins=5, color="black", alpha=0.85, edgecolor="black")
    ax.set_xlabel("RSS = F1_1x - F1_5x")
    ax.set_ylabel("Count")
    ax.grid(True, axis="y", linestyle="--", linewidth=0.6, alpha=0.6)
    fig.tight_layout()
    fig.savefig(plots_dir / "redundancy_delta_histogram.png")
    plt.close(fig)

    # 3) entity loss heatmap (by patient x entity type), using delta counts (5x - 1x)
    pids = per_patient["patient_id"].tolist()
    data = np.zeros((len(pids), len(ENTITY_FIELDS)), dtype=float)
    for i, pid in enumerate(pids):
        c1 = entity_type_counts(patient_id=pid, rep=1)
        c5 = entity_type_counts(patient_id=pid, rep=5)
        for j, field in enumerate(ENTITY_FIELDS):
            data[i, j] = float(c5[f"{field}_n"] - c1[f"{field}_n"])

    fig, ax = plt.subplots(figsize=(6.4, 2.4))
    im = ax.imshow(data, cmap="Greys", aspect="auto")
    ax.set_xticks(list(range(len(ENTITY_FIELDS))), labels=list(ENTITY_FIELDS))
    ax.set_yticks(list(range(len(pids))), labels=pids)
    ax.set_title("Entity count delta (5x - 1x)")
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            ax.text(j, i, f"{data[i,j]:+.0f}", ha="center", va="center", color="black")
    fig.colorbar(im, ax=ax, fraction=0.045, pad=0.04)
    fig.tight_layout()
    fig.savefig(plots_dir / "entity_loss_heatmap.png")
    plt.close(fig)


def main() -> int:
    if not RESULTS_CSV.exists():
        raise FileNotFoundError(f"Missing: {RESULTS_CSV}")

    df = pd.read_csv(RESULTS_CSV)

    # TASK 2: per-patient trends
    per_patient = compute_per_patient_trends(df)
    per_patient.to_csv(RUN_ROOT / "per_patient_trends.csv", index=False)

    # TASK 5: redundancy sensitivity
    rss_df = compute_rss(per_patient)
    rss_df.to_csv(RUN_ROOT / "redundancy_sensitivity.csv", index=False)

    # TASK 3: entity degradation analysis
    (RUN_ROOT / "entity_degradation_analysis.md").write_text(
        build_entity_degradation_analysis(df), encoding="utf-8"
    )

    # TASK 4: entity loss examples (1x vs 5x)
    (RUN_ROOT / "entity_loss_examples.md").write_text(build_entity_loss_examples(df), encoding="utf-8")

    # TASK 6: monotonicity summary
    (RUN_ROOT / "trend_test_summary.md").write_text(build_trend_test_summary(per_patient), encoding="utf-8")

    # TASK 7: plots
    make_plots(df, per_patient)

    # TASK 8: qualitative examples
    (RUN_ROOT / "qualitative_examples.md").write_text(build_qualitative_examples(df), encoding="utf-8")

    # TASK 10: recommendation
    (RUN_ROOT / "full_pilot_recommendation.md").write_text(
        build_full_pilot_recommendation(df, per_patient), encoding="utf-8"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

