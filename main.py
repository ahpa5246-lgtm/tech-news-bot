"""CLI entry point for the technology-news collector."""
from __future__ import annotations

import logging
from collections import Counter

from collector import collect_feeds
from config import RSS_FEEDS, settings
from database import NewsDatabase


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


def main() -> None:
    configure_logging()
    database = NewsDatabase(settings.database_path)
    try:
        articles, results = collect_feeds(RSS_FEEDS, database)
    finally:
        database.close()

    print("=" * 50)
    print("TECH NEWS COLLECTOR")
    print("=" * 50)
    print(f"Sources checked: {len(RSS_FEEDS)}")
    print(f"Feeds successfully loaded: {sum(result.error is None for result in results)}")
    print(f"Articles discovered: {sum(result.discovered for result in results)}")
    print(f"Recent articles: {sum(result.recent for result in results)}")
    print(f"Technology-relevant: {sum(result.relevant for result in results)}")
    print(f"Rejected by safety filter: {sum(result.safety_rejected for result in results)}")
    print(f"Review queue: {sum(result.review for result in results)}")
    print(f"Duplicates removed: {sum(result.duplicates for result in results)}")
    print(f"New articles stored: {len(articles)}")
    print("\n" + "-" * 50)
    print("NEW ARTICLES")
    print("-" * 50)
    for article in sorted(articles, key=lambda item: (item.importance_score, item.published_at or item.collected_at), reverse=True):
        published = article.published_at.isoformat() if article.published_at else "unknown"
        print(f"\n[{article.importance_score}/5] {article.source}")
        print(f"Title: {article.title}")
        print(f"Published: {published}")
        print(f"URL: {article.url}")
    print("\n" + "=" * 50)


if __name__ == "__main__":
    main()
