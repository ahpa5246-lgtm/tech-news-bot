"""RSS fetching, normalization, freshness checks, and collection orchestration."""
from __future__ import annotations

import hashlib
import html
import logging
import re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from time import mktime
from typing import Iterable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urldefrag
from urllib.request import Request, urlopen

import feedparser

from config import settings
from database import NewsDatabase
from filters import calculate_importance, detect_language, is_technology_relevant, run_safety_filter
from models import FeedResult, NewsArticle

logger = logging.getLogger(__name__)


def clean_html(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"<script.*?</script>|<style.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def parse_published(entry: object) -> Optional[datetime]:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        parsed = getattr(entry, key, None)
        if parsed:
            return datetime.fromtimestamp(mktime(parsed), tz=timezone.utc)
    for key in ("published", "updated", "created"):
        raw = getattr(entry, key, None)
        if raw:
            try:
                value = parsedate_to_datetime(raw)
                return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError, OverflowError):
                continue
    return None


def normalize_url(url: str) -> str:
    return urldefrag(url.strip())[0]


def normalize_article(source: str, entry: object) -> Optional[NewsArticle]:
    title = clean_html(getattr(entry, "title", ""))
    url = normalize_url(getattr(entry, "link", ""))
    summary = clean_html(getattr(entry, "summary", "") or getattr(entry, "description", ""))
    if not title or not url:
        return None
    published = parse_published(entry)
    stable = f"{title.casefold()}|{url}|{published.isoformat() if published else ''}"
    return NewsArticle(
        source=source,
        title=title,
        url=url,
        published_at=published,
        summary=summary,
        language=detect_language(f"{title} {summary}"),
        collected_at=datetime.now(timezone.utc),
        content_hash=hashlib.sha256(stable.encode("utf-8")).hexdigest(),
    )


def parse_feed(source: str, feed_url: str) -> tuple[list[NewsArticle], Optional[str]]:
    """Fetch and parse one feed with an explicit timeout."""
    try:
        request = Request(feed_url, headers={"User-Agent": settings.user_agent})
        with urlopen(request, timeout=settings.request_timeout_seconds) as response:
            status = getattr(response, "status", 200)
            payload = response.read()
        if status >= 400:
            return [], f"HTTP {status}"
        parsed = feedparser.parse(payload)
    except HTTPError as exc:
        return [], f"HTTP {exc.code}"
    except (URLError, TimeoutError, OSError) as exc:
        return [], str(exc)
    except Exception as exc:
        return [], str(exc)
    if getattr(parsed, "bozo", False) and not getattr(parsed, "entries", None):
        return [], str(getattr(parsed, "bozo_exception", "invalid RSS/Atom response"))
    articles = []
    for entry in getattr(parsed, "entries", []):
        article = normalize_article(source, entry)
        if article:
            articles.append(article)
    return articles, None


def is_recent(article: NewsArticle, now: Optional[datetime] = None) -> bool:
    if article.published_at is None:
        return True
    now = now or datetime.now(timezone.utc)
    published = article.published_at.astimezone(timezone.utc)
    return now - timedelta(hours=settings.max_article_age_hours) <= published <= now + timedelta(hours=2)


def collect_feeds(feeds: dict[str, str], database: NewsDatabase) -> tuple[list[NewsArticle], list[FeedResult]]:
    """Collect acceptable, non-duplicate articles from all configured feeds."""
    new_articles: list[NewsArticle] = []
    results: list[FeedResult] = []
    for source, url in feeds.items():
        result = FeedResult(source=source)
        articles, error = parse_feed(source, url)
        result.discovered = len(articles)
        if error:
            result.error = error
            logger.warning("Failed to fetch %s RSS: %s", source, error)
            results.append(result)
            continue
        for article in articles:
            if not is_recent(article):
                continue
            result.recent += 1
            if not is_technology_relevant(article):
                continue
            result.relevant += 1
            safety = run_safety_filter(article)
            if safety == "REJECT":
                result.safety_rejected += 1
                article.status = "REJECTED"
                continue
            if safety == "REVIEW":
                result.review += 1
                article.status = "REVIEW"
            article.importance_score = calculate_importance(article)
            if article.importance_score < settings.min_importance_score:
                continue
            if database.is_duplicate(article):
                result.duplicates += 1
                continue
            article.status = "ACCEPTED" if safety == "ACCEPT" else "REVIEW"
            if database.save_article(article):
                result.stored += 1
                new_articles.append(article)
        results.append(result)
    return new_articles, results
