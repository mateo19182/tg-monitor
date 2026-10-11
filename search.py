#!/usr/bin/env python3
"""Full-text search over the archive. The HTTP layer does not depend on SQLite.

  python search.py --index          # initialise once; triggers maintain the index
  python search.py --index --rebuild
"""
import argparse
import csv
import re
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "tg.db"
WATCHLIST = HERE / "channels.csv"
PAGE_SIZE = 25
QUERY_TIMEOUT = 3


class InvalidSearch(ValueError):
    """The exception message is a language-independent error code."""


class SearchTimeout(Exception):
    pass


class SearchUnavailable(Exception):
    pass


@dataclass(frozen=True)
class SearchRequest:
    query: str
    channel: str = ""
    date_from: str = ""
    date_to: str = ""
    sort: str = "relevance"
    page: int = 1

    @classmethod
    def from_params(cls, params: dict[str, str]) -> "SearchRequest":
        query = params.get("q", "").strip()
        if len(query) > 300:
            raise InvalidSearch("query_too_long")
        # Validate here as well as constructing MATCH below, before any database work.
        match_query(query)
        lo, hi = params.get("from", ""), params.get("to", "")
        for value in (lo, hi):
            if value:
                try:
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                        raise ValueError
                    date.fromisoformat(value) + timedelta(days=1)
                except (ValueError, OverflowError):
                    raise InvalidSearch("invalid_date") from None
        if lo and hi and lo > hi:
            raise InvalidSearch("date_range")
        sort = params.get("sort", "relevance")
        if sort not in ("relevance", "newest", "oldest"):
            raise InvalidSearch("invalid_sort")
        page = params.get("page", "1")
        if not re.fullmatch(r"[1-9][0-9]{0,5}", page):
            raise InvalidSearch("invalid_page")
        channel = params.get("channel", "").strip().removeprefix("@").lower()
        if channel and not re.fullmatch(r"[a-z0-9_]{1,64}", channel):
            raise InvalidSearch("invalid_channel")
        return cls(query, channel, lo, hi, sort, int(page))


def match_query(query: str) -> str:
    """Words are ANDed; quoted text is a phrase. Never accept raw FTS syntax."""
    if not query or query.count('"') % 2:
        raise InvalidSearch("invalid_query")
    terms = []
    for phrase, word in re.findall(r'"([^"]*)"|([^\s"]+)', query):
        term = (phrase or word).strip()
        if not any(c.isalnum() for c in term):
            raise InvalidSearch("invalid_query")
        terms.append('"' + term.replace('"', '""') + '"')
    if not terms or len(terms) > 20:
        raise InvalidSearch("invalid_query")
    return " AND ".join(terms)


