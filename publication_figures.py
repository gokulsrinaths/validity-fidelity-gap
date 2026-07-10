"""
Publication-quality figure generation for EMNLP submission.

Generates all 8 figures at ACL two-column format specs:
  - Single-column width: 3.33 in
  - Double-column width: 6.97 in
  - DPI: 300
  - Font: 9pt labels, 8pt ticks/legend (matches ACL 11pt body text at column scale)
  - Colorblind-safe palette (ColorBrewer)
  - No default matplotlib chrome

Run: python publication_figures.py
Outputs to: Paper/.../latex/figures/
"""

from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.lines import Line2D

# ── Output directory ──────────────────────────────────────────────────────────
FIG_DIR = Path("Paper/Association_for_Computational_Linguistics__ACL__conference__3_/latex/figures")
FIG_DIR.mkdir(parents=True, exist_ok=True)

# ── ACL column widths (inches) ────────────────────────────────────────────────
COL1 = 3.33   # single column
COL2 = 6.97   # double column (full width)
ROW_H = 2.2   # standard row height for single-col figures
ROW_H2 = 2.6  # taller variant

# ── Publication rcParams ──────────────────────────────────────────────────────
matplotlib.rcParams.update({
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.04,
    "font.family": "serif",
    "font.serif": ["DejaVu Serif", "Times New Roman", "Times", "serif"],
    "font.size": 8,
    "axes.titlesize": 9,
    "axes.labelsize": 9,
    "axes.linewidth": 0.8,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "xtick.major.width": 0.6,
    "ytick.major.width": 0.6,
    "xtick.major.size": 3,
    "ytick.major.size": 3,
    "legend.fontsize": 7.5,
    "legend.framealpha": 0.92,
    "legend.edgecolor": "0.7",
    "legend.borderpad": 0.4,
    "legend.labelspacing": 0.3,
    "lines.linewidth": 1.6,
    "lines.markersize": 5,
    "grid.linewidth": 0.5,
    "grid.alpha": 0.35,
    "grid.color": "#888888",
    "grid.linestyle": "--",
})

# ── Colorblind-safe palette (ColorBrewer RdBu) ────────────────────────────────
C_RED   = "#D6604D"   # redundancy / degradation
C_BLUE  = "#4393C3"   # filler / neutral / 8B
C_GREEN = "#4DAC26"   # Qwen / stable
C_GREY  = "#999999"   # secondary / 70B
C_DARK  = "#1A1A1A"   # single-series lines

# Entity type colors (colorblind-safe: Wong palette)
ENTITY_COLORS = {
    "conditions":   "#0072B2",   # blue
    "medications":  "#D55E00",   # vermillion
    "observations": "#009E73",   # green
    "procedures":   "#CC79A7",   # pink/purple
}
ENTITY_MARKERS = {
    "conditions":   "o",
    "medications":  "s",
    "observations": "^",
    "procedures":   "D",
}

# ── Helper ────────────────────────────────────────────────────────────────────
def despine(ax, top=True, right=True):
    if top:   ax.spines["top"].set_visible(False)
    if right: ax.spines["right"].set_visible(False)

def zero_line(ax, lw=0.8, color="#333333"):
    ax.axhline(0, color=color, linewidth=lw, zorder=1)

def save(name: str):
    path = FIG_DIR / name
    plt.savefig(path)
    plt.close()
    print(f"  Saved: {path.name}")


# ─────────────────────────────────────────────────────────────────────────────
# Fig 1 — Redundancy scaling F1 (8B pilot, with CI + threshold annotation)
# ─────────────────────────────────────────────────────────────────────────────
def fig_repetition_vs_f1():
    df = pd.read_csv("data/runs/full_pilot_20260520_192127/metrics/redundancy_scaling_statistics.csv")
    reps = df["repetition"].values
    f1   = df["f1_mean"].values
    lo   = df["f1_ci_low"].values
    hi   = df["f1_ci_high"].values

    # Use categorical (evenly-spaced) x positions so "1× 2× 5×" don't crowd
    xlabels = ["1×", "2×", "5×", "10×", "16×", "32×"]
    xs = np.arange(len(reps))

    fig, ax = plt.subplots(figsize=(COL1, ROW_H))
    ax.fill_between(xs, lo, hi, alpha=0.18, color=C_DARK, linewidth=0)
    ax.plot(xs, f1, color=C_DARK, marker="o", zorder=3, clip_on=False)

    # Highlight 2×→5× threshold segment in red
    idx2, idx5 = list(reps).index(2), list(reps).index(5)
    ax.plot(xs[idx2:idx5+1], f1[idx2:idx5+1], color=C_RED, linewidth=2.2, zorder=4)

    # Threshold annotation
    ax.annotate(
        "55% of total\ndegradation here",
        xy=(xs[idx5], f1[idx5]),
        xytext=(xs[idx5]+0.8, f1[idx5]+0.09),
        fontsize=7,
        arrowprops=dict(arrowstyle="->", color="#555555", lw=0.8),
        color="#333333", ha="left",
    )

    ax.set_xlabel("Redundancy level (×)")
    ax.set_ylabel("Micro-F1")
    ax.set_xticks(xs)
    ax.set_xticklabels(xlabels)
    ax.set_ylim(0.15, 0.62)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter("%.2f"))
    ax.grid(axis="y")
    despine(ax)
    fig.subplots_adjust(left=0.16, right=0.97, bottom=0.17, top=0.97)
    save("repetition_vs_F1.png")


