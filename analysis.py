from __future__ import annotations

import json
import math
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd


def estimate_tokens(char_count: int, chars_per_token: float = 4.0) -> int:
    if char_count <= 0:
        return 0
    return int(math.ceil(char_count / max(chars_per_token, 0.1)))


def confidence_interval_95(mean: float, std: float, n: int) -> tuple[float, float]:
    if n <= 1:
        return mean, mean
    # Normal approximation is fine for pilot summaries.
    half = 1.96 * (std / math.sqrt(n))
    return mean - half, mean + half


def summarize_by_repetition(
    semantic_df: pd.DataFrame, structural_df: pd.DataFrame, variance_df: pd.DataFrame | None = None
) -> pd.DataFrame:
    merged = semantic_df.merge(
        structural_df[
            [
                "patient_id",
                "repetition",
                "run",
                "raw_valid_json",
                "structural_drift_score",
                "repair_needed",
            ]
        ],
        on=["patient_id", "repetition", "run"],
        how="left",
    )
    g = merged.groupby("repetition", as_index=False)
    out = g.agg(
        n=("micro_f1", "count"),
        f1_mean=("micro_f1", "mean"),
        f1_std=("micro_f1", "std"),
        omission_mean=("omission_count", "mean"),
        omission_std=("omission_count", "std"),
        halluc_mean=("hallucination_count", "mean"),
        halluc_std=("hallucination_count", "std"),
        raw_json_valid_rate=("raw_valid_json", "mean"),
        sds_mean=("structural_drift_score", "mean"),
        sds_std=("structural_drift_score", "std"),
        repair_rate=("repair_needed", "mean"),
    ).sort_values("repetition")

    for col_mean, col_std, prefix in [
        ("f1_mean", "f1_std", "f1"),
        ("omission_mean", "omission_std", "omission"),
        ("halluc_mean", "halluc_std", "halluc"),
        ("sds_mean", "sds_std", "sds"),
    ]:
        cis = out.apply(
            lambda r: confidence_interval_95(float(r[col_mean]), float(r[col_std] or 0.0), int(r["n"])),
            axis=1,
        )
        out[f"{prefix}_ci_low"] = [c[0] for c in cis]
        out[f"{prefix}_ci_high"] = [c[1] for c in cis]

    if variance_df is not None and not variance_df.empty:
        v = variance_df.groupby("repetition", as_index=False).agg(
            output_variance_mean=("semantic_pairwise_jaccard_distance_mean", "mean")
        )
        out = out.merge(v, on="repetition", how="left")

    return out


def pearson_corr(df: pd.DataFrame, x: str, y: str) -> float | None:
    s = df[[x, y]].dropna()
    if len(s) < 3:
        return None
    return float(s[x].corr(s[y], method="pearson"))


def write_json(path: Path, obj: Any):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def dataclass_to_json(path: Path, dc) -> None:
    write_json(path, asdict(dc))
