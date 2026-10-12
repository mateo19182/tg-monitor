"""Links archive: every URL in archived messages, by domain and kind, with shorteners resolved and
titles fetched for content pages. Stored in links.db (separate from tg.db so the collector is never blocked).

  links.py index              # new messages since the last run -> links table (seconds; runs hourly from sync.sh)
  links.py resolve [--limit N]  # follow shortener redirects (t.co, ift.tt, bit.ly, ...) -> resolved table
  links.py fetch [--limit N] [--domain D]  # fetch <title>/description for content URLs, newest first, 1 req/s per domain
  links.py tme [--min 5]      # t.me handles referenced by watched channels but not on the watchlist (discovery feed)
  links.py domains [--top 40] # domain table
"""
import argparse, csv, json, logging, re, sqlite3, sys, time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

HERE = Path(__file__).resolve().parent
TG_DB, LINKS_DB = HERE / "tg.db", HERE / "links.db"
log = logging.getLogger("links")

SOCIAL = {"instagram.com", "x.com", "twitter.com", "youtube.com", "youtu.be", "facebook.com", "whatsapp.com", "chat.whatsapp.com",
          "vk.com", "bsky.app", "max.ru", "rutube.ru", "ok.ru", "dzen.ru", "tiktok.com", "threads.net", "rumble.com", "odysee.com",
          "twitch.tv", "linkedin.com", "pinterest.com", "reddit.com", "mastodon.social", "gettr.com", "truthsocial.com"}
SHORTENERS = {"t.co", "ift.tt", "bit.ly", "tinyurl.com", "goo.gl", "ow.ly", "cutt.ly", "acortar.link", "dlvr.it", "buff.ly", "is.gd",
              "rb.gy", "shorturl.at", "lnkd.in", "tiny.cc", "clck.ru", "vk.cc", "fb.me", "youtube.com/shorts"}