# ─────────────────────────────────────────────────────────────────────────────
# Fig 2 — Redundancy vs filler F1 comparison (DRE gap annotated)
# ─────────────────────────────────────────────────────────────────────────────
def fig_redundancy_vs_filler():
    # Pilot run (redundancy)
    df_red = pd.read_csv("data/runs/full_pilot_20260520_192127/metrics/redundancy_scaling_statistics.csv")
    # Filler control — best available: use full_pilot_control stats
    # Load from the control run
    ctrl_path = "data/runs/full_pilot_control_20260520_235546/metrics/redundancy_scaling_statistics.csv"
    df_fill = pd.read_csv(ctrl_path)

    reps_r = df_red["repetition"].values
    reps_f = df_fill["repetition"].values
    shared = sorted(set(reps_r) & set(reps_f))
    f1_r_s = [df_red.loc[df_red.repetition==r, "f1_mean"].values[0] for r in shared]
    f1_f_s = [df_fill.loc[df_fill.repetition==r, "f1_mean"].values[0] for r in shared]

    xlabels2 = [f"{r}×" for r in shared]
    xs2 = np.arange(len(shared))

    fig, ax = plt.subplots(figsize=(COL1, ROW_H))

    # Shade DRE gap between 2× and 16×
    shade_idx = [i for i, r in enumerate(shared) if 2 <= r <= 16]
    ax.fill_between([xs2[i] for i in shade_idx],
                    [f1_r_s[i] for i in shade_idx],
                    [f1_f_s[i] for i in shade_idx],
                    alpha=0.12, color=C_RED, linewidth=0)

    ax.plot(xs2, f1_r_s, color=C_RED,  marker="o", label="Redundancy",            zorder=3)
    ax.plot(xs2, f1_f_s, color=C_BLUE, marker="s", linestyle="--", label="Length-matched filler", zorder=3)

    # DRE label
    i10 = shared.index(10)
    mid = (f1_r_s[i10] + f1_f_s[i10]) / 2
    ax.annotate("DRE gap", xy=(xs2[i10], mid), fontsize=7, color=C_RED,
                ha="center", va="center",
                bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="none", alpha=0.85))

    ax.set_xlabel("Redundancy level (×)")
    ax.set_ylabel("Micro-F1 (mean)")
    ax.set_xticks(xs2)
    ax.set_xticklabels(xlabels2)
    ax.set_ylim(0.15, 0.65)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter("%.2f"))
    ax.legend(loc="upper right", ncol=1)
    ax.grid(axis="y")
    despine(ax)
    fig.subplots_adjust(left=0.16, right=0.97, bottom=0.17, top=0.97)
    save("redundancy_vs_filler_F1.png")


# ─────────────────────────────────────────────────────────────────────────────
# Fig 3 — Cross-model DRE comparison
# ─────────────────────────────────────────────────────────────────────────────
def fig_model_dre():
    df = pd.read_csv("paper_artifacts/cross_model_DRE_combined.csv")

    models = {
        "LLaMA-8B (3-run full pilots)":  ("8B",       C_DARK,  "o",  "-",  1.8),
        "LLaMA-70B (midrange, 3 runs)":  ("70B",      C_BLUE,  "s",  "--", 1.4),
        "Qwen-72B (midrange, 3 runs)":   ("Qwen-72B", C_GREEN, "^",  ":",  1.4),
    }

    # Collect all unique repetition levels across models, use categorical positions
    all_reps_set = sorted(df["repetition"].unique())
    xlabels3 = [f"{r}×" for r in all_reps_set]
    rep_to_x = {r: i for i, r in enumerate(all_reps_set)}

    fig, ax = plt.subplots(figsize=(COL1, ROW_H2))

    for raw_label, (short, color, marker, ls, lw) in models.items():
        sub = df[df["model_label"] == raw_label].sort_values("repetition")
        if sub.empty:
            sub = df[df["model_label"].str.contains(short.replace("-",""), case=False)].sort_values("repetition")
        if sub.empty:
            continue
        xs3 = [rep_to_x[r] for r in sub["repetition"]]
        ax.plot(xs3, sub["DRE"].values,
                color=color, marker=marker, linestyle=ls, linewidth=lw,
                label=short, zorder=3, clip_on=False)

    zero_line(ax)
    ax.set_xlabel("Redundancy level (×)")
    ax.set_ylabel("DRE (redund. drop − filler drop)")
    ax.set_xticks(range(len(all_reps_set)))
    ax.set_xticklabels(xlabels3)
    ax.set_ylim(-0.02, 0.25)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter("%.2f"))
    ax.legend(loc="upper left", ncol=1)
    ax.grid(axis="y")
    despine(ax)
    fig.subplots_adjust(left=0.18, right=0.97, bottom=0.15, top=0.97)
    save("model_comparison_DRE.png")


