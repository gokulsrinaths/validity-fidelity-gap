from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def _save_line_plot(df: pd.DataFrame, *, x: str, y: str, title: str, outpath: Path):
    plt.rcParams.update(
        {
            "figure.dpi": 120,
            "savefig.dpi": 400,
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.labelsize": 10,
            "legend.fontsize": 9,
        }
    )
    plt.figure(figsize=(6.5, 3.8))
    agg = df.groupby(x, as_index=False)[y].mean(numeric_only=True)
    plt.plot(agg[x], agg[y], marker="o", color="black", linewidth=1.5)
    plt.title(title, pad=10)
    plt.xlabel(x)
    plt.ylabel(y)
    plt.grid(True, alpha=0.25, linestyle="--", linewidth=0.7)
    outpath.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(outpath, dpi=400)
    plt.close()


def generate_plots(metrics_csv: Path, plots_dir: Path):
    df = pd.read_csv(metrics_csv)
    _save_line_plot(
        df, x="repetition", y="micro_f1", title="Repetition vs F1", outpath=plots_dir / "repetition_vs_f1.png"
    )
    _save_line_plot(
        df,
        x="repetition",
        y="hallucination_count",
        title="Repetition vs Hallucination Rate",
        outpath=plots_dir / "repetition_vs_hallucination_rate.png",
    )
    _save_line_plot(
        df,
        x="repetition",
        y="omission_count",
        title="Repetition vs Omission Rate",
        outpath=plots_dir / "repetition_vs_omission_rate.png",
    )
    _save_line_plot(
        df,
        x="repetition",
        y="drift_score",
        title="Repetition vs Redundancy Drift",
        outpath=plots_dir / "repetition_vs_drift.png",
    )


def generate_structural_plots(structural_csv: Path, plots_dir: Path):
    df = pd.read_csv(structural_csv)
    _save_line_plot(
        df,
        x="repetition",
        y="raw_valid_json",
        title="Repetition vs Raw JSON Validity",
        outpath=plots_dir / "repetition_vs_raw_json_validity.png",
    )
    _save_line_plot(
        df,
        x="repetition",
        y="repair_needed",
        title="Repetition vs Repair Frequency",
        outpath=plots_dir / "repetition_vs_repair_frequency.png",
    )
    _save_line_plot(
        df,
        x="repetition",
        y="structural_drift_score",
        title="Repetition vs Structural Drift Score",
        outpath=plots_dir / "repetition_vs_structural_drift_score.png",
    )


def generate_variance_plots(variance_csv: Path, plots_dir: Path):
    df = pd.read_csv(variance_csv)
    _save_line_plot(
        df,
        x="repetition",
        y="semantic_pairwise_jaccard_distance_mean",
        title="Repetition vs Output Variance (Semantic)",
        outpath=plots_dir / "repetition_vs_output_variance.png",
    )
