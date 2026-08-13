"""Typed data structures used by the collector."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class NewsArticle:
    source: str
    title: str
    url: str
    published_at: Optional[datetime]
    summary: str
    language: str
    collected_at: datetime
    content_hash: str
    importance_score: int = 0
    status: str = "NEW"
    id: Optional[int] = None

    def as_database_tuple(self) -> tuple:
        return (
            self.source,
            self.title,
            self.url,
            self.published_at.isoformat() if self.published_at else None,
            self.summary,
            self.language,
            self.collected_at.isoformat(),
            self.content_hash,
            self.importance_score,
            self.status,
        )


@dataclass
class FeedResult:
    source: str
    discovered: int = 0
    recent: int = 0
    relevant: int = 0
    safety_rejected: int = 0
    review: int = 0
    duplicates: int = 0
    stored: int = 0
    error: Optional[str] = None
