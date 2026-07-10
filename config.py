from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    project_root: Path = Path(__file__).resolve().parent

    # Data
    data_dir: Path = project_root / "data"

    # Experiment sizes
    num_patients: int = 10
    repetition_levels: tuple[int, ...] = (1, 2, 5, 10, 16, 32)
    runs_per_condition: int = 3
    random_seed: int = 1337

    # Control experiment (implemented but not enabled by default)
    enable_constant_length_control: bool = False

    # Prompt and schema (must remain fixed)
    extraction_prompt_template: str = None  # populated in __post_init__
    system_prompt: str = None  # populated in __post_init__
    fixed_schema: dict = None  # populated in __post_init__

    # DeepInfra / model (fixed for pilot)
    deepinfra_base_url: str = "https://api.deepinfra.com/v1/openai"
    model: str = "meta-llama/Meta-Llama-3.1-8B-Instruct"
    temperature: float = 0.0
    top_p: float = 1.0
    # Some OpenAI-compatible backends accept a seed; DeepInfra support may vary.
    seed: int | None = 1337
    # Explicit cap to avoid backend-default truncation; keep fixed across experiments.
    max_tokens: int | None = 512

    # Client behavior
    request_timeout_s: int = 120
    max_retries: int = 5
    initial_backoff_s: float = 1.0

    # Token estimation (cheap heuristic, for logging only)
    est_chars_per_token: float = 4.0

    def __post_init__(self):
        object.__setattr__(
            self,
            "fixed_schema",
            {
                "patient_id": "",
                "conditions": [],
                "medications": [],
                "observations": [],
                "procedures": [],
            },
        )
        object.__setattr__(
            self,
            "system_prompt",
            "You are a backend medical extraction service.\n"
            "Return ONLY valid JSON.\n"
            "Do not use markdown.\n"
            "Do not use code fences.\n"
            "Do not explain.\n"
            "Do not add commentary.\n"
            "If information is missing, return empty arrays.\n"
            "Follow the exact schema.",
        )
        object.__setattr__(
            self,
            "extraction_prompt_template",
            'Extract all medical information from the document into this EXACT schema:\n\n'
            '{{\n'
            '"patient_id": "",\n'
            '"conditions": [],\n'
            '"medications": [],\n'
            '"observations": [],\n'
            '"procedures": []\n'
            '}}\n\n'
            'Rules:\n\n'
            '* Return ONLY valid JSON\n'
            '* Do not wrap in markdown\n'
            '* Do not add extra keys\n'
            '* Do not rename fields\n'
            '* Arrays must always exist\n'
            '* If empty, use []\n\n'
            'Document:\n'
            '{document_text}\n',
        )


def get_settings() -> Settings:
    def _get_int(name: str, default: int) -> int:
        v = os.getenv(name)
        if v is None or not str(v).strip():
            return default
        return int(str(v).strip())

    def _get_str(name: str, default: str) -> str:
        v = os.getenv(name)
        if v is None or not str(v).strip():
            return default
        return str(v).strip()

    def _get_reps(name: str, default: tuple[int, ...]) -> tuple[int, ...]:
        v = os.getenv(name)
        if v is None or not str(v).strip():
            return default
        parts = [p.strip() for p in str(v).split(",") if p.strip()]
        return tuple(int(p) for p in parts)

    return Settings(
        num_patients=_get_int("ATTNDRIFT_NUM_PATIENTS", Settings.num_patients),
        repetition_levels=_get_reps("ATTNDRIFT_REPETITION_LEVELS", Settings.repetition_levels),
        runs_per_condition=_get_int("ATTNDRIFT_RUNS_PER_CONDITION", Settings.runs_per_condition),
        model=_get_str("ATTNDRIFT_MODEL", Settings.model),
    )


def get_deepinfra_api_key() -> str | None:
    return os.getenv("DEEPINFRA_API_KEY")
