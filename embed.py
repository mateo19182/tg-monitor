"""Embed archived message texts with bge-m3 into vec.db (separate from tg.db).

Each distinct normalised text is embedded once. Messages map to a text hash.
Usage: embed.py [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--limit N] [--batch 64]
"""
import argparse, hashlib, logging, re, sqlite3, sys, time
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
TG_DB = HERE / "tg.db"
VEC_DB = HERE / "vec.db"
MODEL = "BAAI/bge-m3"
MIN_CHARS = 40
log = logging.getLogger("embed")

SCHEMA = """
CREATE TABLE IF NOT EXISTS texts (hash TEXT PRIMARY KEY, text TEXT NOT NULL, n INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS vectors (hash TEXT PRIMARY KEY, vec BLOB NOT NULL);
CREATE TABLE IF NOT EXISTS msg_text (
  channel_id INTEGER, msg_id INTEGER, hash TEXT, date TEXT, kind TEXT,
  PRIMARY KEY (channel_id, msg_id));
CREATE INDEX IF NOT EXISTS idx_msg_text_date ON msg_text(date);
CREATE INDEX IF NOT EXISTS idx_msg_text_hash ON msg_text(hash);
CREATE TABLE IF NOT EXISTS stories (
  id INTEGER PRIMARY KEY, week TEXT, kind TEXT, size INTEGER, n_channels INTEGER,
  centroid BLOB, rep_hashes TEXT, title TEXT, summary TEXT, arenas TEXT, note TEXT,
  prev_story INTEGER, prev_sim REAL, related_story INTEGER, labelled_at TEXT, model TEXT);
CREATE INDEX IF NOT EXISTS idx_stories_week ON stories(week, kind);
CREATE TABLE IF NOT EXISTS story_members (
  story_id INTEGER, channel_id INTEGER, msg_id INTEGER, PRIMARY KEY (story_id, channel_id, msg_id));
CREATE INDEX IF NOT EXISTS idx_story_members_msg ON story_members(channel_id, msg_id);
"""

PLATFORMS = re.compile(r"\b(youtube|instagram|facebook|whatsapp|telegram|twitter|tiktok|bluesky|vk|rutube|𝕏|x)\b", re.I)
FOOTER_START = re.compile(r"^\W*(síguenos|siguenos|suscríbete|suscribete|únete|unete|canal:|chat:|web \||más noticias|mas noticias|follow us|subscribe)", re.I)
URL = re.compile(r"https?://\S+|www\.\S+|t\.me/\S+")
HANDLE_ONLY = re.compile(r"^[\W_]*(@\w+[\W_]*)+$")


def normalise(text: str) -> str:
    """Strip URLs, channel signatures and share-footers; collapse whitespace."""
    keep = []
    for line in text.split("\n"):
        s = URL.sub(" ", line).strip()
        if not s:
            continue
        if HANDLE_ONLY.match(s):
            continue
        if FOOTER_START.match(s) or len(PLATFORMS.findall(s)) >= 2:
            continue
        keep.append(s)
    return re.sub(r"\s+", " ", " ".join(keep)).strip()


def text_hash(t: str) -> str:
    return hashlib.sha1(t.lower().encode("utf-8")).hexdigest()[:20]


def open_vec() -> sqlite3.Connection:
    db = sqlite3.connect(f"file:{VEC_DB}", uri=True, timeout=60)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA synchronous=NORMAL")
    db.executescript(SCHEMA)
    cols = {r[1] for r in db.execute("PRAGMA table_info(stories)")}
    for col, typ in [("prev_sim", "REAL"), ("related_story", "INTEGER")]:
        if col not in cols:
            db.execute(f"ALTER TABLE stories ADD COLUMN {col} {typ}")
    return db


