"""CLI entry point for Phase 1 collection and optional Phase 2 analysis."""
from __future__ import annotations

import argparse
import logging

from ai.analyst import AIAnalyst
from ai.writer import ArabicNewsWriter
from ai.base import AIProviderError, ProviderSettings
from ai.provider import build_provider
from collector import collect_feeds
from config import RSS_FEEDS, settings
from database import NewsDatabase
from research.researcher import SourceResearcher


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


def print_collection_report(articles: list, results: list) -> None:
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
    print("\n" + "-" * 50 + "\nNEW ARTICLES\n" + "-" * 50)
    for article in sorted(articles, key=lambda item: (item.importance_score, item.published_at or item.collected_at), reverse=True):
        published = article.published_at.isoformat() if article.published_at else "unknown"
        print(f"\n[{article.importance_score}/5] {article.source}\nTitle: {article.title}\nPublished: {published}\nURL: {article.url}")
    print("\n" + "=" * 50)


def run_analysis(database: NewsDatabase, limit: int | None, reanalyze: bool) -> None:
    provider_settings = ProviderSettings(
        name=settings.ai_provider,
        model=settings.ai_model,
        api_key=settings.ai_api_key,
        api_base=settings.ai_api_base,
        timeout_seconds=settings.ai_timeout_seconds,
    )
    try:
        provider = build_provider(provider_settings)
    except AIProviderError as exc:
        logging.getLogger(__name__).warning("AI provider unavailable: %s", exc)
        provider = None
    analyzed, failed, skipped = AIAnalyst(database, provider).analyze_pending(limit=limit, reanalyze=reanalyze)
    print("\nAI NEWS ANALYST")
    print("=" * 50)
    print(f"AI provider: {settings.ai_provider or 'not configured'}")
    print(f"Analyzed: {analyzed}")
    print(f"Failed: {failed}")
    print(f"Skipped: {skipped}")


def run_writer(database: NewsDatabase, limit: int | None, rewrite: bool) -> None:
    provider_settings = ProviderSettings(
        name=settings.ai_provider, model=settings.ai_model, api_key=settings.ai_api_key,
        api_base=settings.ai_api_base, timeout_seconds=settings.ai_timeout_seconds,
    )
    try:
        provider = build_provider(provider_settings)
    except AIProviderError as exc:
        logging.getLogger(__name__).warning("AI provider unavailable for Arabic writing: %s", exc)
        provider = None
    generated, review, rejected, errors = ArabicNewsWriter(database, provider, settings.writer_max_post_chars).write_pending(limit=limit, rewrite=rewrite)
    print("\nARABIC NEWS WRITER")
    print("=" * 50)
    print(f"AI provider: {settings.ai_provider or 'not configured'}")
    print(f"Generated: {generated}")
    print(f"Review: {review}")
    print(f"Rejected: {rejected}")
    print(f"Errors: {errors}")


def run_research(database: NewsDatabase, limit: int | None, reresearch: bool) -> None:
    provider_settings = ProviderSettings(
        name=settings.ai_provider, model=settings.ai_model, api_key=settings.ai_api_key,
        api_base=settings.ai_api_base, timeout_seconds=settings.ai_timeout_seconds,
    )
    try:
        provider = build_provider(provider_settings)
    except AIProviderError as exc:
        logging.getLogger(__name__).warning("AI provider unavailable for research: %s", exc)
        provider = None
    researched, failed, skipped = SourceResearcher(
        database, provider, settings.request_timeout_seconds, settings.user_agent
    ).research_pending(limit=limit, reresearch=reresearch)
    print("\nSOURCE RESEARCH")
    print("=" * 50)
    print(f"AI verification: {'enabled' if provider else 'not configured; deterministic retrieval metadata only'}")
    print(f"Researched: {researched}")
    print(f"Failed: {failed}")
    print(f"Skipped: {skipped}")


def main() -> None:
    parser = argparse.ArgumentParser(description="RSS technology-news collector and optional AI analyst")
    parser.add_argument("--analyze", action="store_true", help="Analyze unanalyzed NEW/ACCEPTED/REVIEW articles")
    parser.add_argument("--research", action="store_true", help="Retrieve and verify original source pages")
    parser.add_argument("--write", action="store_true", help="Generate a grounded Arabic editorial post")
    parser.add_argument("--collect", action="store_true", help="Explicitly run the Phase 1 collector")
    parser.add_argument("--limit", type=int, default=None, help="Maximum articles for --analyze")
    parser.add_argument("--reanalyze", action="store_true", help="Allow re-analysis of already analyzed articles")
    parser.add_argument("--reresearch", action="store_true", help="Allow re-research of already verified articles")
    parser.add_argument("--rewrite", action="store_true", help="Regenerate existing Phase 4 writer results")
    args = parser.parse_args()
    configure_logging()
    database = NewsDatabase(settings.database_path)
    try:
        if args.write:
            run_writer(database, args.limit, args.rewrite)
        elif args.research:
            run_research(database, args.limit, args.reresearch)
        elif args.analyze:
            run_analysis(database, args.limit, args.reanalyze)
        else:
            articles, results = collect_feeds(RSS_FEEDS, database)
            print_collection_report(articles, results)
    finally:
        database.close()


if __name__ == "__main__":
    main()
