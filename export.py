#!/usr/bin/env python3
"""Export tg.db to a shareable dataset: data/<handle>.jsonl.gz per channel + data/channels.csv + manifest,
plus data/stories.jsonl.gz and data/arenas.csv when vec.db exists (one line per labelled story with its member message ids).

  python export.py            # writes ./data/
  python export.py --out /path
"""
import argparse
import csv
import gzip
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB = HERE / "tg.db"

MSG_COLS = ["sender_id", "channel_id", "msg_id", "date", "text", "views", "forwards", "replies",
            "fwd_from_channel_id", "fwd_from_msg_id", "fwd_from_name", "fwd_date",
            "reply_to_msg_id", "media", "urls", "grouped_id", "edit_date", "fetched_at",
            "media_id", "media_size", "media_mime", "media_duration", "media_w", "media_h"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "data"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row

    chans = db.execute("SELECT * FROM channels ORDER BY tier, username").fetchall()
    with (out / "channels.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "username", "title", "tier", "participants", "created_at", "about", "n_messages", "first_message", "last_message"])
        for c in chans:
            n, lo, hi = db.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM messages WHERE channel_id=?", (c["id"],)).fetchone()
            w.writerow([c["id"], c["username"], c["title"], c["tier"], c["participants"], c["created_at"], c["about"], n, lo, hi])

    manifest = {"exported_at": datetime.now(timezone.utc).isoformat(), "channels": []}
    for c in chans:
        name = (c["username"] or str(c["id"])).lower()
        path = out / f"{name}.jsonl.gz"
        n = 0
        with gzip.open(path, "wt", encoding="utf-8") as f:
            for r in db.execute(f"SELECT {','.join(MSG_COLS)} FROM messages WHERE channel_id=? ORDER BY msg_id", (c["id"],)):
                d = dict(zip(MSG_COLS, r))
                d["urls"] = json.loads(d["urls"] or "[]")
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
                n += 1
        manifest["channels"].append({"username": c["username"], "file": path.name, "messages": n})
        print(f"{path.name}: {n}")

    with (out / "fwd_sources.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["channel_id", "username", "title", "participants"])
        for r in db.execute("SELECT channel_id, username, title, participants FROM fwd_sources"):
            w.writerow(list(r))
    # stories (if the story layer exists): one line per labelled story, with its member message ids
    vec_db = HERE / "vec.db"
    if vec_db.exists():
        v = sqlite3.connect(f"file:{vec_db}?mode=ro", uri=True)
        v.row_factory = sqlite3.Row
        n = 0
        with gzip.open(out / "stories.jsonl.gz", "wt", encoding="utf-8") as f:
            for r in v.execute("SELECT id, week, kind, size, n_channels, title, summary, title_es, summary_es, arenas, prev_story, related_story, labelled_at, model "
                               "FROM stories WHERE title IS NOT NULL ORDER BY week, id"):
                d = dict(r)
                arenas = json.loads(d.pop("arenas") or "[]")
                d["region"], d["themes"] = (arenas[0] if arenas else None), arenas[1:]
                d["members"] = [[m[0], m[1]] for m in v.execute("SELECT channel_id, msg_id FROM story_members WHERE story_id=? ORDER BY channel_id, msg_id", (r["id"],))]
                f.write(json.dumps(d, ensure_ascii=False) + "\n"); n += 1
        manifest["stories"] = {"file": "stories.jsonl.gz", "count": n, "arenas": "arenas.csv"}
        import shutil; shutil.copy(HERE / "arenas.csv", out / "arenas.csv")
        print(f"stories.jsonl.gz: {n}")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
