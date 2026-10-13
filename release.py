#!/usr/bin/env python3
"""Build the Hugging Face dataset release (Parquet + dataset card) and upload it.

  python release.py build              # -> data/release/ (messages shards, channels, stories, card)
  python release.py upload             # build output -> HF repo (created private + gated if missing)
  python release.py upload --public    # also make the repo public (downloads stay gated)

Needs HF_TOKEN in .env. Sender ids in discussion groups are replaced by HMAC-SHA256(HF_SALT, id), so the same
person keeps the same pseudonym across releases but cannot be looked up by Telegram id; HF_SALT is generated
into .env on first run and must never be published.
"""
import argparse, csv, hashlib, hmac, json, os, secrets, sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "release"
REPO = "mateo-19182/spanish-politics-telegram"
SHARD_ROWS = 500_000
CARD = HERE / "dataset_card.md"


def env() -> dict:
    e = {}
    for line in (HERE / ".env").read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1); e[k.strip()] = v.strip()
    if "HF_SALT" not in e:
        e["HF_SALT"] = secrets.token_hex(32)
        with (HERE / ".env").open("a") as f:
            f.write(f"HF_SALT={e['HF_SALT']}\n")
    return e


def read_csv(p: Path) -> list[dict]:
    with p.open(newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r and not next(iter(r.values())).startswith("#")]


MSG_SCHEMA = pa.schema([
    ("channel_id", pa.int64()), ("msg_id", pa.int64()), ("date", pa.string()), ("text", pa.string()),
    ("sender", pa.string()), ("views", pa.int64()), ("forwards", pa.int64()), ("replies", pa.int64()),
    ("fwd_from_channel_id", pa.int64()), ("fwd_from_msg_id", pa.int64()), ("fwd_from_name", pa.string()), ("fwd_date", pa.string()),
    ("reply_to_msg_id", pa.int64()), ("grouped_id", pa.int64()), ("edit_date", pa.string()), ("fetched_at", pa.string()),
    ("urls", pa.list_(pa.string())), ("media", pa.string()), ("media_id", pa.int64()), ("media_size", pa.int64()),
    ("media_mime", pa.string()), ("media_duration", pa.float64()), ("media_w", pa.int64()), ("media_h", pa.int64()),
])
SRC_COLS = ["channel_id", "msg_id", "date", "text", "sender_id", "views", "forwards", "replies", "fwd_from_channel_id", "fwd_from_msg_id",
            "fwd_from_name", "fwd_date", "reply_to_msg_id", "grouped_id", "edit_date", "fetched_at", "urls", "media", "media_id", "media_size",
            "media_mime", "media_duration", "media_w", "media_h"]


