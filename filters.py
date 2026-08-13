"""Deterministic filters for language, safety, relevance, and importance."""
from __future__ import annotations

import re
from typing import Literal

from models import NewsArticle

TECH_KEYWORDS = {
    "ai", "artificial intelligence", "machine learning", "llm", "model", "software", "programming",
    "developer", "github", "open source", "cybersecurity", "robot", "robotics", "hardware", "chip",
    "semiconductor", "cloud", "linux", "windows", "database", "web", "mobile", "android", "ios",
    "space technology", "engineering", "python", "javascript", "api", "cloud computing", "quantum",
    "gpu", "processor", "browser", "operating system", "startup", "technology", "tech",
}
LOW_VALUE_KEYWORDS = {"celebrity", "sports", "recipe", "fashion", "reality show", "horoscope", "gossip"}
PROMOTIONAL_HARM_KEYWORDS = {
    "porn", "pornography", "xxx", "sex tape", "sexual exploitation", "racial supremacy",
    "ethnic hatred", "terrorist recruitment", "terrorist propaganda", "how to make a bomb",
    "buy illegal drugs", "drug dealer", "graphic gore", "nsfw content",
}
SENSITIVE_REPORTING_TERMS = {"research", "report", "investigation", "safety", "cybersecurity", "policy", "analysis"}


def detect_language(text: str) -> str:
    """Return a lightweight language label without rejecting non-Arabic sources."""
    letters = re.findall(r"[A-Za-z\u0600-\u06FF]", text)
    if not letters:
        return "unknown"
    arabic = sum("\u0600" <= char <= "\u06FF" for char in letters)
    ratio = arabic / len(letters)
    return "ar" if ratio >= 0.25 else "en"


def _text(article: NewsArticle) -> str:
    return f"{article.title} {article.summary}".casefold()


def is_technology_relevant(article: NewsArticle) -> bool:
    """Require technology signals and reject clearly unrelated low-value content."""
    text = _text(article)
    if any(term in text for term in LOW_VALUE_KEYWORDS) and not any(term in text for term in TECH_KEYWORDS):
        return False
    return any(term in text for term in TECH_KEYWORDS)


def run_safety_filter(article: NewsArticle) -> Literal["ACCEPT", "REJECT", "REVIEW"]:
    """Classify promotion/distribution of harmful content conservatively.

    Mere reporting about a sensitive subject is allowed; ambiguous matches go to REVIEW.
    """
    text = _text(article)
    direct_matches = [term for term in PROMOTIONAL_HARM_KEYWORDS if term in text]
    if not direct_matches:
        return "ACCEPT"
    if any(term in text for term in SENSITIVE_REPORTING_TERMS):
        return "REVIEW"
    return "REJECT"


def calculate_importance(article: NewsArticle) -> int:
    """Score technology importance on a 0–5 deterministic scale."""
    text = _text(article)
    matched = sum(term in text for term in TECH_KEYWORDS)
    score = min(3, matched)
    major_signals = {"launch", "released", "release", "security", "vulnerability", "acquisition", "research", "update"}
    if any(term in text for term in major_signals):
        score += 1
    if any(term in text for term in {"breakthrough", "major", "introduces", "announces", "available now"}):
        score += 1
    return min(score, 5)
