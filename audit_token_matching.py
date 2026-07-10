from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _call_id_from_out_dir(out_dir: Path) -> str | None:
    """
    Finds the call_id for an outputs/<patient>/rep_<Nx>/run_<YY> folder by
    reading repair_event.json if present, else parsing response/usage filenames.
    """
    repair_event = out_dir / "repair_event.json"
    if repair_event.exists():
        try:
            j = _read_json(repair_event)
            # control_experiment uses repair_event as full RepairResult dict; no call_id key.
        except Exception:
            pass
    # We fall back to joining by (patient_id, repetition, run) using the metrics CSV.
    return None


def audit_control_token_matching(
    *,
    control_root: Path,
    redundancy_root: Path,
    out_md: Path,
) -> pd.DataFrame:
    """
    Uses usage.json prompt_tokens (true backend tokens) as the comparison basis.
    Computes mean prompt_tokens per repetition for both runs and reports relative deltas.
    """
    # Load per-call context metrics (estimated) if present, but prefer true prompt_tokens.
    def collect_usage(run_root: Path) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        for usage_path in run_root.glob("outputs/**/usage.json"):
            try:
                usage = _read_json(usage_path)
            except Exception:
                continue
            out_dir = usage_path.parent
            # parse patient/rep/run from path
            try:
                run_name = out_dir.name  # run_01
                rep_name = out_dir.parent.name  # rep_16x
                patient_name = out_dir.parent.parent.name  # patient_08
                rep = int(rep_name.replace("rep_", "").replace("x", ""))
                run_idx = int(run_name.replace("run_", ""))
            except Exception:
                continue
            rows.append(
                {
                    "patient_id": patient_name,
                    "repetition": rep,
                    "run": run_idx,
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                    "total_tokens": usage.get("total_tokens"),
                }
            )
        return pd.DataFrame(rows)

    c = collect_usage(control_root)
    r = collect_usage(redundancy_root)
    if c.empty or r.empty:
        raise RuntimeError("Missing usage.json artifacts; cannot audit true token matching.")

    c_agg = c.groupby("repetition", as_index=False)["prompt_tokens"].mean(numeric_only=True).rename(columns={"prompt_tokens": "control_prompt_tokens_mean"})
    r_agg = r.groupby("repetition", as_index=False)["prompt_tokens"].mean(numeric_only=True).rename(columns={"prompt_tokens": "redundancy_prompt_tokens_mean"})
    merged = r_agg.merge(c_agg, on="repetition", how="inner").sort_values("repetition")
    merged["delta"] = merged["control_prompt_tokens_mean"] - merged["redundancy_prompt_tokens_mean"]
    merged["delta_frac"] = merged["delta"] / merged["redundancy_prompt_tokens_mean"].replace(0, pd.NA)
    merged["within_5pct"] = (merged["delta_frac"].abs() <= 0.05).astype(int)

    lines = [
        "# Token Matching Audit (Using True Prompt Tokens)",
        "",
        "This audit uses `usage.json.prompt_tokens` (backend-reported) as the token-length proxy.",
        "This includes the system+user prompt wrapper, so it is a *prompt-level* token match check, not pure-document-only.",
        "",
        f"- control_root: `{control_root}`",
        f"- redundancy_root: `{redundancy_root}`",
        "",
        "## By repetition (mean prompt_tokens)",
        "```",
        merged.to_string(index=False),
        "```",
        "",
        "## Pass/fail (±5%)",
        f"- repetitions within ±5%: `{int(merged['within_5pct'].sum())}/{len(merged)}`",
        "",
    ]
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return merged


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--control_root", type=str, default="data/runs/full_pilot_control_20260520_235546")
    ap.add_argument("--redundancy_root", type=str, default="data/runs/full_pilot_20260520_192127")
    ap.add_argument("--out_md", type=str, default="data/runs/full_pilot_control_20260520_235546/token_matching_audit_true_tokens.md")
    args = ap.parse_args()

    audit_control_token_matching(
        control_root=Path(args.control_root),
        redundancy_root=Path(args.redundancy_root),
        out_md=Path(args.out_md),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

