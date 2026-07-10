from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import matplotlib.pyplot as plt


RUNS = {
    "llama8b_full": Path("data/runs/full_pilot_control_20260520_235546"),  # has control_vs_redundancy + DRE
    "llama70b_rep3_mid": Path("data/runs/cross_model_llama70b_rep3_midrange"),
    "qwen72b_rep3_mid": Path("data/runs/cross_model_qwen72b_rep3_midrange"),
}


def _load_dre_for_model(run_root: Path, *, model_label: str) -> pd.DataFrame:
    # For 8B we use control root DRE_statistics.csv (computed against full 180 redundancy run)
    if (run_root / "DRE_statistics.csv").exists():
        d = pd.read_csv(run_root / "DRE_statistics.csv").copy()
        d["model_label"] = model_label
        return d[["model_label", "repetition", "DRE"]]
    # For cross-model runs we use cross_model_DRE_statistics.csv (baseline=lowest rep present)
    d = pd.read_csv(run_root / "cross_model_DRE_statistics.csv").copy()
    d["model_label"] = model_label
    return d[["model_label", "repetition", "DRE"]]


def make_plots(out_dir: Path, dre_df: pd.DataFrame) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update(
        {
            "figure.dpi": 200,
            "savefig.dpi": 400,
            "font.size": 11,
            "axes.spines.top": False,
            "axes.spines.right": False,
        }
    )

    # DRE by repetition (line plot)
    fig, ax = plt.subplots(figsize=(6.4, 3.8))
    styles = {
        "LLaMA-8B (3-run full pilots)": {"ls": "-", "color": "black"},
        "LLaMA-70B (midrange, 3 runs)": {"ls": "--", "color": "gray"},
        "Qwen-72B (midrange, 3 runs)": {"ls": ":", "color": "black"},
    }
    for label, g in dre_df.groupby("model_label"):
        g2 = g.sort_values("repetition")
        st = styles.get(label, {"ls": "-", "color": "black"})
        ax.plot(
            g2["repetition"].astype(int).tolist(),
            g2["DRE"].astype(float).tolist(),
            marker="o",
            linewidth=1.6,
            markersize=5,
            label=label,
            linestyle=st["ls"],
            color=st["color"],
        )
    ax.axhline(0.0, color="black", linewidth=0.8, alpha=0.5)
    ax.set_xlabel("Repetition level (x)")
    ax.set_ylabel("DRE (F1 drop redundancy − filler)")
    ax.grid(True, axis="y", linestyle="--", linewidth=0.6, alpha=0.6)
    ax.legend(frameon=False, fontsize=9)
    fig.tight_layout()
    fig.savefig(out_dir / "model_comparison_DRE.png")
    plt.close(fig)


def main() -> int:
    dre_parts = [
        _load_dre_for_model(RUNS["llama8b_full"], model_label="LLaMA-8B (3-run full pilots)"),
        _load_dre_for_model(RUNS["llama70b_rep3_mid"], model_label="LLaMA-70B (midrange, 3 runs)"),
        _load_dre_for_model(RUNS["qwen72b_rep3_mid"], model_label="Qwen-72B (midrange, 3 runs)"),
    ]
    dre = pd.concat(dre_parts, ignore_index=True)
    out_dir = Path("paper_artifacts")
    out_dir.mkdir(parents=True, exist_ok=True)
    dre.to_csv(out_dir / "cross_model_DRE_combined.csv", index=False)
    make_plots(out_dir, dre)

    # Short summary markdown
    md = [
        "# Cross-Model Summary (DRE)",
        "",
        "This report consolidates DRE across:",
        "- LLaMA-8B full pilots (redundancy vs filler control)",
        "- LLaMA-70B midrange replication (3 runs/condition)",
        "- Qwen-72B midrange replication (3 runs/condition)",
        "",
        "Primary files:",
        "- `paper_artifacts/cross_model_DRE_combined.csv`",
        "- `paper_artifacts/model_comparison_DRE.png`",
        "",
        "Table:",
        "```",
        dre.sort_values(["model_label", "repetition"]).to_string(index=False),
        "```",
        "",
    ]
    (out_dir / "cross_model_summary.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
