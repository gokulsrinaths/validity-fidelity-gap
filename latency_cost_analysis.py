from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def analyze(run_root: Path, out_dir: Path) -> None:
    outputs = run_root / "outputs"
    rows = []
    for usage_path in outputs.rglob("usage.json"):
        try:
            usage = _read_json(usage_path)
        except Exception:
            continue
        # try to pair with latency/meta
        out_dir_path = usage_path.parent
        latency_s = None
        lat_path = out_dir_path / "latency_s.txt"
        if lat_path.exists():
            try:
                latency_s = float(lat_path.read_text(encoding="utf-8").strip())
            except Exception:
                latency_s = None

        meta_path = out_dir_path / "response_meta.json"
        status_code = None
        ok = None
        if meta_path.exists():
            try:
                meta = _read_json(meta_path)
                status_code = meta.get("status_code")
                ok = meta.get("ok")
            except Exception:
                pass

        rows.append(
            {
                "path": str(out_dir_path).replace("\\", "/"),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "latency_s": latency_s,
                "ok": ok,
                "status_code": status_code,
            }
        )

    df = pd.DataFrame(rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_dir / "usage_latency_per_call.csv", index=False)

    # aggregate by repetition if available in path
    def rep_from_path(p: str) -> int | None:
        # expects ".../rep_10x/..."
        import re

        m = re.search(r"/rep_(\\d+)x/", p.replace("\\", "/"))
        return int(m.group(1)) if m else None

    df["repetition"] = df["path"].map(rep_from_path)
    agg = df.dropna(subset=["repetition"]).groupby("repetition", as_index=False).agg(
        n=("total_tokens", "count"),
        prompt_tokens_mean=("prompt_tokens", "mean"),
        completion_tokens_mean=("completion_tokens", "mean"),
        total_tokens_mean=("total_tokens", "mean"),
        latency_s_mean=("latency_s", "mean"),
        latency_s_p95=("latency_s", lambda x: float(pd.Series(x).quantile(0.95)) if len(x) else None),
    )
    agg.to_csv(out_dir / "usage_latency_by_repetition.csv", index=False)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--run_root", required=True)
    ap.add_argument("--out_dir", default="paper_artifacts/latency_cost")
    args = ap.parse_args()
    analyze(Path(args.run_root), Path(args.out_dir))

