"""SQLite persistence and duplicate lookup helpers."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from models import NewsArticle


class NewsDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self) -> None:
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                published_at TEXT,
                summary TEXT NOT NULL DEFAULT '',
                language TEXT NOT NULL,
                collected_at TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                importance_score INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'NEW',
                UNIQUE(url),
                UNIQUE(content_hash)
            )"""
        )
        self.connection.execute("CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at)")
        self.connection.execute("CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status)")
        self.connection.commit()

    def is_duplicate(self, article: NewsArticle) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM articles WHERE url = ? OR content_hash = ? LIMIT 1",
            (article.url, article.content_hash),
        ).fetchone()
        if row:
            return True
        candidates = self.connection.execute(
            "SELECT title FROM articles WHERE published_at IS NULL OR published_at >= datetime('now', '-7 days')"
        ).fetchall()
        from difflib import SequenceMatcher
        normalized = article.title.casefold()
        return any(SequenceMatcher(None, normalized, row["title"].casefold()).ratio() >= 0.88 for row in candidates)

    def save_article(self, article: NewsArticle) -> bool:
        try:
            self.connection.execute(
                """INSERT INTO articles
                (source, title, url, published_at, summary, language, collected_at,
                 content_hash, importance_score, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                article.as_database_tuple(),
            )
            self.connection.commit()
            return True
        except sqlite3.IntegrityError:
            self.connection.rollback()
            return False

    def save_articles(self, articles: Iterable[NewsArticle]) -> int:
        return sum(self.save_article(article) for article in articles)

    def close(self) -> None:
        self.connection.close()