TELEGRAM = {"t.me", "telegram.me", "telegram.dog", "telegra.ph"}
TRACKING = re.compile(r"^(utm_|fbclid|gclid|yclid|mc_cid|mc_eid|ref$|ref_src|_branch|igshid|si$|feature$)")
TME = re.compile(r"^/(?:s/)?(?:c/)?(\+?[A-Za-z0-9_]{3,64})(?:/(\d+))?")
TME_RESERVED = {"boost", "addlist", "joinchat", "share", "proxy", "socks", "iv", "s", "c", "setlanguage", "bg", "login", "confphone",
                "giftcode", "invoice", "m", "nft", "contact", "addstickers", "addemoji", "addtheme", "web", "a", "k", "z", "premium", "stars"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS links (channel_id INTEGER, msg_id INTEGER, date TEXT, url TEXT, canon TEXT, domain TEXT, kind TEXT,
  PRIMARY KEY (channel_id, msg_id, url));
CREATE INDEX IF NOT EXISTS idx_links_domain ON links(domain);
CREATE INDEX IF NOT EXISTS idx_links_canon ON links(canon);
CREATE INDEX IF NOT EXISTS idx_links_date ON links(date);
CREATE TABLE IF NOT EXISTS resolved (url TEXT PRIMARY KEY, target TEXT, status INTEGER, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS pages (canon TEXT PRIMARY KEY, domain TEXT, title TEXT, description TEXT, status INTEGER, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS tme (channel_id INTEGER, msg_id INTEGER, date TEXT, handle TEXT, ref_msg_id INTEGER, PRIMARY KEY (channel_id, msg_id, handle, ref_msg_id));
CREATE INDEX IF NOT EXISTS idx_tme_handle ON tme(handle);
CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT);
"""


def open_db() -> sqlite3.Connection:
    db = sqlite3.connect(f"file:{LINKS_DB}", uri=True, timeout=60)
    db.execute("PRAGMA journal_mode=WAL"); db.execute("PRAGMA synchronous=NORMAL")
    db.executescript(SCHEMA)
    db.execute("ATTACH DATABASE ? AS tg", (f"file:{TG_DB}?mode=ro",))
    return db


def canonical(url: str) -> tuple[str, str] | None:
    """Return (canonical url, domain) or None for junk. Strips fragments, tracking params, trailing slashes, 'www.'."""
    u = url.strip().strip(").,;'\"<>[]")
    if "://" not in u:
        u = "https://" + u
    try:
        p = urlsplit(u)
    except ValueError:
        return None
    host = (p.hostname or "").lower().removeprefix("www.").removeprefix("m.").removeprefix("amp.")
    if not host or "." not in host or len(host) < 4 or host.endswith("."):
        return None
    q = urlencode([(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not TRACKING.match(k.lower())])
    path = re.sub(r"/+$", "", p.path) or "/"
    return urlunsplit(("https", host, path, q, "")), host


def kind_of(host: str, path: str) -> str:
    if host in TELEGRAM: return "telegram"
    if host in SHORTENERS or (host == "youtube.com" and path.startswith("/shorts")): return "shortener"
    if host in SOCIAL: return "social"
    return "content"


def index(db: sqlite3.Connection) -> None:
    last = (db.execute("SELECT value FROM state WHERE key='last_fetched_at'").fetchone() or ("",))[0]
    q = "SELECT channel_id, msg_id, date, urls, fetched_at FROM tg.messages WHERE urls IS NOT NULL AND urls != '[]' AND urls != ''"
    args: list = []
    if last:
        q += " AND fetched_at > ?"; args.append(last)
    q += " ORDER BY fetched_at"
    rows_l, rows_t, n, newest = [], [], 0, last
    for cid, mid, date, urls, fa in db.execute(q, args):
        try:
            lst = json.loads(urls)
        except json.JSONDecodeError:
            continue
        newest = max(newest, fa or ""); n += 1
        for raw in lst:
            c = canonical(raw)
            if not c: continue
            canon, host = c
            k = kind_of(host, urlsplit(canon).path)
            rows_l.append((cid, mid, date, raw[:2000], canon[:2000], host, k))
            if k == "telegram" and host in ("t.me", "telegram.me"):
                m = TME.match(urlsplit(canon).path)
                if m and not m.group(1).startswith("+") and m.group(1).lower() not in TME_RESERVED:
                    rows_t.append((cid, mid, date, m.group(1).lower(), int(m.group(2)) if m.group(2) else None))
        if len(rows_l) >= 20000:
            flush(db, rows_l, rows_t, newest); rows_l, rows_t = [], []
    flush(db, rows_l, rows_t, newest)
    log.info("indexed %d messages; links=%d tme=%d", n, db.execute("SELECT count(*) FROM links").fetchone()[0], db.execute("SELECT count(*) FROM tme").fetchone()[0])


def flush(db, rows_l, rows_t, newest):
    db.executemany("INSERT OR IGNORE INTO links VALUES (?,?,?,?,?,?,?)", rows_l)
    db.executemany("INSERT OR IGNORE INTO tme VALUES (?,?,?,?,?)", rows_t)
    if newest:
        db.execute("INSERT OR REPLACE INTO state VALUES ('last_fetched_at', ?)", (newest,))
    db.commit()


def _session():
    import requests
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0 (X11; Linux x86_64) tg-monitor-links/1.0 (research archive; contact via repo)"
    return s


def resolve(db: sqlite3.Connection, limit: int) -> None:
    s = _session()
    todo = [r[0] for r in db.execute("SELECT DISTINCT l.canon FROM links l LEFT JOIN resolved r ON r.url=l.canon WHERE l.kind='shortener' AND r.url IS NULL ORDER BY l.date DESC LIMIT ?", (limit,))]
    log.info("resolving %d shortener urls", len(todo)); ok = 0
    for i, u in enumerate(todo):
        target, status = None, None
        try:
            r = s.head(u, allow_redirects=True, timeout=10); target, status = r.url, r.status_code
            if target == u and status == 200:  # some shorteners need GET
                r = s.get(u, allow_redirects=True, timeout=10, stream=True); target, status = r.url, r.status_code; r.close()
        except Exception as e:
            status = -1; target = None
        db.execute("INSERT OR REPLACE INTO resolved VALUES (?,?,?,?)", (u, target, status, datetime.now(timezone.utc).isoformat(timespec="seconds")))
        if target and target != u:
            c = canonical(target)
            if c:
                db.execute("UPDATE links SET canon=?, domain=?, kind=? WHERE canon=?", (c[0][:2000], c[1], kind_of(c[1], urlsplit(c[0]).path), u)); ok += 1
        if i % 50 == 49: db.commit()
        time.sleep(0.2)
    db.commit(); log.info("resolved %d/%d", ok, len(todo))


def fetch(db: sqlite3.Connection, limit: int, domain: str | None) -> None:
    s = _session()
    q = "SELECT l.canon, l.domain, MAX(l.date) d FROM links l LEFT JOIN pages p ON p.canon=l.canon WHERE l.kind='content' AND p.canon IS NULL"
    args: list = []
    if domain:
        q += " AND l.domain=?"; args.append(domain)
    q += " GROUP BY l.canon ORDER BY d DESC LIMIT ?"; args.append(limit)
    todo = db.execute(q, args).fetchall()
    log.info("fetching titles for %d urls", len(todo)); last_hit: dict[str, float] = {}; ok = 0
    for i, (u, host, _) in enumerate(todo):
        wait = 1.0 - (time.time() - last_hit.get(host, 0))
        if wait > 0: time.sleep(wait)
        title = desc = None; status = -1
        try:
            r = s.get(u, timeout=12, stream=True); status = r.status_code
            if "html" in (r.headers.get("content-type") or ""):
                head = r.raw.read(200_000, decode_content=True).decode(r.encoding or "utf-8", "replace")
                m = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']{1,300})', head, re.I) or re.search(r"<title[^>]*>\s*([^<]{1,300})", head, re.I)
                title = m.group(1).strip() if m else None
                m = re.search(r'<meta[^>]+(?:property=["\']og:description["\']|name=["\']description["\'])[^>]+content=["\']([^"\']{1,500})', head, re.I)
                desc = m.group(1).strip() if m else None
            r.close()
        except Exception:
            pass
        last_hit[host] = time.time()
        db.execute("INSERT OR REPLACE INTO pages VALUES (?,?,?,?,?,?)", (u, host, title, desc, status, datetime.now(timezone.utc).isoformat(timespec="seconds")))
        ok += bool(title)
        if i % 20 == 19: db.commit()
    db.commit(); log.info("fetched %d titles of %d", ok, len(todo))


def tme(db: sqlite3.Connection, min_n: int) -> None:
    watch = {r["handle"].lower() for r in csv.DictReader(open(HERE / "channels.csv", encoding="utf-8"))}
    cut = {r["handle"].lower() for r in csv.DictReader(open(HERE / "channels_cut.csv", encoding="utf-8"))} if (HERE / "channels_cut.csv").exists() else set()
    own = {(u or "").lower() for (u,) in db.execute("SELECT username FROM tg.channels")}
    rows = db.execute("SELECT handle, COUNT(*) n, COUNT(DISTINCT channel_id) c, MAX(date) last FROM tme GROUP BY handle HAVING n >= ? ORDER BY c DESC, n DESC", (min_n,)).fetchall()
    print(f"{'handle':32s} {'refs':>6s} {'by':>3s}  last        status")
    for h, n, c, last in rows:
        st = "watched" if h in watch or h in own else ("cut" if h in cut else "")
        if st == "watched": continue
        print(f"{h:32s} {n:6d} {c:3d}  {(last or '')[:10]}  {st}")


def domains(db: sqlite3.Connection, top: int) -> None:
    for d, n, c, k in db.execute("SELECT domain, COUNT(*) n, COUNT(DISTINCT channel_id) c, kind FROM links GROUP BY domain ORDER BY n DESC LIMIT ?", (top,)):
        print(f"{n:8d} {c:4d}ch {k:9s} {d}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["index", "resolve", "fetch", "tme", "domains"])
    ap.add_argument("--limit", type=int, default=2000); ap.add_argument("--domain"); ap.add_argument("--min", type=int, default=5); ap.add_argument("--top", type=int, default=40)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    db = open_db()
    {"index": lambda: index(db), "resolve": lambda: resolve(db, a.limit), "fetch": lambda: fetch(db, a.limit, a.domain), "tme": lambda: tme(db, a.min), "domains": lambda: domains(db, a.top)}[a.cmd]()


if __name__ == "__main__":
    main()
