"""Original webpage retrieval and conservative article-content extraction."""
from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)
MAX_SOURCE_BYTES = 4 * 1024 * 1024


@dataclass
class SourceDocument:
    requested_url: str
    final_url: str | None = None
    domain: str | None = None
    http_status: int | None = None
    accessible: bool = False
    extracted: bool = False
    title: str | None = None
    author: str | None = None
    publication_date: str | None = None
    canonical_url: str | None = None
    source_name: str | None = None
    text: str = ""
    error: str | None = None


def _valid_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _meta(soup: BeautifulSoup, *names: str) -> str | None:
    for name in names:
        tag = soup.find("meta", attrs={"name": name}) or soup.find("meta", attrs={"property": name})
        if tag and tag.get("content"):
            return html.unescape(str(tag["content"])).strip()
    return None


def _date_value(value: str | None) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        return value.strip() or None


def extract_article(html_bytes: bytes, final_url: str, requested_url: str) -> SourceDocument:
    """Extract metadata and readable paragraphs; return unsuccessful for empty pages."""
    document = SourceDocument(requested_url=requested_url, final_url=final_url, domain=urlparse(final_url).netloc)
    soup = BeautifulSoup(html_bytes, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer", "aside", "form", "iframe"]):
        tag.decompose()
    document.title = _meta(soup, "og:title", "twitter:title") or (soup.title.get_text(" ", strip=True) if soup.title else None)
    document.author = _meta(soup, "author", "article:author")
    date_raw = _meta(soup, "article:published_time", "date", "datePublished")
    if not date_raw:
        time_tag = soup.find("time", datetime=True)
        date_raw = time_tag.get("datetime") if time_tag else None
    document.publication_date = _date_value(date_raw)
    canonical = soup.find("link", rel=lambda value: value and "canonical" in value)
    document.canonical_url = canonical.get("href", "").strip() if canonical else None
    document.source_name = _meta(soup, "og:site_name", "application-name") or document.domain
    container = soup.find("article") or soup.find("main") or soup.body
    if container is None:
        document.error = "no article container"
        return document
    paragraphs = []
    for paragraph in container.find_all(["p", "h2", "h3"], limit=400):
        value = re.sub(r"\s+", " ", paragraph.get_text(" ", strip=True)).strip()
        if len(value) >= 25:
            paragraphs.append(value)
    document.text = "\n\n".join(paragraphs)
    if len(document.text) < 120:
        document.error = "article text too short or empty"
        return document
    document.extracted = True
    return document


def retrieve_source(url: str, timeout_seconds: float, user_agent: str) -> SourceDocument:
    """Retrieve one public page without bypassing access controls or retrying aggressively."""
    document = SourceDocument(requested_url=url)
    if not _valid_url(url):
        document.error = "invalid URL"
        return document
    request = Request(url, headers={"User-Agent": user_agent, "Accept": "text/html,application/xhtml+xml"})
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            document.http_status = getattr(response, "status", None)
            final_url = response.geturl()
            payload = response.read(MAX_SOURCE_BYTES + 1)
        if len(payload) > MAX_SOURCE_BYTES:
            document.error = "source exceeds maximum size"
            return document
        if document.http_status and document.http_status >= 400:
            document.error = f"HTTP {document.http_status}"
            return document
        document = extract_article(payload, final_url, url)
        document.http_status = document.http_status or 200
        document.accessible = True
        return document
    except HTTPError as exc:
        document.http_status = exc.code
        document.error = f"HTTP {exc.code}"
    except (URLError, TimeoutError, OSError) as exc:
        document.error = str(exc)
    except Exception as exc:
        logger.warning("Unexpected source extraction error for %s: %s", url, exc)
        document.error = str(exc)
    return document
