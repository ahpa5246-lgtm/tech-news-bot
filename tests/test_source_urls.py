import unittest
from research.source import retrieve_source,extract_article
class SourceUrls(unittest.TestCase):
 def test_malformed_ipv6_is_reported_instead_of_crashing_batch(self):
  self.assertIsNotNone(retrieve_source('https://[invalid',1,'test').error)
 def test_relative_canonical_is_resolved_against_final_url(self):
  page=b'<html><head><link rel="canonical" href="../story"></head><body><article><p>'+b'a'*150+b'</p></article></body></html>'
  self.assertEqual(extract_article(page,'https://example.test/news/article','https://example.test/start').canonical_url,'https://example.test/story')
