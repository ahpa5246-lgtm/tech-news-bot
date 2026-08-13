"""Optional OpenAI-compatible provider implementation.

The rest of the application depends only on the AIProvider protocol, so another
provider can be added without changing the analyst or database layers.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ai.base import AIProviderError, ProviderSettings

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


def load_prompt() -> str:
    return (PROMPT_DIR / "news_analyst_system.txt").read_text(encoding="utf-8")


def load_schema() -> dict[str, Any]:
    return json.loads((PROMPT_DIR / "news_analyst_schema.json").read_text(encoding="utf-8"))


class OpenAICompatibleProvider:
    def __init__(self, settings: ProviderSettings) -> None:
        self.settings = settings
        self.model = settings.model
        if not settings.configured:
            raise AIProviderError("AI provider is not configured")
        if not settings.api_base:
            raise AIProviderError("AI_API_BASE is required for an OpenAI-compatible provider")

    def analyze_article(self, article_payload: dict[str, Any]) -> dict[str, Any]:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": load_prompt()},
                {"role": "user", "content": json.dumps(article_payload, ensure_ascii=False)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "news_editorial_analysis",
                    "strict": True,
                    "schema": load_schema(),
                },
            },
            "max_completion_tokens": 1800,
        }
        endpoint = self.settings.api_base.rstrip("/") + "/chat/completions"
        request = Request(
            endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "TechNewsCollector/2.0",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.settings.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise AIProviderError(f"HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise AIProviderError(str(exc)) from exc
        try:
            content = payload["choices"][0]["message"]["content"]
            return json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise AIProviderError(f"Malformed provider response: {exc}") from exc


def build_provider(settings: ProviderSettings) -> OpenAICompatibleProvider | None:
    """Return a configured provider or None so Phase 1 can run independently."""
    if not settings.name:
        return None
    if settings.name not in {"openai", "openai_compatible"}:
        raise AIProviderError(f"Unsupported AI_PROVIDER: {settings.name}")
    return OpenAICompatibleProvider(settings)
