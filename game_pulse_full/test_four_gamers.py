import unittest
from unittest.mock import patch

import services.four_gamers as four_gamers
from services.four_gamers import filter_related_news, parse_feed


SAMPLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <item>
    <title>《ELDEN RING》更新公開</title>
    <link>https://www.4gamers.com.tw/news/detail/123/elden-ring-update</link>
    <description><![CDATA[<b>FromSoftware</b> 公開更新內容。]]></description>
    <pubDate>Fri, 14 Aug 2026 13:11:23 +0800</pubDate>
  </item>
  <item>
    <title>不安全連結不可出現</title>
    <link>https://example.com/not-allowed</link>
    <description>ignore</description>
  </item>
</channel></rss>"""


class FourGamersTests(unittest.TestCase):
    def test_parse_feed_keeps_short_safe_fields(self):
        rows = parse_feed(SAMPLE_RSS)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["feedlabel"], "4Gamers")
        self.assertEqual(rows[0]["contents"], "FromSoftware 公開更新內容。")
        self.assertTrue(rows[0]["published_at"].endswith("+00:00"))

    def test_related_news_requires_game_title_match(self):
        rows = parse_feed(SAMPLE_RSS)
        self.assertEqual(len(filter_related_news("ELDEN RING", rows)), 1)
        self.assertEqual(filter_related_news("Minecraft", rows), [])

    def test_failed_feed_uses_backoff_instead_of_repeated_requests(self):
        old_cache = dict(four_gamers._CACHE)
        four_gamers._CACHE.update({"at": 0.0, "failed_at": 0.0, "rows": []})
        try:
            with patch.object(four_gamers, "_download_feed", side_effect=RuntimeError("offline")) as download:
                self.assertEqual(four_gamers.latest_news(), [])
                self.assertEqual(four_gamers.latest_news(), [])
                self.assertEqual(download.call_count, 1)
        finally:
            four_gamers._CACHE.clear()
            four_gamers._CACHE.update(old_cache)


if __name__ == "__main__":
    unittest.main()