def ensure_index(db_path: Path = DB, *, rebuild: bool = False) -> None:
    """Install and populate atomically; collected inserts/edits/deletes stay in sync."""
    with closing(sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=rw", uri=True, timeout=60)) as db:
        required = {"message_search", "message_search_insert", "message_search_delete", "message_search_update"}
        installed = {r[0] for r in db.execute(
            "SELECT name FROM sqlite_master WHERE name IN (?,?,?,?)", tuple(required))}
        if not rebuild and required <= installed:
            return
        db.execute("BEGIN IMMEDIATE")
        try:
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='message_search'").fetchone()
            db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS message_search USING fts5("
                       "text, content='messages', content_rowid='rowid', "
                       "tokenize='unicode61 remove_diacritics 2')")
            db.execute("""CREATE TRIGGER IF NOT EXISTS message_search_insert AFTER INSERT ON messages BEGIN
                INSERT INTO message_search(rowid, text) VALUES (new.rowid, new.text);
            END""")
            db.execute("""CREATE TRIGGER IF NOT EXISTS message_search_delete AFTER DELETE ON messages BEGIN
                INSERT INTO message_search(message_search, rowid, text) VALUES ('delete', old.rowid, old.text);
            END""")
            db.execute("""CREATE TRIGGER IF NOT EXISTS message_search_update AFTER UPDATE OF text ON messages
                WHEN old.text IS NOT new.text BEGIN
                INSERT INTO message_search(message_search, rowid, text) VALUES ('delete', old.rowid, old.text);
                INSERT INTO message_search(rowid, text) VALUES (new.rowid, new.text);
            END""")
            if not exists or rebuild:
                db.execute("INSERT INTO message_search(message_search) VALUES ('rebuild')")
            db.commit()
        except Exception:
            db.rollback()
            raise


def snippet_parts(text: str) -> list[dict]:
    """Separate match spans from text, so the frontend never receives snippet HTML."""
    parts, matched = [], False
    for part in re.split(r"([\x01\x02])", text[:4000]):
        if part == "\x01":
            matched = True
        elif part == "\x02":
            matched = False
        elif part:
            parts.append({"text": part, "match": matched})
    return parts


def search_messages(request: SearchRequest, *, db_path: Path = DB,
                    watchlist_path: Path = WATCHLIST) -> dict:
    """Return paginated results for indexed channels. All storage-specific code lives here."""
    try:
        with watchlist_path.open(newline="", encoding="utf-8") as f:
            handles = [r["handle"].lower() for r in csv.DictReader(f)
                       if r.get("handle") and not r["handle"].startswith("#")]
    except OSError as e:
        raise SearchUnavailable from e
    if request.channel and request.channel not in handles:
        raise InvalidSearch("invalid_channel")
    where = ["message_search MATCH ?", f"lower(c.username) IN ({','.join('?' for _ in handles)})"]
    params = [match_query(request.query), *handles]
    if request.channel:
        where.append("lower(c.username) = ?")
        params.append(request.channel)
    if request.date_from:
        where.append("m.date >= ?")
        params.append(request.date_from)
    if request.date_to:
        where.append("m.date < ?")
        params.append((date.fromisoformat(request.date_to) + timedelta(days=1)).isoformat())
    relation = (" FROM message_search JOIN messages m ON m.rowid=message_search.rowid "
                "JOIN channels c ON c.id=m.channel_id WHERE " + " AND ".join(where))
    order = {"relevance": "message_search.rank, m.date DESC, m.channel_id, m.msg_id",
             "newest": "m.date DESC, m.channel_id, m.msg_id DESC",
             "oldest": "m.date, m.channel_id, m.msg_id"}[request.sort]
    try:
        with closing(sqlite3.connect(f"{db_path.resolve().as_uri()}?mode=ro", uri=True, timeout=1)) as db:
            db.row_factory = sqlite3.Row
            deadline = time.monotonic() + QUERY_TIMEOUT
            db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            db.execute("BEGIN")  # Count and page describe the same snapshot.
            total = db.execute("SELECT COUNT(*)" + relation, params).fetchone()[0]
            rows = db.execute(
                "SELECT m.channel_id, m.msg_id, m.date, c.username AS handle, c.title, "
                "snippet(message_search, 0, char(1), char(2), '…', 48) AS excerpt" + relation +
                " ORDER BY " + order + " LIMIT ? OFFSET ?",
                [*params, PAGE_SIZE, (request.page - 1) * PAGE_SIZE]).fetchall()
    except sqlite3.Error as e:
        if e.sqlite_errorcode == sqlite3.SQLITE_INTERRUPT:
            raise SearchTimeout from e
        raise SearchUnavailable from e
    results = []
    for row in rows:
        results.append({"channel_id": row["channel_id"], "msg_id": row["msg_id"],
                        "handle": row["handle"], "title": row["title"], "date": row["date"],
                        "snippet": snippet_parts(row["excerpt"]),
                        "url": f"https://t.me/{row['handle']}/{row['msg_id']}"})
    return {"query": request.query, "total": total, "page": request.page, "page_size": PAGE_SIZE,
            "has_next": request.page * PAGE_SIZE < total, "results": results}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--index", action="store_true", required=True)
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--db", type=Path, default=DB)
    args = ap.parse_args()
    ensure_index(args.db, rebuild=args.rebuild)
    print("Message search index ready.")


if __name__ == "__main__":
    main()