# ─────────────────────────────────────────────────────────────────────────────
# Fig 4 — Entity-type persistence (appendix)
# ─────────────────────────────────────────────────────────────────────────────
def fig_entity_persistence():
    df = pd.read_csv("paper_artifacts/entity_persistence_fullpilot/entity_type_persistence_summary.csv")
    entity_types = ["conditions", "medications", "observations", "procedures"]
    label_map = {"conditions": "Conditions", "medications": "Medications",
                 "observations": "Observations", "procedures": "Procedures"}

    fig, ax = plt.subplots(figsize=(COL1, ROW_H2))

    ent_reps = [1, 2, 5, 10, 16, 32]
    rep_to_x4 = {r: i for i, r in enumerate(ent_reps)}
    for etype in entity_types:
        sub = df[df["entity_type"] == etype].sort_values("repetition")
        color  = ENTITY_COLORS[etype]
        marker = ENTITY_MARKERS[etype]
        xs4 = [rep_to_x4[r] for r in sub["repetition"]]
        ax.fill_between(xs4, sub["persistence_ci_low"], sub["persistence_ci_high"],
                        alpha=0.12, color=color, linewidth=0)
        ax.plot(xs4, sub["persistence_mean"],
                color=color, marker=marker, label=label_map[etype], zorder=3, clip_on=False)

    ax.set_xlabel("Redundancy level (×)")
    ax.set_ylabel("Persistence vs. 1× baseline")
    ent_reps = [1, 2, 5, 10, 16, 32]
    xlabels4 = ["1×", "2×", "5×", "10×", "16×", "32×"]
    rep_to_x4 = {r: i for i, r in enumerate(ent_reps)}
    ax.set_xticks(range(len(ent_reps)))
    ax.set_xticklabels(xlabels4)
    ax.set_ylim(-0.05, 1.08)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter("%.1f"))
    ax.legend(loc="lower left", ncol=2)
    ax.grid(axis="y")
    despine(ax)
    fig.subplots_adjust(left=0.17, right=0.97, bottom=0.15, top=0.97)
    save("entity_type_persistence_with_ci.png")


# ─────────────────────────────────────────────────────────────────────────────
# Fig 5 — Large-N DRE with bootstrap CI (appendix)
# ─────────────────────────────────────────────────────────────────────────────
def fig_largeN_dre():
    df = pd.read_csv("paper_artifacts/largeN_paired_effects/dre_bootstrap_summary.csv")
    reps = df["repetition"].values
    dre  = df["mean_dre"].values
    lo   = df["dre_ci_low"].values
    hi   = df["dre_ci_high"].values

    fig, ax = plt.subplots(figsize=(COL1, ROW_H))
    zero_line(ax)
    ax.fill_between(reps, lo, hi, alpha=0.18, color=C_DARK, linewidth=0)
    ax.plot(reps, dre, color=C_DARK, marker="o", zorder=3)

    # Annotate "CI excludes 0" at each point
    for r, d, l in zip(reps, dre, lo):
        if l > 0:
            ax.annotate("CI excl. 0", xy=(r, l - 0.005), fontsize=6.5,
                        ha="center", va="top", color="#444444")

    ax.set_xlabel("Redundancy level (×)")
    ax.set_ylabel("Mean DRE (95% CI)")
    ax.set_xticks(reps)
    ax.set_xticklabels([f"{r}×" for r in reps])
    ax.set_ylim(-0.01, 0.28)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter("%.2f"))
    ax.grid(axis="y")
    despine(ax)
    fig.subplots_adjust(left=0.17, right=0.97, bottom=0.17, top=0.97)
    save("largeN_dre_with_ci.png")


