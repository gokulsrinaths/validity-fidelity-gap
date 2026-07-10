from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import requests

from config import Settings, get_deepinfra_api_key


class DeepInfraAuthError(RuntimeError):
    pass


class DeepInfraRequestError(RuntimeError):
    pass


@dataclass(frozen=True)
class DeepInfraResult:
    ok: bool
    status_code: int | None
    latency_s: float
    response_json: dict[str, Any] | None
    error: str | None

    @property
    def content_text(self) -> str | None:
        if not self.response_json:
            return None
        try:
            return self.response_json["choices"][0]["message"]["content"]
        except Exception:
            return None

    @property
    def usage(self) -> dict[str, Any] | None:
        if not self.response_json:
            return None
        return self.response_json.get("usage")


class DeepInfraClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.api_key = get_deepinfra_api_key()
        if not self.api_key:
            raise DeepInfraAuthError(
                "Missing DEEPINFRA_API_KEY. Add it to .env or environment variables."
            )

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        )

    def chat_completions(self, *, user_prompt: str, document_text: str) -> DeepInfraResult:
        url = f"{self.settings.deepinfra_base_url}/chat/completions"
        payload = {
            "model": self.settings.model,
            "temperature": self.settings.temperature,
            "top_p": self.settings.top_p,
            **({"max_tokens": self.settings.max_tokens} if getattr(self.settings, "max_tokens", None) is not None else {}),
            **({"seed": self.settings.seed} if self.settings.seed is not None else {}),
            # JSON mode (OpenAI-compatible structured outputs)
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": self.settings.system_prompt},
                {
                    "role": "user",
                    "content": user_prompt.format(document_text=document_text),
                },
            ],
        }

        backoff = self.settings.initial_backoff_s
        last_error: str | None = None
        for attempt in range(1, self.settings.max_retries + 1):
            t0 = time.perf_counter()
            try:
                resp = self.session.post(
                    url, data=json.dumps(payload), timeout=self.settings.request_timeout_s
                )
                latency = time.perf_counter() - t0

                if resp.status_code == 401 or resp.status_code == 403:
                    return DeepInfraResult(
                        ok=False,
                        status_code=resp.status_code,
                        latency_s=latency,
                        response_json=None,
                        error=f"Auth error ({resp.status_code}): {resp.text[:500]}",
                    )

                if resp.status_code >= 500:
                    last_error = f"Server error ({resp.status_code}): {resp.text[:500]}"
                    raise DeepInfraRequestError(last_error)

                if resp.status_code >= 400:
                    return DeepInfraResult(
                        ok=False,
                        status_code=resp.status_code,
                        latency_s=latency,
                        response_json=None,
                        error=f"Request error ({resp.status_code}): {resp.text[:500]}",
                    )

                try:
                    j = resp.json()
                except Exception:
                    return DeepInfraResult(
                        ok=False,
                        status_code=resp.status_code,
                        latency_s=latency,
                        response_json=None,
                        error=f"Non-JSON response: {resp.text[:500]}",
                    )

                return DeepInfraResult(
                    ok=True,
                    status_code=resp.status_code,
                    latency_s=latency,
                    response_json=j,
                    error=None,
                )
            except (requests.Timeout, requests.ConnectionError, DeepInfraRequestError) as e:
                latency = time.perf_counter() - t0
                last_error = str(e)
                if attempt == self.settings.max_retries:
                    return DeepInfraResult(
                        ok=False,
                        status_code=None,
                        latency_s=latency,
                        response_json=None,
                        error=f"Failed after {attempt} attempts: {last_error}",
                    )
                time.sleep(backoff)
                backoff *= 2

        return DeepInfraResult(
            ok=False,
            status_code=None,
            latency_s=0.0,
            response_json=None,
            error=last_error or "Unknown error",
        )
