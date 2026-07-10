from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


ENTITY_TYPES = ("conditions", "medications", "observations", "procedures")


@dataclass(frozen=True)
class RunRef:
    patient_id: str
    repetition: int
    run: int
    repaired_path: Path


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _norm_str(x: Any) -> str:
    if x is None:
        return ""
    if not isinstance(x, str):
        x = str(x)
    s = x.strip().lower()
    s = " ".join(s.split())
    return s


def _as_set(obj: dict[str, Any], key: str) -> set[str]:
    xs = obj.get(key) or []
    if not isinstance(xs, list):
        xs = [xs]
    return {s for s in (_norm_str(v) for v in xs) if s}


def _iter_runs(run_root: Path) -> Iterable[RunRef]:
    out_root = run_root / "outputs"
    for patient_dir in sorted(out_root.glob("patient_*")):
        pid = patient_dir.name
        for rep_dir in sorted(patient_dir.glob("rep_*x")):
            rep = int(rep_dir.name.replace("rep_", "").replace("x", ""))
            for run_dir in sorted(rep_dir.glob("run_*")):
                m = run_dir.name.replace("run_", "")
                try:
                    run = int(m)
                except Exception:
                    run = 0
                repaired = run_dir / "repaired.json"
                if repaired.exists():
                    yield RunRef(patient_id=pid, repetition=rep, run=run, repaired_path=repaired)


def _bootstrap_ci(values: np.ndarray, *, n_boot: int = 5000, seed: int = 1337) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    v = np.asarray(values, dtype=float)
    v = v[~np.isnan(v)]
    if v.size == 0:
        return float("nan"), float("nan"), float("nan")
    if v.size == 1:
        m = float(v.mean())
        return m, m, m
    boots = rng.choice(v, size=(n_boot, v.size), replace=True).mean(axis=1)
    lo, hi = np.quantile(boots, [0.025, 0.975])
    return float(v.mean()), float(lo), float(hi)


def compute(run_root: Path, out_dir: Path) -> None:
    """
    Persistence is computed relative to each patient's 1x extraction (baseline = run 1 for that patient at 1x).
    For each call, persistence(type) = |pred(type) ∩ base(type)| / max(|base(type)|, 1).
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    # load all repaired.json refs
    refs = list(_iter_runs(run_root))
    if not refs:
        raise RuntimeError(f"No repaired.json found under {run_root}")

    # build baseline sets per patient from (rep=1, run=1) if available, else smallest run at rep=1
    baselines: dict[str, dict[str, set[str]]] = {}
    for pid in sorted({r.patient_id for r in refs}):
        r1 = [r for r in refs if r.patient_id == pid and r.repetition == 1]
        if not r1:
            continue
        r1_sorted = sorted(r1, key=lambda r: (r.run if r.run else 9999))
        base_obj = _read_json(r1_sorted[0].repaired_path)
        baselines[pid] = {t: _as_set(base_obj, t) for t in ENTITY_TYPES}

    rows: list[dict[str, Any]] = []
    for r in refs:
        if r.patient_id not in baselines:
            continue
        obj = _read_json(r.repaired_path)
        for t in ENTITY_TYPES:
            base = baselines[r.patient_id][t]
            pred = _as_set(obj, t)
            inter = len(base & pred)
            denom = max(len(base), 1)
            rows.append(
                {
                    "patient_id": r.patient_id,
                    "repetition": r.repetition,
                    "run": r.run,
                    "entity_type": t,
                    "base_size": len(base),
                    "pred_size": len(pred),
                    "intersection_size": inter,
                    "persistence": inter / denom,
                }
            )

    df = pd.DataFrame(rows)
    df.to_csv(out_dir / "entity_type_persistence_per_call.csv", index=False)

    # aggregate with bootstrap CIs over calls
    agg_rows: list[dict[str, Any]] = []
    for (rep, t), g in df.groupby(["repetition", "entity_type"]):
        mean, lo, hi = _bootstrap_ci(g["persistence"].to_numpy(dtype=float))
        agg_rows.append(
            {
                "repetition": int(rep),
                "entity_type": t,
                "n": int(len(g)),
                "persistence_mean": mean,
                "persistence_ci_low": lo,
                "persistence_ci_high": hi,
            }
        )
    agg = pd.DataFrame(agg_rows).sort_values(["entity_type", "repetition"]).reset_index(drop=True)
    agg.to_csv(out_dir / "entity_type_persistence_summary.csv", index=False)

    # plots
    import matplotlib.pyplot as plt

    plt.rcParams.update({"figure.dpi": 200, "savefig.dpi": 400, "font.size": 10})
    fig, ax = plt.subplots(figsize=(6.0, 3.4), dpi=200)
    for t in ENTITY_TYPES:
        s = agg[agg["entity_type"] == t].sort_values("repetition")
        ax.plot(s["repetition"], s["persistence_mean"], marker="o", linewidth=1.6, label=t)
        ax.fill_between(
            s["repetition"],
            s["persistence_ci_low"],
            s["persistence_ci_high"],
            alpha=0.12,
            linewidth=0,
        )
    ax.set_xscale("log", base=2)
    ax.set_xticks(sorted(agg["repetition"].unique().tolist()))
    ax.set_xticklabels([str(x) for x in sorted(agg["repetition"].unique().tolist())])
    ax.set_ylim(0.0, 1.05)
    ax.set_xlabel("Repetition level (x)")
    ax.set_ylabel("Entity persistence vs 1x baseline")
    ax.grid(True, axis="y", linestyle="--", linewidth=0.6, alpha=0.6)
    ax.legend(frameon=False, fontsize=8, ncol=2)
    fig.tight_layout()
    fig.savefig(out_dir / "entity_type_persistence_with_ci.png")
    plt.close(fig)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--run_root", required=True)
    ap.add_argument("--out_dir", required=True)
    args = ap.parse_args()
    compute(Path(args.run_root), Path(args.out_dir))

