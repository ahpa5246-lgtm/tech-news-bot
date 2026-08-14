"""Phase 3 source research orchestration."""
from __future__ import annotations

import json
import logging
from typing import Any

from ai.base import AIProviderError
from database import NewsDatabase
from research.source import SourceDocument, retrieve_source
from research.verifier import deterministic_verification, validate_verification

logger = logging.getLogger(__name__)


def document_payload(document: SourceDocument) -> dict[str, Any]:
    return {
        "requested_url": document.requested_url, "final_url": document.final_url,
        "domain": document.domain, "http_status": document.http_status, "accessible": document.accessible,
        "extracted": document.extracted, "title": document.title, "author": document.author,
        "publication_date": document.publication_date, "canonical_url": document.canonical_url,
        "source_name": document.source_name, "text": document.text, "error": document.error,
    }


def research_payload(row: Any, document: SourceDocument) -> dict[str, Any]:
    phase2 = {
        "decision": row["ai_decision"], "category": row["ai_category"],
        "summary_ar": row["ai_summary_ar"], "what_happened": row["ai_what_happened"],
        "why_it_matters": row["ai_why_it_matters"], "key_facts": row["ai_key_facts"],
        "claims": row["ai_claims"], "needs_research": bool(row["ai_needs_research"] or 0),
    }
    return {
        "rss": {"title": row["title"], "source": row["source"], "url": row["url"], "published_at": row["published_at"], "summary": row["summary"]},
        "phase2": phase2,
        "source": document_payload(document),
    }


class SourceResearcher:
    def __init__(self, database: NewsDatabase, provider: Any | None, timeout_seconds: float, user_agent: str) -> None:
        self.database = database
        self.provider = provider
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent

    def research_pending(self, limit: int | None = None, reresearch: bool = False) -> tuple[int, int, int]:
        rows = self.database.get_research_pending(limit=limit, reresearch=reresearch)
        researched = failed = 0
        for row in rows:
            article_id = row["id"]
            self.database.mark_researching(article_id)
            document = retrieve_source(row["url"], self.timeout_seconds, self.user_agent)
            payload = document_payload(document)
            try:
                if self.provider is not None and hasattr(self.provider, "verify_source") and document.accessible and document.extracted:
                    verification = self.provider.verify_source(research_payload(row, document))
                else:
                    verification = deterministic_verification(row["title"], payload)
                verification = validate_verification(verification)
                self.database.save_research(article_id, payload, verification, row["url"])
                researched += 1
            except (AIProviderError, ValueError, TypeError, json.JSONDecodeError) as exc:
                failed += 1
                logger.warning("Source research failed for article %s: %s", article_id, exc)
                self.database.save_research_error(article_id, str(exc))
            except Exception as exc:
                failed += 1
                logger.warning("Unexpected source research failure for article %s: %s", article_id, exc)
                self.database.save_research_error(article_id, str(exc))
        return researched, failed, 0
