#!/usr/bin/env python3
"""Archive public Telegram channels into SQLite. Idempotent and resumable.

  python collect.py                      # every channel in channels.csv
  python collect.py RybarESP herQles     # subset
  python collect.py --resolve "Eureka News"   # search Telegram for a channel by name
  python collect.py --refetch RybarESP        # re-walk full history to fill columns added later

Each run, per channel: (1) fetch messages newer than the last stored id (full history on the
first run, or from the channel's `since` date), (2) refresh views/forwards for the last 7 days,
(3) record outcome in sync_state. A crash or reboot mid-channel loses nothing: the next run
resumes from the last committed id. Errors on one channel never stop the others.
"""
import argparse
import asyncio
import csv
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient, functions
from telethon.errors import ChannelPrivateError, FloodWaitError, RPCError, TakeoutInitDelayError, UsernameInvalidError, UsernameNotOccupiedError
from telethon.tl.types import (
    MessageEntityTextUrl,
    MessageEntityUrl,
    MessageMediaDocument,
    MessageMediaPhoto,
    MessageMediaWebPage,
    PeerChannel,
)

HERE = Path(__file__).resolve().parent
load_dotenv(HERE / ".env")
API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]
SESSION = str(HERE / "tgmon")
DB = HERE / "tg.db"
WATCHLIST = HERE / "channels.csv"
COMMIT_EVERY = 200
REFRESH_DAYS = 7
MAX_FLOOD_WAIT = 600  # sleep through waits up to this; longer ones are deferred to the next run

log = logging.getLogger("collect")
RESOLVE = {"blocked_until": datetime.min.replace(tzinfo=timezone.utc), "count": 0, "cap": 80, "pause": 3.0}


class ResolveDeferred(Exception):
    """A new handle could not be resolved this run (flood wait or cap); try again next run."""


SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
  id INTEGER PRIMARY KEY, username TEXT, title TEXT, about TEXT, tier TEXT,
  participants INTEGER, created_at TEXT, first_seen TEXT, last_synced TEXT
);
CREATE TABLE IF NOT EXISTS messages (
  channel_id INTEGER, msg_id INTEGER, date TEXT, text TEXT,
  views INTEGER, forwards INTEGER, replies INTEGER,
  fwd_from_channel_id INTEGER, fwd_from_msg_id INTEGER, fwd_from_name TEXT, fwd_date TEXT,
  reply_to_msg_id INTEGER, media TEXT, urls TEXT, grouped_id INTEGER,
  edit_date TEXT, fetched_at TEXT, sender_id INTEGER,
  media_id INTEGER, media_size INTEGER, media_mime TEXT, media_duration REAL, media_w INTEGER, media_h INTEGER,
  PRIMARY KEY (channel_id, msg_id)
);
CREATE INDEX IF NOT EXISTS idx_messages_date ON messages(date);
CREATE INDEX IF NOT EXISTS idx_messages_fwd ON messages(fwd_from_channel_id);
CREATE TABLE IF NOT EXISTS fwd_sources (
  channel_id INTEGER PRIMARY KEY, username TEXT, title TEXT, participants INTEGER
);
CREATE TABLE IF NOT EXISTS sync_state (
  handle TEXT PRIMARY KEY, channel_id INTEGER, last_msg_id INTEGER,
  last_run TEXT, last_ok TEXT, last_error TEXT, new_msgs INTEGER, backfill_done INTEGER DEFAULT 0
);
"""


def open_db() -> sqlite3.Connection:
    db = sqlite3.connect(DB, timeout=60)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.executescript(SCHEMA)
    # forward-compatible column adds
    cols = {r[1] for r in db.execute("PRAGMA table_info(channels)")}
    if "tier" not in cols:
        db.execute("ALTER TABLE channels ADD COLUMN tier TEXT")
    cols = {r[1] for r in db.execute("PRAGMA table_info(messages)")}
    for col, typ in [("sender_id", "INTEGER"), ("media_id", "INTEGER"), ("media_size", "INTEGER"), ("media_mime", "TEXT"),
                     ("media_duration", "REAL"), ("media_w", "INTEGER"), ("media_h", "INTEGER")]:
        if col not in cols:
            db.execute(f"ALTER TABLE messages ADD COLUMN {col} {typ}")
    db.execute("CREATE INDEX IF NOT EXISTS idx_messages_media ON messages(media_id)")
    cols = {r[1] for r in db.execute("PRAGMA table_info(fwd_sources)")}
    if "participants" not in cols:
        db.execute("ALTER TABLE fwd_sources ADD COLUMN participants INTEGER")
    return db


def load_watchlist(only: list[str]) -> list[dict]:
    with WATCHLIST.open(newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("handle") and not r["handle"].startswith("#")]
    if only:
        want = {h.lower().lstrip("@") for h in only}
        rows = [r for r in rows if r["handle"].lower() in want]
        missing = want - {r["handle"].lower() for r in rows}
        for h in missing:  # allow ad-hoc handles not in the csv
            rows.append({"handle": h, "tier": "adhoc", "since": ""})
    return rows


def media_kind(m) -> str | None:
    if m is None:
        return None
    if isinstance(m, MessageMediaPhoto):
        return "photo"
    if isinstance(m, MessageMediaWebPage):
        return "webpage"
    if isinstance(m, MessageMediaDocument):
        mt = getattr(m.document, "mime_type", "") or ""
        return "video" if mt.startswith("video") else "document"
    return type(m).__name__.replace("MessageMedia", "").lower()


def media_info(m) -> tuple:
    """Stable Telegram ids + metadata, no download. The same photo/document id across channels
    means the same file was re-posted (copy-paste), which forwards alone do not reveal."""
    if isinstance(m, MessageMediaPhoto) and m.photo:
        sizes = [sz for sz in (m.photo.sizes or []) if hasattr(sz, "w")]
        big = max(sizes, key=lambda sz: sz.w * sz.h) if sizes else None
        size = None
        if big is not None:
            size = getattr(big, "size", None) or (max(big.sizes) if getattr(big, "sizes", None) else None)  # progressive JPEGs list sizes
        return (m.photo.id, size, "image/jpeg", None, getattr(big, "w", None), getattr(big, "h", None))
    if isinstance(m, MessageMediaDocument) and m.document:
        d = m.document
        dur = w = h = None
        for a in d.attributes or []:
            dur = getattr(a, "duration", dur)
            w = getattr(a, "w", w)
            h = getattr(a, "h", h)
        return (d.id, d.size, d.mime_type, dur, w, h)
    return (None, None, None, None, None, None)


def extract_urls(msg) -> list[str]:
    urls = []
    for ent in msg.entities or []:
        if isinstance(ent, MessageEntityTextUrl):
            urls.append(ent.url)
        elif isinstance(ent, MessageEntityUrl):
            urls.append(msg.raw_text[ent.offset : ent.offset + ent.length])
    if isinstance(msg.media, MessageMediaWebPage) and getattr(msg.media.webpage, "url", None):
        urls.append(msg.media.webpage.url)
    return urls


def row_from(msg, channel_id: int, now: str) -> tuple:
    fwd = msg.fwd_from
    fwd_chan = fwd_msg = fwd_name = fwd_date = None
    if fwd:
        if isinstance(fwd.from_id, PeerChannel):
            fwd_chan = fwd.from_id.channel_id
        fwd_msg = fwd.channel_post
        fwd_name = fwd.from_name or fwd.post_author
        fwd_date = fwd.date.isoformat() if fwd.date else None
    return (
        channel_id, msg.id, msg.date.isoformat(), msg.raw_text or "",
        msg.views, msg.forwards, (msg.replies.replies if msg.replies else None),
        fwd_chan, fwd_msg, fwd_name, fwd_date,
        (msg.reply_to.reply_to_msg_id if msg.reply_to else None),
        media_kind(msg.media), json.dumps(extract_urls(msg)), msg.grouped_id,
        (msg.edit_date.isoformat() if msg.edit_date else None), now,
        (msg.sender_id if msg.sender_id and msg.sender_id != channel_id else None),  # users in groups; NULL for the channel itself
        *media_info(msg.media),
    )


UPSERT = """
INSERT INTO messages (channel_id,msg_id,date,text,views,forwards,replies,fwd_from_channel_id,fwd_from_msg_id,fwd_from_name,fwd_date,reply_to_msg_id,media,urls,grouped_id,edit_date,fetched_at,sender_id,media_id,media_size,media_mime,media_duration,media_w,media_h) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(channel_id, msg_id) DO UPDATE SET
  text=excluded.text, views=excluded.views, forwards=excluded.forwards,
  replies=excluded.replies, edit_date=excluded.edit_date, fetched_at=excluded.fetched_at, sender_id=excluded.sender_id,
  media_id=excluded.media_id, media_size=excluded.media_size, media_mime=excluded.media_mime,
  media_duration=excluded.media_duration, media_w=excluded.media_w, media_h=excluded.media_h
