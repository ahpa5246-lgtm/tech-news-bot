"""Provider-neutral contracts for Phase 2 AI analysis."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class AIProviderError(RuntimeError):
    """Raised when an AI provider cannot complete a structured analysis."""


class AIProvider(Protocol):
    model: str

    def analyze_article(self, article_payload: dict[str, Any]) -> dict[str, Any]:
        """Analyze one article and return a validated-shape candidate mapping."""


@dataclass(frozen=True)
class ProviderSettings:
    name: str
    model: str
    api_key: str | None
    api_base: str | None
    timeout_seconds: float = 45.0

    @property
    def configured(self) -> bool:
        return bool(self.name and self.api_key)
