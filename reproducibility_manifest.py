from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


KEY_FILES = [
    "metrics/redundancy_scaling_statistics.csv",
    "DRE_statistics.csv",
    "control_vs_redundancy.csv",
    "metrics/semantic_metrics.csv",
    "metrics/structural_metrics.csv",
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def write_manifest(out_path: Path) -> None:
    repo = Path(".").resolve()
    runs = {
        "full_pilot_8b": "data/runs/full_pilot_20260520_192127",
        "full_control_8b": "data/runs/full_pilot_control_20260520_235546",
        "largeN_redundancy": "data/runs/full_pilot_20260522_161847",
        "largeN_control": "data/runs/full_pilot_control_20260522_165338",
        "shuffled_midrange_rep3": "data/runs/full_pilot_shuffled_20260522_155750",
        "section_level_largeN": "data/runs/section_redundancy_20260522_224913",
        "prompt_robustness_ABC": "data/runs/prompt_robustness_20260523_134838",
    }

    obj: dict[str, Any] = {"repo_root": str(repo), "runs": {}, "hashes": {}}
    for k, v in runs.items():
        root = Path(v)
        obj["runs"][k] = str(root)
        for rel in KEY_FILES:
            p = root / rel
            if p.exists():
                obj["hashes"][f"{k}:{rel}"] = {"path": str(p).replace("\\", "/"), "sha256": _sha256(p)}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    write_manifest(Path("paper_artifacts/reproducibility_manifest.json"))