"""


async def with_retries(coro_fn, what: str, tries: int = 3):
    for attempt in range(1, tries + 1):
        try:
            return await coro_fn()
        except FloodWaitError as e:
            if e.seconds > MAX_FLOOD_WAIT:
                raise
            log.warning("%s: flood wait %ss (attempt %d)", what, e.seconds, attempt)
            await asyncio.sleep(e.seconds + 1)
        except (ConnectionError, TimeoutError, OSError) as e:
            if attempt == tries:
                raise
            log.warning("%s: %s (attempt %d), retrying", what, e, attempt)
            await asyncio.sleep(5 * attempt)


async def sync_channel(client: TelegramClient, db: sqlite3.Connection, spec: dict, refetch: bool = False, takeout=None) -> None:
    handle = spec["handle"]
    since = None
    if spec.get("since"):
        since = datetime.fromisoformat(spec["since"]).replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc).isoformat()
    db.execute("INSERT OR IGNORE INTO sync_state (handle) VALUES (?)", (handle,))
    db.execute("UPDATE sync_state SET last_run=?, last_error=NULL WHERE handle=?", (now, handle))
    db.commit()

    # Resolve the channel. Username resolution (ResolveUsernameRequest) is the most rate-limited call we make
    # (a burst of ~150 new handles earned an 11-hour FloodWait on 2026-10-12), so once a channel's id is known we
    # address it by id, which only touches the session's entity cache. Fresh usernames are resolved with pacing.
    known = db.execute("SELECT id FROM channels WHERE lower(username)=lower(?)", (handle,)).fetchone()
    if handle.isdigit():
        target = PeerChannel(int(handle))  # numeric ids = joined private groups
    elif known:
        target = PeerChannel(known[0])
    else:
        if RESOLVE["blocked_until"] > datetime.now(timezone.utc):
            raise ResolveDeferred(f"username resolution blocked until {RESOLVE['blocked_until']:%H:%M} UTC")
        if RESOLVE["count"] >= RESOLVE["cap"]:
            raise ResolveDeferred(f"resolve cap {RESOLVE['cap']} reached this run")
        target = handle
    try:
        ent = await with_retries(lambda: client.get_entity(target), handle)
    except ValueError:  # id not in the session cache (e.g. db restored elsewhere): fall back to the username
        ent = await with_retries(lambda: client.get_entity(handle), handle)
    except FloodWaitError as e:
        if target is handle:
            RESOLVE["blocked_until"] = datetime.now(timezone.utc) + timedelta(seconds=e.seconds)
            log.warning("[%s] ResolveUsername flood wait %ss; deferring remaining new handles this run", handle, e.seconds)
            raise ResolveDeferred(f"flood wait {e.seconds}s on resolve")
        raise
    if target is handle:
        RESOLVE["count"] += 1
        await asyncio.sleep(RESOLVE["pause"])
    # Channel metadata: refresh at most once a day unless this is the first fetch (GetFullChannel is cheap but
    # 470 calls an hour is pointless).
    stale = db.execute("SELECT last_synced FROM channels WHERE id=? AND last_synced > datetime('now','-1 day')", (ent.id,)).fetchone()
    if not known or not stale:
        full = await with_retries(lambda: client(functions.channels.GetFullChannelRequest(ent)), handle)
        about, participants = full.full_chat.about, full.full_chat.participants_count
    else:
        about, participants = None, None
    db.execute(
        "INSERT INTO channels (id, username, title, about, tier, participants, created_at, first_seen, last_synced) "
        "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET username=excluded.username, title=excluded.title, "
        "about=COALESCE(excluded.about, channels.about), tier=excluded.tier, "
        "participants=COALESCE(excluded.participants, channels.participants), last_synced=excluded.last_synced",
        (ent.id, ent.username, ent.title, about, spec.get("tier"), participants,
         ent.date.isoformat() if ent.date else None, now, now),
    )
    db.commit()

    last = db.execute("SELECT MAX(msg_id) FROM messages WHERE channel_id=?", (ent.id,)).fetchone()[0] or 0
    if refetch:
        last = 0  # walk everything again; UPSERT refreshes columns in place
    n = 0
    # With --takeout, full backfills go through a Takeout session; hourly increments always use the normal
    # client. Measured 2026-10-12: no gain over normal reads here (the collector is latency-bound), so off by default.
    reader = takeout if (takeout is not None and last == 0) else client
    if reader is takeout:
        log.info("[%s] backfill via takeout", handle)
    # (1) new messages, oldest first so a crash leaves a contiguous prefix
    async for msg in reader.iter_messages(ent, min_id=last, reverse=True, offset_date=since if last == 0 else None):
        db.execute(UPSERT, row_from(msg, ent.id, now))
        n += 1
        if n % COMMIT_EVERY == 0:
            db.commit()
        if n % 2000 == 0:
            log.info("[%s] %d msgs...", handle, n)
    db.commit()
    # (2) refresh engagement on the last week (views/forwards keep changing after publication)
    cutoff = datetime.now(timezone.utc) - timedelta(days=REFRESH_DAYS)
    async for msg in client.iter_messages(ent, offset_date=cutoff, reverse=True, max_id=last):
        db.execute(UPSERT, row_from(msg, ent.id, now))
    db.commit()

    new_last = db.execute("SELECT MAX(msg_id) FROM messages WHERE channel_id=?", (ent.id,)).fetchone()[0] or 0
    total = db.execute("SELECT COUNT(*) FROM messages WHERE channel_id=?", (ent.id,)).fetchone()[0]
    db.execute(
        "UPDATE sync_state SET channel_id=?, last_msg_id=?, last_ok=?, new_msgs=?, backfill_done=1 WHERE handle=?",
        (ent.id, new_last, datetime.now(timezone.utc).isoformat(), n, handle),
    )
    db.commit()
    log.info("[%s] +%d new, %d total, %s subscribers", handle, n, total, participants if participants is not None else "cached")


async def resolve_fwd_sources(client: TelegramClient, db: sqlite3.Connection, limit: int = 200) -> None:
    """Fill in username/title for channels that appear only as forward origins (bounded per run)."""
    ids = [r[0] for r in db.execute(
        "SELECT fwd_from_channel_id, COUNT(*) c FROM messages WHERE fwd_from_channel_id IS NOT NULL "
        "AND fwd_from_channel_id NOT IN (SELECT channel_id FROM fwd_sources) GROUP BY 1 ORDER BY c DESC LIMIT ?", (limit,)
    )]
    for cid in ids:
        try:
            ent = await client.get_entity(PeerChannel(cid))
            db.execute("INSERT OR REPLACE INTO fwd_sources VALUES (?,?,?,?)",
                       (cid, ent.username, ent.title, getattr(ent, "participants_count", None)))
        except FloodWaitError as e:
            log.warning("fwd_sources: flood wait %ss, stopping for this run", e.seconds)
            break
        except Exception:  # private/deleted/unreachable: remember so we don't retry forever
            db.execute("INSERT OR REPLACE INTO fwd_sources VALUES (?,?,?,?)", (cid, None, None, None))
        await asyncio.sleep(0.3)
    db.commit()
    if ids:
        log.info("fwd_sources: resolved %d origin channels", len(ids))


async def resolve_name(client: TelegramClient, name: str) -> None:
    res = await client(functions.contacts.SearchRequest(q=name, limit=10))
    for c in res.chats:
        if getattr(c, "broadcast", False):
            print(f"@{c.username}\t{c.title}\tsubs={getattr(c, 'participants_count', None)}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("channels", nargs="*")
    ap.add_argument("--resolve", action="append", help="search Telegram for a channel by name; repeat for multiple names")
    ap.add_argument("--refetch", action="store_true", help="re-read full history of the given channels (fills new columns; no new rows expected)")
    ap.add_argument("--benchmark-takeout", action="store_true", help="compare normal and Takeout history reads; no archive writes")
    ap.add_argument("--takeout", action="store_true", help="read backfills through a Takeout session (measured no faster than normal reads here; off by default)")
    ap.add_argument("--concurrency", type=int, default=3, help="channels fetched in parallel (default 3)")
    ap.add_argument("--max-resolve", type=int, default=80, help="max new usernames resolved per run (ResolveUsername is heavily rate-limited)")
    ap.add_argument("--benchmark-messages", type=int, default=1000)
    ap.add_argument("--benchmark-rounds", type=int, default=2)
    args = ap.parse_args()
    if args.benchmark_messages <= 0 or args.benchmark_rounds <= 0:
        ap.error("benchmark messages and rounds must be positive")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stderr)
    logging.getLogger("telethon").setLevel(logging.WARNING)

    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.connect()
    if not await client.is_user_authorized():
        log.error("not logged in; run login.py first")
        sys.exit(1)
    try:
        if args.benchmark_takeout:
            from benchmark import run
            await run(client, args.channels or ["RybarESP", "infodefSPAIN"],
                      args.benchmark_messages, args.benchmark_rounds)
            return
        if args.resolve:
            for name in args.resolve:
                print(f"Search: {name}", flush=True)
                await resolve_name(client, name)
                await asyncio.sleep(3)
            return
        db = open_db()
        specs = load_watchlist(args.channels)
        RESOLVE["cap"] = args.max_resolve
        takeout = None
        needs_backfill = any(
            (db.execute("SELECT 1 FROM sync_state WHERE handle=? AND backfill_done=1", (sp["handle"],)).fetchone() is None) or args.refetch
            for sp in specs)
        if needs_backfill and args.takeout:
            try:
                takeout = await client.takeout(channels=True, files=False).__aenter__()
                log.info("takeout session open")
            except ValueError:  # a previous run was killed with its takeout still open
                try:
                    await client.end_takeout(success=False)
                    takeout = await client.takeout(channels=True, files=False).__aenter__()
                    log.info("takeout session open (stale one closed)")
                except Exception as e:  # noqa: BLE001
                    log.warning("takeout unavailable (%s); using normal reads this run", e)
            except TakeoutInitDelayError as e:
                log.warning("takeout refused for %ss; using normal reads this run", e.seconds)
            except RPCError as e:
                log.warning("takeout unavailable (%s); using normal reads this run", e)
        elif not args.takeout:
            try:  # clear any stale takeout left by an interrupted run so later --takeout runs work
                await client.end_takeout(success=False)
            except Exception:  # noqa: BLE001
                pass
        failed = 0
        sem = asyncio.Semaphore(max(1, args.concurrency))

        async def run_one(spec):
            nonlocal failed
            async with sem:
                try:
                    await sync_channel(client, db, spec, refetch=args.refetch, takeout=takeout)
                except ResolveDeferred as e:
                    db.execute("UPDATE sync_state SET last_error=? WHERE handle=?", (f"deferred: {e}", spec["handle"]))
                    db.commit()
                except FloodWaitError as e:
                    failed += 1
                    db.execute("UPDATE sync_state SET last_error=? WHERE handle=?", (f"flood wait {e.seconds}s", spec["handle"]))
                    db.commit()
                    log.error("[%s] flood wait %ss too long; deferred to next run", spec["handle"], e.seconds)
                except (UsernameInvalidError, UsernameNotOccupiedError, ChannelPrivateError, ValueError) as e:
                    failed += 1
                    db.execute("UPDATE sync_state SET last_error=? WHERE handle=?", (f"unreachable: {e}", spec["handle"]))
                    db.commit()
                    log.error("[%s] unreachable: %s", spec["handle"], e)
                except (RPCError, ConnectionError, OSError) as e:
                    failed += 1
                    db.execute("UPDATE sync_state SET last_error=? WHERE handle=?", (f"{type(e).__name__}: {e}", spec["handle"]))
                    db.commit()
                    log.exception("[%s] failed", spec["handle"])

        # Channels run a few at a time: a single history read is latency-bound (~100 msgs per round trip,
        # collector CPU ~4%), so modest concurrency multiplies throughput without touching per-method limits.
        await asyncio.gather(*(run_one(sp) for sp in specs))
        if takeout is not None:
            try:
                await takeout.__aexit__(None, None, None)
            except Exception as e:  # noqa: BLE001
                log.warning("takeout close: %s", e)
        await resolve_fwd_sources(client, db)
        deferred = db.execute("SELECT COUNT(*) FROM sync_state WHERE last_error LIKE 'deferred:%'").fetchone()[0]
        log.info("run complete: %d channels, %d failed, %d deferred (new handles awaiting resolution)", len(specs), failed, deferred)
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