def build() -> dict:
    salt = env()["HF_SALT"].encode()
    pseud = lambda i: None if i is None else hmac.new(salt, str(i).encode(), hashlib.sha256).hexdigest()[:16]
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("**/*.parquet"):
        old.unlink()
    (OUT / "messages").mkdir(exist_ok=True)
    db = sqlite3.connect(f"file:{HERE / 'tg.db'}?mode=ro", uri=True)
    stats = {"built": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "messages": 0}

    # channels: archive metadata + watchlist tier/source (internal notes left out)
    watch = {r["handle"].lower(): r for r in read_csv(HERE / "channels.csv")}
    import importlib.util
    spec = importlib.util.spec_from_file_location("tg_site", HERE / "site.py"); tg_site = importlib.util.module_from_spec(spec); spec.loader.exec_module(tg_site)
    rows = []
    for cid, user, title, about, subs, created, tier in db.execute("SELECT id, username, title, about, participants, created_at, tier FROM channels"):
        w = watch.get((user or "").lower()) or watch.get(str(cid)) or {}
        t = w.get("tier") or tier or ""
        n, lo, hi = db.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM messages WHERE channel_id=?", (cid,)).fetchone()
        if not n:
            continue
        rows.append({"channel_id": cid, "username": user, "title": title, "about": about, "subscribers": subs, "created_at": created,
                     "tier": t, "tier_description": tg_site.TIERS.get(t, {}).get("en"), "group": tg_site.GROUP_OF.get(t[:1]),
                     "archived_from": w.get("since") or None, "list_source": w.get("source") or None,
                     "n_messages": n, "first_message": lo, "last_message": hi})
    pq.write_table(pa.Table.from_pylist(rows), OUT / "channels.parquet", compression="zstd")
    stats["channels"] = len(rows); stats["groups_n"] = sum(r["tier"].startswith("I") for r in rows)

    group_ids = {r["channel_id"] for r in rows if r["tier"].startswith("I")}
    # messages, sharded
    cur = db.execute(f"SELECT {','.join(SRC_COLS)} FROM messages ORDER BY channel_id, msg_id")
    shard, buf = 0, []
    def flush():
        nonlocal shard, buf
        if not buf: return
        cols = {k: [r[k] for r in buf] for k in MSG_SCHEMA.names}
        pq.write_table(pa.table(cols, schema=MSG_SCHEMA), OUT / "messages" / f"messages-{shard:05d}.parquet", compression="zstd", row_group_size=100_000)
        shard += 1; buf = []
    while True:
        batch = cur.fetchmany(50_000)
        if not batch: break
        for r in batch:
            d = dict(zip(SRC_COLS, r))
            sid = d.pop("sender_id")
            d["sender"] = pseud(sid) if d["channel_id"] in group_ids else None  # channel posts: sender is the channel or a signing admin
            try:
                d["urls"] = json.loads(d["urls"] or "[]")
            except json.JSONDecodeError:
                d["urls"] = []
            buf.append(d)
        stats["messages"] += len(batch)
        if len(buf) >= SHARD_ROWS: flush()
    flush(); stats["shards"] = shard

    # forward origins that are not archived channels
    pq.write_table(pa.Table.from_pylist([dict(zip(["channel_id", "username", "title", "subscribers"], r))
                                         for r in db.execute("SELECT channel_id, username, title, participants FROM fwd_sources")]),
                   OUT / "forward_sources.parquet", compression="zstd")

    # stories + labels (only labelled post stories)
    vec = sqlite3.connect(f"file:{HERE / 'vec.db'}?mode=ro", uri=True)
    st = []
    for r in vec.execute("SELECT id, week, size, n_channels, title, summary, title_es, summary_es, arenas, prev_story, prev_sim, related_story, model, labelled_at, subject_id "
                         "FROM stories WHERE kind='post' AND title IS NOT NULL ORDER BY week, id"):
        d = dict(zip(["story_id", "week", "size", "n_channels", "title", "summary", "title_es", "summary_es", "arenas", "prev_story", "prev_similarity",
                      "related_story", "label_model", "labelled_at", "subject_id"], r))
        a = json.loads(d.pop("arenas") or "[]")
        d["region"], d["themes"] = (a[0] if a else None), a[1:]
        st.append(d)
    pq.write_table(pa.Table.from_pylist(st), OUT / "stories.parquet", compression="zstd")
    mem = vec.execute("SELECT m.story_id, m.channel_id, m.msg_id FROM story_members m JOIN stories s ON s.id=m.story_id "
                      "WHERE s.kind='post' AND s.title IS NOT NULL ORDER BY 1, 2, 3").fetchall()
    pq.write_table(pa.table({"story_id": [m[0] for m in mem], "channel_id": [m[1] for m in mem], "msg_id": [m[2] for m in mem]}),
                   OUT / "story_members.parquet", compression="zstd")
    sj = [dict(zip(["subject_id", "title", "title_es", "region", "theme", "n_stories", "n_weeks", "size", "first_week", "last_week", "label_model"], x))
          for x in vec.execute("SELECT id, title, title_es, region, theme, n_stories, n_weeks, size, first_week, last_week, model FROM subjects WHERE title IS NOT NULL ORDER BY id")]
    if sj: pq.write_table(pa.Table.from_pylist(sj), OUT / "subjects.parquet", compression="zstd")
    stats["subjects"] = len(sj)
    stats["stories"] = len(st); stats["weeks"] = f"{st[0]['week']} to {st[-1]['week']}" if st else "none"

    arenas = read_csv(HERE / "arenas.csv")
    pq.write_table(pa.Table.from_pylist(arenas), OUT / "arenas.parquet", compression="zstd")

    lo, hi = db.execute("SELECT MIN(date), MAX(date) FROM messages").fetchone()
    stats["range"] = f"{lo[:10]} to {hi[:10]}"; stats["watchlist"] = len(watch)
    card = CARD.read_text(encoding="utf-8")
    for k, v in stats.items():
        card = card.replace("{" + k + "}", f"{v:,}" if isinstance(v, int) else str(v))
    (OUT / "README.md").write_text(card, encoding="utf-8")
    (OUT / "release.json").write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats, indent=2))
    return stats


def upload(public: bool) -> None:
    from huggingface_hub import HfApi
    api = HfApi(token=env()["HF_TOKEN"])
    api.create_repo(REPO, repo_type="dataset", private=True, exist_ok=True)
    api.update_repo_settings(REPO, repo_type="dataset", gated="auto")
    stamp = json.loads((OUT / "release.json").read_text())["built"]
    api.upload_folder(repo_id=REPO, repo_type="dataset", folder_path=str(OUT), commit_message=f"Release {stamp}",
                      allow_patterns=["README.md", "*.parquet", "messages/*.parquet", "release.json"],
                      delete_patterns=["*.parquet", "messages/*.parquet"])  # drop tables no longer built
    if public:
        api.update_repo_settings(REPO, repo_type="dataset", private=False)
    print(f"https://huggingface.co/datasets/{REPO} ({'public' if public else 'private'}, gated)")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["build", "upload"]); ap.add_argument("--public", action="store_true")
    a = ap.parse_args()
    build() if a.cmd == "build" else upload(a.public)


if __name__ == "__main__":
    main()