# ─────────────────────────────────────────────────────────────────────────────
# Fig 6 — Large-N paired F1 drop with CI (appendix)
# ─────────────────────────────────────────────────────────────────────────────
def fig_largeN_f1drop():
    df = pd.read_csv("paper_artifacts/largeN_paired_effects/paired_effects_bootstrap_summary.csv")
    df = df[df["metric"] == "F1_drop"]
    reps = df["repetition"].values
    mn   = df["mean"].values
    lo   = df["ci_low"].values
    hi   = df["ci_high"].values

    fig, ax = plt.subplots(figsize=(COL1, ROW_H))
    zero_line(ax)
    ax.fill_between(reps, lo, hi, alpha=0.18, color=C_DARK, linewidth=0)
    ax.plot(reps, mn, color=C_DARK, marker="o", zorder=3)

    ax.set_xlabel("Redundancy level (×)")
    ax.set_ylabel("Paired F1 drop (1× to r×), 95% CI")
    ax.set_xticks(reps)
    ax.set_xticklabels([f"{r}×" for r in reps])
    ax.set_ylim(0.08, 0.26)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter("%.2f"))
    ax.grid(axis="y")
    despine(ax)
    fig.subplots_adjust(left=0.17, right=0.97, bottom=0.17, top=0.97)
    save("largeN_paired_f1_drop_with_ci.png")


# ─────────────────────────────────────────────────────────────────────────────
# Fig 7 — Section-level DRE with CI (appendix)
# ─────────────────────────────────────────────────────────────────────────────
def fig_section_dre():
    df = pd.read_csv("paper_artifacts/section_redundancy_largeN/dre_bootstrap_summary.csv")
    df = df[df["condition"] == "DRE_section_vs_filler"]
    reps = df["repetition"].values
    dre  = df["mean_f1_drop"].values
    lo   = df["ci_low"].values
    hi   = df["ci_high"].values

    fig, ax = plt.subplots(figsize=(COL1, ROW_H))
    zero_line(ax)
    ax.fill_between(reps, lo, hi, alpha=0.18, color=C_DARK, linewidth=0)
    ax.plot(reps, dre, color=C_DARK, marker="o", zorder=3)

    # Annotate CI status per point
    labels = {5: "CI crosses 0", 10: "CI excl. 0", 16: "CI excl. 0"}
    offsets = {5: (0, -0.012), 10: (0, 0.008), 16: (0.3, 0.008)}
    for r, d, l_ci, h_ci in zip(reps, dre, lo, hi):
        txt = labels.get(r, "")
        ox, oy = offsets.get(r, (0, 0.008))
        ax.annotate(txt, xy=(r + ox, d + oy), fontsize=6.5,
                    ha="center", va="bottom", color="#444444")

    ax.set_xlabel("Redundancy level (×)")
    ax.set_ylabel("Section-level DRE (95% CI)")
    ax.set_xticks(reps)
    ax.set_xticklabels([f"{r}×" for r in reps])
    ax.set_ylim(-0.04, 0.14)
    ax.yaxis.set_major_formatter(matplotlib.ticker.FormatStrFormatter("%.2f"))
    ax.grid(axis="y")
    despine(ax)
    fig.subplots_adjust(left=0.18, right=0.97, bottom=0.17, top=0.97)
    save("section_redundancy_dre_with_ci.png")


# ─────────────────────────────────────────────────────────────────────────────
# Fig 8 — Large-N per-patient DRE distribution boxplot (appendix)
# ─────────────────────────────────────────────────────────────────────────────
def fig_largeN_boxplot():
    df = pd.read_csv("paper_artifacts/largeN_paired_effects/dre_by_patient.csv")
    reps = sorted(df["repetition"].unique())

    fig, ax = plt.subplots(figsize=(COL1, ROW_H))

    data = [df.loc[df["repetition"] == r, "DRE"].values for r in reps]
    bp = ax.boxplot(data, positions=range(len(reps)), widths=0.5,
                    patch_artist=True, notch=False,
                    medianprops=dict(color=C_DARK, linewidth=1.8),
                    boxprops=dict(facecolor="white", edgecolor=C_DARK, linewidth=0.9),
                    whiskerprops=dict(color=C_DARK, linewidth=0.9),
                    capprops=dict(color=C_DARK, linewidth=0.9),
                    flierprops=dict(marker="o", markerfacecolor=C_GREY,
                                    markeredgecolor=C_GREY, markersize=2.5, alpha=0.5))

    zero_line(ax)
    ax.set_xticks(range(len(reps)))
    ax.set_xticklabels([f"{r}×" for r in reps])
    ax.set_xlabel("Redundancy level (×)")
    ax.set_ylabel("Per-patient DRE")
    ax.grid(axis="y")
    despine(ax)
    fig.subplots_adjust(left=0.17, right=0.97, bottom=0.17, top=0.97)
    save("largeN_dre_distribution_boxplot.png")


# ─────────────────────────────────────────────────────────────────────────────
# Run all
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Generating publication figures...")
    fig_repetition_vs_f1()
    fig_redundancy_vs_filler()
    fig_model_dre()
    fig_entity_persistence()
    fig_largeN_dre()
    fig_largeN_f1drop()
    fig_section_dre()
    fig_largeN_boxplot()
    print("Done. All figures written to:", FIG_DIR)
