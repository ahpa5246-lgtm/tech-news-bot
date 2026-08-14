"""SQLite persistence and duplicate lookup helpers for Phases 1 and 2."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from models import NewsArticle


AI_COLUMNS: dict[str, str] = {
    "ai_analysis_status": "TEXT NOT NULL DEFAULT 'NOT_ANALYZED'",
    "ai_decision": "TEXT",
    "ai_confidence": "REAL",
    "ai_category": "TEXT",
    "ai_summary_ar": "TEXT",
    "ai_what_happened": "TEXT",
    "ai_why_it_matters": "TEXT",
    "ai_key_facts": "TEXT",
    "ai_claims": "TEXT",
    "ai_safety_status": "TEXT",
    "ai_needs_review": "INTEGER",
    "ai_needs_research": "INTEGER",
    "ai_rejection_reason": "TEXT",
    "ai_analyzed_at": "TEXT",
    "ai_model": "TEXT",
    "ai_error": "TEXT",
}

RESEARCH_COLUMNS: dict[str, str] = {
    "research_status": "TEXT NOT NULL DEFAULT 'RESEARCH_PENDING'",
    "researched_at": "TEXT",
    "source_accessible": "INTEGER",
    "source_http_status": "INTEGER",
    "source_url": "TEXT",
    "source_domain": "TEXT",
    "source_name": "TEXT",
    "canonical_url": "TEXT",
    "extracted_title": "TEXT",
    "extracted_author": "TEXT",
    "extracted_publication_date": "TEXT",
    "extracted_content": "TEXT",
    "verification_status": "TEXT",
    "verified_claims": "TEXT",
    "unsupported_claims": "TEXT",
    "verification_summary": "TEXT",
    "safety_flags": "TEXT",
    "verification_confidence": "REAL",
    "research_error": "TEXT"
}

WRITER_COLUMNS: dict[str, str] = {
    "writer_status": "TEXT NOT NULL DEFAULT 'WRITING_PENDING'",
    "written_at": "TEXT",
    "writer_decision": "TEXT",
    "writer_title": "TEXT",
    "writer_post": "TEXT",
    "writer_summary": "TEXT",
    "writer_news_angle": "TEXT",
    "writer_source_label": "TEXT",
    "writer_source_url": "TEXT",
    "writer_hashtags": "TEXT",
    "writer_safety_flags": "TEXT",
    "writer_unsupported_claims": "TEXT",
    "writer_editorial_notes": "TEXT",
    "writer_model": "TEXT",
    "writer_error": "TEXT"
}


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
                UNIQUE(url), UNIQUE(content_hash)
            )"""
        )
        existing = {row["name"] for row in self.connection.execute("PRAGMA table_info(articles)")}
        for columns in (AI_COLUMNS, RESEARCH_COLUMNS, WRITER_COLUMNS):
            for name, definition in columns.items():
                if name not in existing:
                    self.connection.execute(f"ALTER TABLE articles ADD COLUMN {name} {definition}")
        self.connection.execute("CREATE INDEX IF NOT EXISTS idx_articles_published ON articles(published_at)")
        self.connection.execute("CREATE INDEX IF NOT EXISTS idx_articles_status ON articles(status)")
        self.connection.execute("CREATE INDEX IF NOT EXISTS idx_articles_ai_status ON articles(ai_analysis_status)")
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

    def get_unanalyzed_articles(self, limit: int | None = None, reanalyze: bool = False) -> list[sqlite3.Row]:
        allowed = ("NEW", "ACCEPTED", "REVIEW")
        placeholders = ",".join("?" for _ in allowed)
        query = f"SELECT * FROM articles WHERE status IN ({placeholders})"
        params: list[object] = list(allowed)
        if not reanalyze:
            query += " AND ai_analysis_status != 'ANALYZED'"
        query += " ORDER BY importance_score DESC, COALESCE(published_at, collected_at) DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        return list(self.connection.execute(query, params).fetchall())

    def mark_analyzing(self, article_id: int) -> None:
        self.connection.execute(
            "UPDATE articles SET ai_analysis_status = 'ANALYZING', ai_error = NULL WHERE id = ?",
            (article_id,),
        )
        self.connection.commit()

    def save_analysis(self, article_id: int, result: dict, model: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.connection.execute(
            """UPDATE articles SET
                ai_analysis_status = 'ANALYZED', ai_decision = ?, ai_confidence = ?, ai_category = ?,
                ai_summary_ar = ?, ai_what_happened = ?, ai_why_it_matters = ?, ai_key_facts = ?,
                ai_claims = ?, ai_safety_status = ?, ai_needs_review = ?, ai_needs_research = ?,
                ai_rejection_reason = ?, ai_analyzed_at = ?, ai_model = ?, ai_error = NULL,
                status = CASE WHEN ? = 'REJECT' THEN 'REJECTED' WHEN ? = 'REVIEW' THEN 'REVIEW' ELSE status END
            WHERE id = ?""",
            (
                result["decision"], result["confidence"], result["category"], result["summary_ar"],
                result["what_happened"], result["why_it_matters"], json.dumps(result["key_facts"], ensure_ascii=False),
                json.dumps(result["claims"], ensure_ascii=False), result["safety_status"],
                int(result["needs_review"]), int(result["needs_research"]), result["rejection_reason"],
                now, model, result["decision"], result["decision"], article_id,
            ),
        )
        self.connection.commit()

    def save_ai_error(self, article_id: int, error: str, model: str | None = None) -> None:
        self.connection.execute(
            "UPDATE articles SET ai_analysis_status = 'AI_ERROR', ai_error = ?, ai_model = ? WHERE id = ?",
            (error[:2000], model, article_id),
        )
        self.connection.commit()

    def get_research_pending(self, limit: int | None = None, reresearch: bool = False) -> list[sqlite3.Row]:
        allowed = ("ACCEPTED", "REVIEW")
        placeholders = ",".join("?" for _ in allowed)
        query = f"SELECT * FROM articles WHERE status IN ({placeholders})"
        params: list[object] = list(allowed)
        if not reresearch:
            query += " AND research_status NOT IN ('VERIFIED', 'RESEARCHING')"
        query += " ORDER BY importance_score DESC, COALESCE(published_at, collected_at) DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        return list(self.connection.execute(query, params).fetchall())

    def mark_researching(self, article_id: int) -> None:
        self.connection.execute(
            "UPDATE articles SET research_status = 'RESEARCHING', research_error = NULL WHERE id = ?",
            (article_id,),
        )
        self.connection.commit()

    def save_research(self, article_id: int, document: dict, verification: dict, source_url: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        status = verification["status"]
        self.connection.execute(
            """UPDATE articles SET research_status = ?, researched_at = ?, source_accessible = ?,
                source_http_status = ?, source_url = ?, source_domain = ?, source_name = ?, canonical_url = ?,
                extracted_title = ?, extracted_author = ?, extracted_publication_date = ?, extracted_content = ?,
                verification_status = ?, verified_claims = ?, unsupported_claims = ?, verification_summary = ?,
                safety_flags = ?, verification_confidence = ?, research_error = ?
            WHERE id = ?""",
            (
                status, now, int(document.get("accessible", False)), document.get("http_status"), source_url,
                document.get("domain"), document.get("source_name"), document.get("canonical_url"),
                document.get("title"), document.get("author"), document.get("publication_date"), document.get("text", ""),
                status, json.dumps(verification["verified_claims"], ensure_ascii=False),
                json.dumps(verification["unsupported_claims"], ensure_ascii=False), verification["verification_summary"],
                json.dumps(verification["safety_flags"], ensure_ascii=False), verification["confidence"],
                verification.get("error"), article_id,
            ),
        )
        self.connection.commit()

    def save_research_error(self, article_id: int, error: str) -> None:
        self.connection.execute(
            "UPDATE articles SET research_status = 'RESEARCH_ERROR', researched_at = ?, research_error = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), error[:2000], article_id),
        )
        self.connection.commit()

    def get_writing_pending(self, limit: int | None = None, rewrite: bool = False) -> list[sqlite3.Row]:
        query = """SELECT * FROM articles
                   WHERE status IN ('ACCEPTED', 'REVIEW')
                     AND research_status IN ('VERIFIED', 'REVIEW', 'RESEARCH_ERROR')"""
        params: list[object] = []
        if not rewrite:
            query += " AND writer_status NOT IN ('GENERATED', 'REVIEW', 'REJECTED', 'WRITING')"
        query += " ORDER BY importance_score DESC, COALESCE(published_at, collected_at) DESC"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        return list(self.connection.execute(query, params).fetchall())

    def mark_writing(self, article_id: int) -> None:
        self.connection.execute(
            "UPDATE articles SET writer_status = 'WRITING', writer_error = NULL WHERE id = ?",
            (article_id,),
        )
        self.connection.commit()

    def save_writer(self, article_id: int, result: dict, model: str | None) -> None:
        now = datetime.now(timezone.utc).isoformat()
        decision = result.get("decision", "REVIEW")
        status = "GENERATED" if decision == "PUBLISH" else ("REJECTED" if decision == "REJECT" else "REVIEW")
        self.connection.execute(
            """UPDATE articles SET writer_status = ?, written_at = ?, writer_decision = ?,
                writer_title = ?, writer_post = ?, writer_summary = ?, writer_news_angle = ?,
                writer_source_label = ?, writer_source_url = ?, writer_hashtags = ?,
                writer_safety_flags = ?, writer_unsupported_claims = ?, writer_editorial_notes = ?,
                writer_model = ?, writer_error = NULL
            WHERE id = ?""",
            (
                status, now, decision, result.get("title"), result.get("post_text"), result.get("summary"),
                result.get("news_angle"), result.get("source_label"), result.get("source_url"),
                json.dumps(result.get("hashtags", []), ensure_ascii=False),
                json.dumps(result.get("safety_flags", []), ensure_ascii=False),
                json.dumps(result.get("unsupported_claims", []), ensure_ascii=False),
                json.dumps(result.get("editorial_notes", []), ensure_ascii=False), model, article_id,
            ),
        )
        self.connection.commit()

    def save_writer_error(self, article_id: int, error: str, model: str | None = None) -> None:
        self.connection.execute(
            "UPDATE articles SET writer_status = 'WRITING_ERROR', written_at = ?, writer_error = ?, writer_model = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), error[:2000], model, article_id),
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.close()
