import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
import types


# The repository's runtime dependencies are installed on deployment. These tiny
# offline stubs let the data-shaping tests run in a dependency-free build sandbox;
# every HTTP request below is supplied by QueueSession.
try:
    import dotenv  # noqa: F401
except ModuleNotFoundError:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *args, **kwargs: None
    sys.modules["dotenv"] = dotenv_stub

try:
    import requests  # noqa: F401
except ModuleNotFoundError:
    requests_stub = types.ModuleType("requests")
    requests_stub.Session = object
    sys.modules["requests"] = requests_stub

import db
from services.wikipedia import WikipediaClient
from services.youtube import YouTubeClient


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class QueueSession:
    def __init__(self, get_payloads=None):
        self.get_payloads = list(get_payloads or [])
        self.get_calls = []

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        return FakeResponse(self.get_payloads.pop(0))

class ClientTests(unittest.TestCase):
    def test_youtube_collects_only_title_matches_and_sums_stats(self):
        session = QueueSession(get_payloads=[
            {
                "pageInfo": {"totalResults": 12},
                "items": [
                    {
                        "id": {"videoId": "abc"},
                        "snippet": {
                            "title": "Street Supremacy gameplay",
                            "description": "",
                            "channelTitle": "Tester",
                            "publishedAt": "2026-08-12T00:00:00Z",
                        },
                    },
                    {
                        "id": {"videoId": "wrong"},
                        "snippet": {"title": "Unrelated game", "description": ""},
                    },
                ],
            },
            {
                "items": [
                    {
                        "id": "abc",
                        "statistics": {"viewCount": "100", "likeCount": "7", "commentCount": "4"},
                    }
                ]
            },
        ])
        result = YouTubeClient(api_key="test", session=session).game_signal("Street Supremacy")
        self.assertEqual(result["matched_videos"], 1)
        self.assertEqual(result["sample_views"], 100)
        self.assertEqual(result["sample_comments"], 4)
        self.assertEqual(len(session.get_calls), 2)

    def test_wikipedia_resolves_article_and_builds_daily_signal(self):
        session = QueueSession(get_payloads=[
            {"query": {"search": [{"title": "The Choicer Voicer (video game)"}]}},
            {"items": [{"timestamp": f"2026080{i}00", "views": i * 10} for i in range(1, 9)]},
        ])
        result = WikipediaClient(session=session, user_agent="test-agent").game_signal("The Choicer Voicer")
        self.assertEqual(result["article_title"], "The Choicer Voicer (video game)")
        self.assertEqual(result["latest_daily_views"], 80)
        self.assertEqual(result["seven_day_views"], 350)

class StoreAndRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_path = db.DATABASE_PATH
        db.DATABASE_PATH = Path(self.temp.name) / "social-test.db"
        db.init_db()
        db.replace_section("hot", [{
            "game_key": "title:street supremacy",
            "title": "Street Supremacy",
            "platforms": [],
            "genres": [],
            "stores": [],
            "sources": [],
            "pulse_score": 50,
        }])

    def tearDown(self):
        db.DATABASE_PATH = self.old_path
        self.temp.cleanup()

    def test_snapshot_history_and_ttl_cache(self):
        db.save_social_signal(
            "title:street supremacy",
            "Street Supremacy",
            "Wikipedia",
            {"latest_daily_views": 42, "source_url": "https://example.test"},
            "https://example.test",
        )
        self.assertFalse(db.social_signal_is_stale("title:street supremacy", "Wikipedia", 24))
        payload = db.get_social_signals("title:street supremacy", history_days=7)
        self.assertFalse(payload["ranking_included"])
        self.assertEqual(payload["signals"][0]["metrics"]["latest_daily_views"], 42)
        self.assertEqual(len(payload["history"]), 1)

    def test_refresh_skips_optional_sources_and_caches_wikipedia(self):
        import services.social_signals as social

        class DisabledClient:
            enabled = False

        class FakeWikipedia:
            calls = 0
            enabled = True

            def game_signal(self, title):
                type(self).calls += 1
                return {
                    "status": "ok",
                    "article_title": title,
                    "latest_daily_views": 10,
                    "source_url": "https://example.test/wiki",
                }

        sources = (
            ("YouTube", DisabledClient),
            ("Wikipedia", FakeWikipedia),
        )
        games = db.get_games("hot", 10)
        with patch.object(social, "SOURCE_CLIENTS", sources):
            first = social.refresh_social_signals(games, ttl_hours=24)
            second = social.refresh_social_signals(games, ttl_hours=24)

        self.assertEqual(FakeWikipedia.calls, 1)
        self.assertEqual(next(x for x in first if x["source"] == "YouTube")["status"], "optional")
        self.assertIn("快取 1 款", next(x for x in second if x["source"] == "Wikipedia")["message"])

    def test_public_status_error_redacts_api_keys(self):
        import services.social_signals as social

        with patch.object(social, "YOUTUBE_API_KEY", "super-secret-key"):
            message = social._safe_error(
                RuntimeError("403 https://example.test/?key=super-secret-key&part=snippet")
            )
        self.assertNotIn("super-secret-key", message)
        self.assertIn("[redacted]", message)


if __name__ == "__main__":
    unittest.main()
