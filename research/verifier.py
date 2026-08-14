"""Source verification contracts, validation, and conservative no-AI fallback."""
from __future__ import annotations

import json
from difflib import SequenceMatcher
from typing import Any

STATUSES = {"VERIFIED", "REVIEW", "RESEARCH_ERROR"}


def validate_verification(value: Any) -> dict[str, Any]:
    required = {"status", "source_accessible", "source_title", "source_domain", "publication_date", "canonical_url", "verified_claims", "unsupported_claims", "verification_summary", "safety_flags", "confidence", "error"}
    if not isinstance(value, dict):
        raise ValueError("verification must be a JSON object")
    missing = required - value.keys()
    if missing:
        raise ValueError(f"missing fields: {', '.join(sorted(missing))}")
    if value["status"] not in STATUSES:
        raise ValueError("invalid research status")
    if not isinstance(value["source_accessible"], bool):
        raise ValueError("source_accessible must be boolean")
    for field in ("source_title", "source_domain", "publication_date", "canonical_url", "error"):
        if value[field] is not None and not isinstance(value[field], str):
            raise ValueError(f"{field} must be string or null")
    for field in ("verified_claims", "unsupported_claims", "safety_flags"):
        if not isinstance(value[field], list) or not all(isinstance(item, str) for item in value[field]):
            raise ValueError(f"{field} must be a string array")
    if not isinstance(value["verification_summary"], str):
        raise ValueError("verification_summary must be a string")
    if not isinstance(value["confidence"], (int, float)) or not 0 <= value["confidence"] <= 1:
        raise ValueError("confidence must be between 0 and 1")
    return value


def deterministic_verification(rss_title: str, document: dict[str, Any]) -> dict[str, Any]:
    """Store useful retrieval facts without claiming unsupported article facts."""
    if not document.get("accessible") or not document.get("extracted"):
        return {
            "status": "REVIEW", "source_accessible": bool(document.get("accessible")),
            "source_title": document.get("title"), "source_domain": document.get("domain"),
            "publication_date": document.get("publication_date"), "canonical_url": document.get("canonical_url"),
            "verified_claims": [], "unsupported_claims": [rss_title],
            "verification_summary": "The original source was not extracted reliably; independent verification is unavailable.",
            "safety_flags": [], "confidence": 0.0, "error": document.get("error") or "source extraction failed",
        }
    title_similarity = SequenceMatcher(None, rss_title.casefold(), (document.get("title") or "").casefold()).ratio()
    if title_similarity >= 0.45:
        return {
            "status": "VERIFIED", "source_accessible": True,
            "source_title": document.get("title"), "source_domain": document.get("domain"),
            "publication_date": document.get("publication_date"), "canonical_url": document.get("canonical_url"),
            "verified_claims": ["The source page was retrieved and its title is consistent with the RSS title."],
            "unsupported_claims": [],
            "verification_summary": "The original page was retrieved and extracted. Detailed claims remain limited to the supplied source text.",
            "safety_flags": [], "confidence": round(min(0.85, title_similarity), 2), "error": None,
        }
    return {
        "status": "REVIEW", "source_accessible": True,
        "source_title": document.get("title"), "source_domain": document.get("domain"),
        "publication_date": document.get("publication_date"), "canonical_url": document.get("canonical_url"),
        "verified_claims": [], "unsupported_claims": [rss_title],
        "verification_summary": "The source was retrieved, but its title does not clearly match the RSS metadata.",
        "safety_flags": [], "confidence": round(title_similarity, 2), "error": "RSS/source title mismatch",
    }
