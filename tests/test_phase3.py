from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database import NewsDatabase
from research.researcher import SourceResearcher
from research.source import extract_article, retrieve_source
from research.verifier import deterministic_verification, validate_verification

HTML = b'''<html><head><title>New AI Tool</title><meta property="og:title" content="New AI Tool for Developers"><meta property="og:site_name" content="Example"><meta name="author" content="Ada"><link rel="canonical" href="https://example.test/canonical"></head><body><nav>Menu</nav><article><p>This is a sufficiently long paragraph describing a new software tool for developers and its documented behavior.</p><p>The source explains the practical impact for engineering teams and users.</p></article></body></html>'''


class FakeResponse:
    status = 200
    def __init__(self, payload=HTML, url="https://example.test/article"):
        self.payload, self.url = payload, url
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def geturl(self): return self.url
    def read(self, limit=-1): return self.payload


class FakeProvider:
    model = "fake"
    def verify_source(self, payload):
        return {"status": "VERIFIED", "source_accessible": True, "source_title": "New AI Tool for Developers", "source_domain": "example.test", "publication_date": None, "canonical_url": "https://example.test/canonical", "verified_claims": ["The page contains the tool description."], "unsupported_claims": [], "verification_summary": "Source supports the topic.", "safety_flags": [], "confidence": 0.9, "error": None}


class Phase3Tests(unittest.TestCase):
    def test_successful_retrieval_and_redirect(self):
        with patch("research.source.urlopen", return_value=FakeResponse()) as opener:
            result = retrieve_source("https://example.test/article", 1, "TestAgent")
        self.assertTrue(result.accessible); self.assertEqual(result.http_status, 200); opener.assert_called_once()

    def test_http_failure_and_invalid_url(self):
        from urllib.error import HTTPError
        with patch("research.source.urlopen", side_effect=HTTPError("x", 404, "missing", {}, None)):
            result = retrieve_source("https://example.test/missing", 1, "TestAgent")
        self.assertEqual(result.http_status, 404); self.assertIn("HTTP 404", result.error)
        self.assertEqual(retrieve_source("not-a-url", 1, "TestAgent").error, "invalid URL")

    def test_timeout_is_recorded(self):
        with patch("research.source.urlopen", side_effect=TimeoutError("timed out")):
            result = retrieve_source("https://example.test/article", 1, "TestAgent")
        self.assertIn("timed out", result.error)

    def test_extraction_and_canonical_url(self):
        result = extract_article(HTML, "https://example.test/article", "https://example.test/article")
        self.assertTrue(result.extracted); self.assertEqual(result.canonical_url, "https://example.test/canonical")
        self.assertIn("software tool", result.text); self.assertEqual(result.author, "Ada")

    def test_empty_article_and_mismatch_review(self):
        empty = extract_article(b"<html><body><p>tiny</p></body></html>", "https://x", "https://x")
        self.assertFalse(empty.extracted)
        result = deterministic_verification("Completely unrelated title", {"accessible": True, "extracted": True, "title": "Different", "domain": "x", "text": "long"})
        self.assertEqual(result["status"], "REVIEW")

    def test_verification_validation_rejects_malformed_json(self):
        with self.assertRaises(ValueError): validate_verification({"status": "VERIFIED"})
        self.assertEqual(validate_verification({"status": "VERIFIED", "source_accessible": True, "source_title": None, "source_domain": "x", "publication_date": None, "canonical_url": None, "verified_claims": [], "unsupported_claims": [], "verification_summary": "ok", "safety_flags": [], "confidence": 0.8, "error": None})["status"], "VERIFIED")

    def test_database_migration_preserves_phase2_data(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "phase2.db"
            db = NewsDatabase(path)
            db.connection.execute("INSERT INTO articles (source,title,url,summary,language,collected_at,content_hash,status,ai_decision,ai_summary_ar) VALUES ('S','T','https://x','s','en','now','h','ACCEPTED','ACCEPT','تحليل')")
            db.connection.commit(); db.close()
            db = NewsDatabase(path)
            row = db.connection.execute("SELECT ai_decision, ai_summary_ar, research_status FROM articles").fetchone()
            self.assertEqual(tuple(row), ("ACCEPT", "تحليل", "RESEARCH_PENDING")); db.close()

    def test_research_without_ai_and_with_mocked_ai(self):
        with tempfile.TemporaryDirectory() as directory:
            db = NewsDatabase(Path(directory) / "test.db")
            db.connection.execute("INSERT INTO articles (source,title,url,summary,language,collected_at,content_hash,status) VALUES ('S','New AI Tool','https://example.test/article','summary','en','now','h','ACCEPTED')")
            db.connection.commit()
            with patch("research.source.urlopen", return_value=FakeResponse()):
                counts = SourceResearcher(db, None, 1, "TestAgent").research_pending()
            self.assertEqual(counts, (1, 0, 0))
            self.assertEqual(db.connection.execute("SELECT research_status FROM articles").fetchone()[0], "VERIFIED")
            db.connection.execute("UPDATE articles SET research_status='RESEARCH_PENDING'")
            db.connection.commit()
            with patch("research.source.urlopen", return_value=FakeResponse()):
                counts = SourceResearcher(db, FakeProvider(), 1, "TestAgent").research_pending()
            self.assertEqual(counts, (1, 0, 0)); db.close()


if __name__ == "__main__": unittest.main()
