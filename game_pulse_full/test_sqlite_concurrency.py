import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path

import db


class SQLiteConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.old_path = db.DATABASE_PATH
        db.DATABASE_PATH = Path(self.temp_dir.name) / "concurrency.db"
        db.init_db()
        db.replace_section(
            "hot",
            [
                {
                    "game_key": "test:game",
                    "title": "Test Game",
                    "pulse_score": 42,
                }
            ],
        )

    def tearDown(self):
        db.DATABASE_PATH = self.old_path
        self.temp_dir.cleanup()

    def test_database_uses_wal(self):
        with sqlite3.connect(db.DATABASE_PATH) as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        self.assertEqual(mode.lower(), "wal")

    def test_context_manager_closes_connection(self):
        with db.connect() as conn:
            conn.execute("SELECT 1").fetchone()
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_reader_is_not_blocked_by_background_writer(self):
        writer_started = threading.Event()

        def hold_write_transaction():
            with db.connect() as conn:
                conn.execute("BEGIN EXCLUSIVE")
                conn.execute(
                    "UPDATE games SET pulse_score=? WHERE game_key=?",
                    (99, "test:game"),
                )
                writer_started.set()
                time.sleep(0.6)

        thread = threading.Thread(target=hold_write_transaction)
        thread.start()
        self.assertTrue(writer_started.wait(timeout=1))

        started = time.monotonic()
        games = db.get_games("hot", 1)
        elapsed = time.monotonic() - started

        thread.join(timeout=2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(games[0]["title"], "Test Game")
        self.assertLess(elapsed, 0.3)


if __name__ == "__main__":
    unittest.main()
