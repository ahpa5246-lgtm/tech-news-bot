from __future__ import annotations

import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ai.analyst import AIAnalyst, validate_analysis
from database import NewsDatabase
from filters import calculate_importance, run_safety_filter
from models import NewsArticle


def article(title: str, summary: str = "") -> NewsArticle:
    return NewsArticle("Test", title, "https://example.test/1", datetime.now(timezone.utc), summary, "en", datetime.now(timezone.utc), title)


def valid_result(decision="ACCEPT"):
    return {
        "decision": decision, "confidence": 0.9, "category": "AI", "importance_score": 4,
        "summary_ar": "ملخص عربي", "what_happened": "حدث تقني", "why_it_matters": "أهمية عملية",
        "key_facts": ["حقيقة من النص"], "claims": [{"claim": "ادعاء", "verification_status": "NOT_CHECKED", "evidence": None}],
        "safety_status": "SAFE", "needs_review": decision == "REVIEW", "needs_research": True,
        "rejection_reason": "سبب" if decision == "REJECT" else None,
    }


class FakeProvider:
    model = "fake-model"
    def __init__(self, response): self.response = response
    def analyze_article(self, payload): return self.response


class Phase2Tests(unittest.TestCase):
    def test_valid_json_shape(self):
        self.assertEqual(validate_analysis(valid_result())["decision"], "ACCEPT")

    def test_invalid_json_shape(self):
        with self.assertRaises(ValueError): validate_analysis({"decision": "MAYBE"})
        bad = valid_result(); bad["importance_score"] = 9
        with self.assertRaises(ValueError): validate_analysis(bad)

    def test_safety_distinguishes_reporting(self):
        self.assertEqual(run_safety_filter(article("Cybersecurity research examines extremist networks")), "REVIEW")
        self.assertEqual(run_safety_filter(article("Pornography and sex tape distribution")), "REJECT")
        self.assertEqual(run_safety_filter(article("New GPU security update for developers")), "ACCEPT")

    def test_importance(self):
        self.assertGreaterEqual(calculate_importance(article("Major AI model release improves security", "new developer platform update")), 4)
        self.assertLessEqual(calculate_importance(article("Minor fashion update")), 2)

    def test_migration_preserves_existing_article(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.db"
            connection = sqlite3.connect(path)
            connection.execute("CREATE TABLE articles (id INTEGER PRIMARY KEY, source TEXT, title TEXT, url TEXT, published_at TEXT, summary TEXT, language TEXT, collected_at TEXT, content_hash TEXT, importance_score INTEGER, status TEXT)")
            connection.execute("INSERT INTO articles VALUES (1, 'Old', 'Old title', 'https://old', NULL, '', 'en', 'now', 'hash', 3, 'ACCEPTED')")
            connection.commit(); connection.close()
            db = NewsDatabase(path)
            row = db.connection.execute("SELECT title, ai_analysis_status FROM articles WHERE id=1").fetchone()
            self.assertEqual(tuple(row), ("Old title", "NOT_ANALYZED"))
            db.close()

    def test_valid_ai_analysis_is_stored(self):
        with tempfile.TemporaryDirectory() as directory:
            db = NewsDatabase(Path(directory) / "test.db")
            db.save_article(article("AI software release", "developer tool"))
            analyzed, failed, skipped = AIAnalyst(db, FakeProvider(valid_result())).analyze_pending()
            self.assertEqual((analyzed, failed, skipped), (1, 0, 0))
            row = db.connection.execute("SELECT ai_analysis_status, ai_decision, ai_summary_ar FROM articles").fetchone()
            self.assertEqual(tuple(row), ("ANALYZED", "ACCEPT", "ملخص عربي"))
            db.close()

    def test_ai_failure_is_stored_without_crash(self):
        with tempfile.TemporaryDirectory() as directory:
            db = NewsDatabase(Path(directory) / "test.db")
            db.save_article(article("AI software release", "developer tool"))
            analyst = AIAnalyst(db, FakeProvider({"malformed": True}))
            analyzed, failed, skipped = analyst.analyze_pending()
            self.assertEqual((analyzed, failed, skipped), (0, 1, 0))
            self.assertEqual(db.connection.execute("SELECT ai_analysis_status FROM articles").fetchone()[0], "AI_ERROR")
            db.close()


if __name__ == "__main__":
    unittest.main()
