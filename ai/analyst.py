"""Phase 2 AI News Analyst orchestration and response validation."""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from ai.base import AIProvider, AIProviderError
from database import NewsDatabase

logger = logging.getLogger(__name__)
DECISIONS = {"ACCEPT", "REVIEW", "REJECT"}
VERIFICATION = {"SUPPORTED", "UNSUPPORTED", "UNCERTAIN", "NOT_CHECKED"}
SAFETY = {"SAFE", "SENSITIVE_REVIEW", "UNSAFE"}


def row_to_payload(row: Any) -> dict[str, Any]:
    return {
        "title": row["title"], "source": row["source"], "url": row["url"],
        "published_at": row["published_at"], "summary": row["summary"],
        "language": row["language"], "importance_score": row["importance_score"],
        "status": row["status"],
    }


def validate_analysis(value: Any) -> dict[str, Any]:
    """Validate the required structured response without unsafe eval or silent repair."""
    if not isinstance(value, dict):
        raise ValueError("analysis must be a JSON object")
    required = {"decision", "confidence", "category", "importance_score", "summary_ar", "what_happened", "why_it_matters", "key_facts", "claims", "safety_status", "needs_review", "needs_research", "rejection_reason"}
    missing = required - value.keys()
    if missing:
        raise ValueError(f"missing fields: {', '.join(sorted(missing))}")
    if value["decision"] not in DECISIONS:
        raise ValueError("invalid decision")
    if not isinstance(value["confidence"], (int, float)) or not 0 <= value["confidence"] <= 1:
        raise ValueError("confidence must be between 0 and 1")
    if not isinstance(value["category"], str) or not value["category"].strip():
        raise ValueError("category must be non-empty")
    if not isinstance(value["importance_score"], int) or not 0 <= value["importance_score"] <= 5:
        raise ValueError("importance_score must be an integer from 0 to 5")
    for field in ("summary_ar", "what_happened", "why_it_matters"):
        if not isinstance(value[field], str):
            raise ValueError(f"{field} must be a string")
    if not isinstance(value["key_facts"], list) or not all(isinstance(item, str) for item in value["key_facts"]):
        raise ValueError("key_facts must be a string array")
    if not isinstance(value["claims"], list):
        raise ValueError("claims must be an array")
    for claim in value["claims"]:
        if not isinstance(claim, dict) or set(claim) != {"claim", "verification_status", "evidence"}:
            raise ValueError("each claim must contain claim, verification_status, evidence only")
        if not isinstance(claim["claim"], str) or claim["verification_status"] not in VERIFICATION:
            raise ValueError("invalid claim structure")
        if claim["evidence"] is not None and not isinstance(claim["evidence"], str):
            raise ValueError("claim evidence must be string or null")
    if value["safety_status"] not in SAFETY:
        raise ValueError("invalid safety_status")
    for field in ("needs_review", "needs_research"):
        if not isinstance(value[field], bool):
            raise ValueError(f"{field} must be boolean")
    if value["rejection_reason"] is not None and not isinstance(value["rejection_reason"], str):
        raise ValueError("rejection_reason must be string or null")
    if value["decision"] == "REJECT" and not value["rejection_reason"]:
        raise ValueError("REJECT requires rejection_reason")
    if value["decision"] == "REVIEW" and not value["needs_review"]:
        raise ValueError("REVIEW requires needs_review=true")
    return value


class AIAnalyst:
    def __init__(self, database: NewsDatabase, provider: AIProvider | None) -> None:
        self.database = database
        self.provider = provider

    def analyze_pending(self, limit: int | None = None, reanalyze: bool = False) -> tuple[int, int, int]:
        """Analyze pending articles; return (analyzed, failed, skipped)."""
        rows = self.database.get_unanalyzed_articles(limit=limit, reanalyze=reanalyze)
        if self.provider is None:
            logger.warning("AI provider is not configured. AI analysis skipped.")
            return 0, 0, len(rows)
        analyzed = failed = 0
        for row in rows:
            article_id = row["id"]
            self.database.mark_analyzing(article_id)
            try:
                candidate = self.provider.analyze_article(row_to_payload(row))
                result = validate_analysis(candidate)
                self.database.save_analysis(article_id, result, self.provider.model)
                analyzed += 1
            except (AIProviderError, ValueError, TypeError, json.JSONDecodeError) as exc:
                failed += 1
                logger.warning("AI analysis failed for article %s: %s", article_id, exc)
                self.database.save_ai_error(article_id, str(exc), getattr(self.provider, "model", None))
            except Exception as exc:
                failed += 1
                logger.warning("Unexpected AI analysis failure for article %s: %s", article_id, exc)
                self.database.save_ai_error(article_id, str(exc), getattr(self.provider, "model", None))
        return analyzed, failed, 0