def ingest(vec: sqlite3.Connection, since: str | None, until: str | None, limit: int | None) -> int:
    """Map messages (not yet mapped) to normalised text hashes. Returns number of messages mapped."""
    tg = sqlite3.connect(f"file:{TG_DB}?mode=ro", uri=True, timeout=60)
    tiers = dict(tg.execute("SELECT id, tier FROM channels"))
    vec.execute("ATTACH DATABASE ? AS tg", (f"file:{TG_DB}?mode=ro",))
    q = ("SELECT m.channel_id, m.msg_id, m.date, m.text FROM tg.messages m "
         "LEFT JOIN msg_text x ON x.channel_id=m.channel_id AND x.msg_id=m.msg_id "
         "WHERE x.hash IS NULL AND length(coalesce(m.text,'')) >= ?")
    args: list = [MIN_CHARS]
    if since:
        q += " AND m.date >= ?"; args.append(since)
    if until:
        q += " AND m.date < ?"; args.append(until)
    if limit:
        q += " LIMIT ?"; args.append(limit)
    n = 0; rows_t = []; rows_m = []
    for cid, mid, date, text in vec.execute(q, args):
        t = normalise(text)
        if len(t) < MIN_CHARS:
            h = None
        else:
            h = text_hash(t); rows_t.append((h, t))
        kind = "comment" if (tiers.get(cid) or "").startswith("I_") else "post"
        rows_m.append((cid, mid, h, date, kind)); n += 1
        if len(rows_m) >= 5000:
            flush(vec, rows_t, rows_m); rows_t, rows_m = [], []
    flush(vec, rows_t, rows_m)
    vec.execute("DETACH DATABASE tg")
    return n


def flush(vec, rows_t, rows_m):
    vec.executemany("INSERT INTO texts(hash, text, n) VALUES (?,?,0) ON CONFLICT(hash) DO NOTHING", rows_t)
    vec.executemany("INSERT OR REPLACE INTO msg_text VALUES (?,?,?,?,?)", rows_m)
    vec.executemany("UPDATE texts SET n = n + 1 WHERE hash = ?", [(r[0],) for r in rows_t])
    vec.commit()


def embed_missing(vec: sqlite3.Connection, batch: int) -> int:
    todo = vec.execute("SELECT t.hash, t.text FROM texts t LEFT JOIN vectors v ON v.hash=t.hash WHERE v.hash IS NULL").fetchall()
    if not todo:
        return 0
    import torch
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL, model_kwargs={"torch_dtype": torch.float16})
    model.max_seq_length = 512
    todo.sort(key=lambda r: len(r[1]))  # length-sorted batches waste less padding
    done = 0; t0 = time.time()
    for i in range(0, len(todo), 2048):
        chunk = todo[i:i + 2048]
        embs = model.encode([t for _, t in chunk], batch_size=batch, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False)
        vec.executemany("INSERT OR REPLACE INTO vectors VALUES (?,?)", [(h, embs[j].astype(np.float16).tobytes()) for j, (h, _) in enumerate(chunk)])
        vec.commit(); done += len(chunk)
        log.info("embedded %d/%d (%.0f/s)", done, len(todo), done / (time.time() - t0))
    return done


def load_vectors(vec: sqlite3.Connection, hashes: list[str]) -> np.ndarray:
    out = np.zeros((len(hashes), 1024), np.float32)
    idx = {h: i for i, h in enumerate(hashes)}
    for i in range(0, len(hashes), 900):
        part = hashes[i:i + 900]
        for h, blob in vec.execute(f"SELECT hash, vec FROM vectors WHERE hash IN ({','.join('?' * len(part))})", part):
            out[idx[h]] = np.frombuffer(blob, np.float16).astype(np.float32)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since"); ap.add_argument("--until"); ap.add_argument("--limit", type=int)
    ap.add_argument("--batch", type=int, default=64)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    vec = open_vec()
    n = ingest(vec, a.since, a.until, a.limit)
    log.info("mapped %d messages", n)
    e = embed_missing(vec, a.batch)
    log.info("embedded %d new texts; totals: %s texts, %s messages", e,
             vec.execute("SELECT count(*) FROM vectors").fetchone()[0], vec.execute("SELECT count(*) FROM msg_text").fetchone()[0])


if __name__ == "__main__":
    main()
