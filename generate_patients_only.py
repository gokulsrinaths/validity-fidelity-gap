from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

from config import get_settings
from run_experiments import generate_synthetic_patients, write_patient_files


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate synthetic patient raw/PDF/GT files only (no API calls).")
    ap.add_argument("--num_patients", type=int, default=100)
    ap.add_argument("--reps", type=str, default="1,5,10,16", help="Comma-separated repetition levels.")
    args = ap.parse_args()

    reps = tuple(int(x.strip()) for x in args.reps.split(",") if x.strip())
    if not reps or any(r <= 0 for r in reps):
        raise SystemExit("--reps must be positive integers, e.g. 1,5,10,16")

    settings = get_settings()
    settings = replace(settings, num_patients=int(args.num_patients), repetition_levels=reps)

    patients = generate_synthetic_patients(settings)
    write_patient_files(settings, patients)

    print(f"Generated {len(patients)} patients under `{settings.data_dir}` with reps={list(reps)}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

