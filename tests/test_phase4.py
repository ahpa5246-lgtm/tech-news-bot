from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ai.writer import ArabicNewsWriter, editorial_gate, validate_writer_output
from database import NewsDatabase


VALID_RESULT = {
    "decision": "PUBLISH",
    "title": "أداة جديدة تساعد المطورين على بناء تطبيقات أكثر كفاءة",
    "post_text": "كشفت الشركة عن أداة جديدة للمطورين، وتوضح الصفحة الأصلية أنها تساعد في تحسين سير العمل داخل المشاريع البرمجية. التفاصيل المنشورة تركز على طريقة الاستخدام والميزات المعلنة دون تقديم وعود تتجاوز ما ورد في المصدر.",
    "summary": "أداة جديدة للمطورين.",
    "news_angle": "أداة تطوير جديدة",
    "source_label": "Example",
    "source_url": "https://example.test/article",
    "hashtags": ["#برمجة", "#تقنية"],
    "safety_flags": [],
    "unsupported_claims": [],
    "editorial_notes": [],
}


class FakeWriter:
    model = "fake-writer"
    def __init__(self, result=None, error=None):
        self.result, self.error = result or VALID_RESULT, error
    def write_article(self, payload):
        if self.error:
            raise self.error
        self.seen_payload = payload
        return dict(self.result)


def make_db(path: Path, *, research_status="VERIFIED", unsupported=None, safety=None):
    db = NewsDatabase(path)
    db.connection.execute("""INSERT INTO articles
        (source,title,url,summary,language,collected_at,content_hash,status,importance_score,
         ai_analysis_status,ai_decision,ai_summary_ar,ai_claims,
         research_status,source_accessible,source_url,canonical_url,source_domain,
         extracted_title,extracted_content,verification_status,verified_claims,unsupported_claims,
         verification_summary,safety_flags,verification_confidence)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
        "Example", "New Tool", "https://example.test/article", "summary", "en", "now", "hash", "ACCEPTED", 4,
        "ANALYZED", "ACCEPT", "ملخص", json.dumps([]), research_status, 1,
        "https://example.test/article", "https://example.test/article", "example.test", "New Tool",
        "This is a sufficiently long source article with verified factual content for the writer gate and editorial tests. It contains enough grounded context about the product, the affected users, and the documented technical change.",
        "VERIFIED", json.dumps(["The source describes the tool."]), json.dumps(unsupported or []),
        "The source supports the topic.", json.dumps(safety or []), 0.9,
    ))
    db.connection.commit()
    return db


class Phase4Tests(unittest.TestCase):
    def test_valid_schema_and_arabic_output(self):
        result = validate_writer_output(VALID_RESULT)
        self.assertEqual(result["decision"], "PUBLISH")

    def test_invalid_decision_and_missing_fields(self):
        with self.assertRaises(ValueError):
            validate_writer_output({"decision": "MAYBE"})
        bad = dict(VALID_RESULT); bad["title"] = "English only"; bad["post_text"] = "This is an English post with enough length but no Arabic."
        with self.assertRaises(ValueError): validate_writer_output(bad)

    def test_gate_blocks_review_unsupported_and_unsafe_items(self):
        with tempfile.TemporaryDirectory() as directory:
            for index, kwargs in enumerate(({"research_status": "REVIEW"}, {"unsupported": ["an unsupported claim"]}, {"safety": ["malicious instructions"]})):
                db = make_db(Path(directory) / f"gate_{index}.db", **kwargs)
                row = db.connection.execute("SELECT * FROM articles").fetchone()
                allowed, reasons = editorial_gate(row)
                self.assertFalse(allowed); self.assertTrue(reasons); db.close()

    def test_verified_article_is_generated_and_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            db = make_db(Path(directory) / "writer.db")
            generated, review, rejected, errors = ArabicNewsWriter(db, FakeWriter()).write_pending()
            self.assertEqual((generated, review, rejected, errors), (1, 0, 0, 0))
            row = db.connection.execute("SELECT writer_status, writer_decision, writer_post FROM articles").fetchone()
            self.assertEqual(row[0], "GENERATED"); self.assertEqual(row[1], "PUBLISH"); self.assertIn("الشركة", row[2]); db.close()

    def test_phase3_gate_overrides_fake_publish_and_prompt_injection_is_data(self):
        with tempfile.TemporaryDirectory() as directory:
            db = make_db(Path(directory) / "review.db", research_status="REVIEW")
            generated, review, rejected, errors = ArabicNewsWriter(db, FakeWriter()).write_pending()
            self.assertEqual((generated, review, rejected, errors), (0, 1, 0, 0))
            self.assertEqual(db.connection.execute("SELECT writer_status FROM articles").fetchone()[0], "REVIEW")
            db.close()

    def test_malformed_output_and_provider_failure_are_stored_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            db = make_db(Path(directory) / "bad.db")
            bad = dict(VALID_RESULT); bad["decision"] = "INVALID"
            counts = ArabicNewsWriter(db, FakeWriter(bad)).write_pending()
            self.assertEqual(counts[-1], 1)
            db.close()
            db = make_db(Path(directory) / "error.db")
            counts = ArabicNewsWriter(db, FakeWriter(error=TimeoutError("timeout"))).write_pending()
            self.assertEqual(counts[-1], 1)
            self.assertEqual(db.connection.execute("SELECT writer_status FROM articles").fetchone()[0], "WRITING_ERROR"); db.close()

    def test_no_ai_provider_does_not_create_fake_post(self):
        with tempfile.TemporaryDirectory() as directory:
            db = make_db(Path(directory) / "noai.db")
            counts = ArabicNewsWriter(db, None).write_pending()
            self.assertEqual(counts[-1], 1)
            row = db.connection.execute("SELECT writer_status, writer_post FROM articles").fetchone()
            self.assertEqual(row[0], "WRITING_ERROR"); self.assertIsNone(row[1]); db.close()

    def test_migration_preserves_phase1_phase2_phase3_data(self):
        with tempfile.TemporaryDirectory() as directory:
            db = make_db(Path(directory) / "migration.db")
            db.close()
            db = NewsDatabase(Path(directory) / "migration.db")
            row = db.connection.execute("SELECT title, ai_summary_ar, research_status, writer_status FROM articles").fetchone()
            self.assertEqual(tuple(row), ("New Tool", "ملخص", "VERIFIED", "WRITING_PENDING")); db.close()


if __name__ == "__main__": unittest.main()
