"""Search behaviour, index maintenance, and the public HTTP contract."""
import csv
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import urlopen

from search import InvalidSearch, SearchRequest, SearchTimeout, SearchUnavailable, ensure_index, search_messages
from server import make_server


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.db_path, self.watchlist = self.root / "archive.db", self.root / "channels.csv"
        with self.watchlist.open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["handle"])
            w.writerows([["canal_uno"], ["canal_dos"], ["#comment"]])
        self.db = sqlite3.connect(self.db_path)
        self.addCleanup(self.db.close)
        self.db.executescript("""
            CREATE TABLE channels(id INTEGER PRIMARY KEY, username TEXT, title TEXT);
            CREATE TABLE messages(channel_id INTEGER, msg_id INTEGER, date TEXT, text TEXT, views INTEGER,
                PRIMARY KEY(channel_id, msg_id));
            INSERT INTO channels VALUES (1, 'canal_uno', 'Canal <uno>'), (2, 'canal_dos', 'Канал'),
                (3, 'unlisted', 'Not in the index');
        """)
        self.db.executemany("INSERT INTO messages VALUES (?,?,?,?,0)", [
            (1, 1, "2026-01-01T00:00:00+00:00", 'Elección Madrid <img src=x onerror="alert(1)">'),
            (1, 2, "2026-01-01T23:59:59+00:00", "Eleccion en Madrid"),
            (1, 3, "2026-01-02T00:00:00+00:00", "Madrid elección"),
            (1, 4, "2026-01-02T00:00:00+00:00", "Madrid OR Barcelona"),
            (2, 1, "2026-01-02T00:00:00+00:00", "МОСКВА Москва"),
            (3, 1, "2026-01-01T12:00:00+00:00", "Elección Madrid"),
            *[(1, i, "2026-02-01T12:00:00+00:00", "paginación archivo") for i in range(10, 45)],
        ])
        self.db.commit()
        ensure_index(self.db_path)

    def search(self, **params):
        return search_messages(SearchRequest.from_params(params), db_path=self.db_path,
                               watchlist_path=self.watchlist)

    def test_words_phrases_accents_and_scope(self):
        self.assertEqual(self.search(q="ELECCION madrid")["total"], 3)
        phrase = self.search(q='"elección madrid"')
        self.assertEqual([(r["channel_id"], r["msg_id"]) for r in phrase["results"]], [(1, 1)])
        self.assertEqual(self.search(q="москва")["total"], 1)
        # OR is a word, not a way to inject full-text query operators.
        self.assertEqual(self.search(q="Madrid OR Barcelona")["total"], 1)

    def test_filters_and_inclusive_utc_end_date(self):
        result = self.search(q="eleccion", channel="@CANAL_UNO", **{"from": "2026-01-01", "to": "2026-01-01"})
        self.assertEqual(result["total"], 2)
        self.assertEqual(self.search(q="eleccion", channel="canal_dos")["total"], 0)
        self.assertEqual(self.search(q="eleccion", **{"from": "2026-01-02"})["total"], 1)
        with self.assertRaisesRegex(InvalidSearch, "invalid_channel"):
            self.search(q="eleccion", channel="unlisted")

    def test_pagination_and_sorting(self):
        first, second = self.search(q="paginacion"), self.search(q="paginacion", page="2")
        self.assertEqual(first["total"], 35)
        self.assertEqual(len(first["results"]), 25)
        self.assertEqual(len(second["results"]), 10)
        self.assertTrue(first["has_next"])
        self.assertFalse(second["has_next"])
        ids = [r["msg_id"] for r in first["results"] + second["results"]]
        self.assertEqual(len(set(ids)), 35)
        newest = self.search(q="eleccion", sort="newest")["results"]
        oldest = self.search(q="eleccion", sort="oldest")["results"]
        self.assertEqual([r["msg_id"] for r in newest], [3, 2, 1])
        self.assertEqual([r["msg_id"] for r in oldest], [1, 2, 3])

    def test_snippets_preserve_text_and_separate_matches(self):
        result = self.search(q='"elección madrid"')["results"][0]
        self.assertEqual(result["url"], "https://t.me/canal_uno/1")
        self.assertIn('<img src=x onerror="alert(1)">', ''.join(p["text"] for p in result["snippet"]))
        self.assertTrue(any(p["match"] for p in result["snippet"]))

    def test_index_tracks_inserts_upserts_empty_text_and_deletes(self):
        self.db.execute("INSERT INTO messages VALUES (1,100,'2026-01-01T00:00:00+00:00','originalterm',0)")
        self.db.commit()
        self.assertEqual(self.search(q="originalterm")["total"], 1)
        self.db.execute("""INSERT INTO messages VALUES (1,100,'2026-01-01T00:00:00+00:00','replacementterm',5)
            ON CONFLICT(channel_id,msg_id) DO UPDATE SET text=excluded.text, views=excluded.views""")
        self.db.commit()
        self.assertEqual(self.search(q="originalterm")["total"], 0)
        self.assertEqual(self.search(q="replacementterm")["total"], 1)
        # Engagement-only refreshes must not disturb the text index.
        self.db.execute("UPDATE messages SET text=text, views=10 WHERE msg_id=100")
        self.db.commit()
        ensure_index(self.db_path)
        self.assertEqual(self.search(q="replacementterm")["total"], 1)
        self.db.execute("UPDATE messages SET text='' WHERE msg_id=100")
        self.db.commit()
        self.assertEqual(self.search(q="replacementterm")["total"], 0)
        self.db.execute("DELETE FROM messages WHERE msg_id=1 AND channel_id=1")
        self.db.commit()
        self.assertEqual(self.search(q='"elección madrid"')["total"], 0)
        self.db.execute("INSERT INTO message_search(message_search, rank) VALUES ('integrity-check', 1)")

    def test_existing_index_startup_does_not_take_a_write_lock(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            ensure_index(self.db_path)
        finally:
            self.db.rollback()

    def test_invalid_requests(self):
        cases = [({"q": ""}, "invalid_query"), ({"q": '"unclosed'}, "invalid_query"),
                 ({"q": "***"}, "invalid_query"), ({"q": "term " * 21}, "invalid_query"),
                 ({"q": "x" * 301}, "query_too_long"), ({"from": "2026-02-30"}, "invalid_date"),
                 ({"to": "9999-12-31"}, "invalid_date"),
                 ({"from": "2026-02-01", "to": "2026-01-01"}, "date_range"),
                 ({"sort": "rank; DROP TABLE messages"}, "invalid_sort"),
                 ({"page": "-1"}, "invalid_page"), ({"page": "1.5"}, "invalid_page"),
                 ({"channel": "' OR 1=1 --"}, "invalid_channel")]
        for params, code in cases:
            with self.subTest(params=params), self.assertRaisesRegex(InvalidSearch, code):
                SearchRequest.from_params({"q": "madrid", **params})

    def test_query_timeout(self):
        self.db.executemany("INSERT INTO messages VALUES (1,?,'2026-01-01T00:00:00+00:00','timeoutterm',0)",
                            [(i,) for i in range(1000, 2000)])
        self.db.commit()
        with patch("search.QUERY_TIMEOUT", -1), self.assertRaises(SearchTimeout):
            self.search(q="timeoutterm")

    def test_missing_database_reports_unavailable_without_creating_it(self):
        missing = self.root / "missing.db"
        with self.assertRaises(SearchUnavailable):
            search_messages(SearchRequest.from_params({"q": "madrid"}), db_path=missing,
                            watchlist_path=self.watchlist)
        self.assertFalse(missing.exists())

    def test_http_contract(self):
        site = self.root / "site"
        site.mkdir()
        (site / "index.html").write_text("archive")
        with patch("server.ArchiveHandler.log_message"):
            server = make_server(0, directory=site, db_path=self.db_path, watchlist_path=self.watchlist)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with urlopen(base + "/") as response:
                    self.assertEqual(response.read(), b"archive")
                with urlopen(base + "/api/search?" + urlencode({"q": '"elección madrid"'})) as response:
                    self.assertEqual(response.headers["Cache-Control"], "no-store")
                    data = json.load(response)
                    self.assertEqual(data["total"], 1)
                for query in ("q=", "q=one&q=two", "q=madrid&page=0", "q=madrid&to=bad"):
                    with self.subTest(query=query), self.assertRaises(HTTPError) as caught:
                        urlopen(base + "/api/search?" + query)
                    self.assertEqual(caught.exception.code, 400)
                    self.assertIn("error", json.load(caught.exception))
                with self.assertRaises(HTTPError) as caught:
                    urlopen(base + "/api/unknown")
                self.assertEqual(caught.exception.code, 404)
                for error, code in [(SearchTimeout, "search_timeout"), (SearchUnavailable, "search_unavailable")]:
                    with patch("server.search_messages", side_effect=error), patch("server.log.exception"):
                        with self.assertRaises(HTTPError) as caught:
                            urlopen(base + "/api/search?q=madrid")
                        self.assertEqual(caught.exception.code, 503)
                        self.assertEqual(json.load(caught.exception)["error"], code)
                with self.assertRaises(HTTPError) as caught:
                    urlopen(base + "/../archive.db")
                self.assertEqual(caught.exception.code, 404)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == "__main__":
    unittest.main()
