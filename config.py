"""Application configuration for the RSS technology-news collector."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATABASE_PATH = Path(os.getenv("NEWS_DATABASE_PATH", DATA_DIR / "news.db"))
MAX_ARTICLE_AGE_HOURS = int(os.getenv("MAX_ARTICLE_AGE_HOURS", "48"))
REQUEST_TIMEOUT_SECONDS = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "15"))
MIN_IMPORTANCE_SCORE = int(os.getenv("MIN_IMPORTANCE_SCORE", "3"))
USER_AGENT = os.getenv(
    "RSS_USER_AGENT",
    "TechNewsCollector/1.0 (+https://example.invalid; contact: admin@example.invalid)",
)
AI_PROVIDER = os.getenv("AI_PROVIDER", "").strip().casefold()
AI_MODEL = os.getenv("AI_MODEL", "gpt-5-mini")
AI_API_KEY = os.getenv("AI_API_KEY", "").strip() or None
AI_API_BASE = os.getenv("AI_API_BASE", "").strip() or None
AI_TIMEOUT_SECONDS = float(os.getenv("AI_TIMEOUT_SECONDS", "45"))
WRITER_MAX_POST_CHARS = int(os.getenv("WRITER_MAX_POST_CHARS", "1400"))

# Keep this mapping easy to edit. Disabled sources are documented in README.md.
RSS_FEEDS: dict[str, str] = {
    "OpenAI": "https://openai.com/blog/rss.xml",
    "Google DeepMind": "https://deepmind.google/blog/rss.xml",
    "GitHub": "https://github.blog/feed/",
    "Hugging Face": "https://huggingface.co/blog/feed.xml",
    "NVIDIA": "https://blogs.nvidia.com/feed/",
    "Microsoft": "https://blogs.microsoft.com/feed/",
    "Apple": "https://www.apple.com/newsroom/rss-feed.rss",
    "TechCrunch": "https://techcrunch.com/feed/",
    "The Verge": "https://www.theverge.com/rss/index.xml",
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/index",
    "Hacker News": "https://news.ycombinator.com/rss",
}

# Anthropic has no consistently documented public official RSS endpoint here;
# keep it disabled until an endpoint is manually verified.
DISABLED_FEEDS: dict[str, str] = {
    "Anthropic": "No stable official public RSS endpoint verified for this version.",
    "Meta AI": "Configured endpoint returned HTTP 404 during local verification; disabled until a working official feed is confirmed.",
}

@dataclass(frozen=True)
class Settings:
    database_path: Path = DATABASE_PATH
    max_article_age_hours: int = MAX_ARTICLE_AGE_HOURS
    request_timeout_seconds: float = REQUEST_TIMEOUT_SECONDS
    min_importance_score: int = MIN_IMPORTANCE_SCORE
    user_agent: str = USER_AGENT
    ai_provider: str = AI_PROVIDER
    ai_model: str = AI_MODEL
    ai_api_key: str | None = AI_API_KEY
    ai_api_base: str | None = AI_API_BASE
    ai_timeout_seconds: float = AI_TIMEOUT_SECONDS
    writer_max_post_chars: int = WRITER_MAX_POST_CHARS

settings = Settings()
