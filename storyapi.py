"""Read-only queries over vec.db (stories) joined with tg.db (posts), for /api/stories and /api/story."""
import json
import re
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
VEC_DB = HERE / "vec.db"
TG_DB = HERE / "tg.db"
WEEK = re.compile(r"^\d{4}-W\d{2}$")
KEY = re.compile(r"^[a-z_0-9]{1,32}$")
MAX_POSTS = 200


def _open() -> sqlite3.Connection:
    db = sqlite3.connect(f"file:{VEC_DB}?mode=ro", uri=True, timeout=5)
    db.execute("ATTACH DATABASE ? AS tg", (f"file:{TG_DB}?mode=ro",))
    db.row_factory = sqlite3.Row
    return db


def _arenas(a: str | None) -> tuple[str | None, list[str]]:
    l = json.loads(a) if a else []
    return (l[0] if l else None), l[1:]


def weeks() -> dict:
    db = _open()
    rows = db.execute("SELECT week, COUNT(*) n, SUM(size) posts FROM stories WHERE kind='post' AND title IS NOT NULL GROUP BY week ORDER BY week DESC").fetchall()
    return {"weeks": [dict(r) for r in rows]}


def stories(week: str, region: str | None = None, theme: str | None = None) -> dict:
    if not WEEK.match(week) or (region and not KEY.match(region)) or (theme and not KEY.match(theme)):
        raise ValueError("invalid_request")
    db = _open()
    out, regions, themes = [], {}, {}
    for r in db.execute("SELECT id, size, n_channels, title, summary, title_es, summary_es, arenas, prev_story, related_story FROM stories "
                        "WHERE kind='post' AND week=? AND title IS NOT NULL ORDER BY size DESC", (week,)):
        reg, ths = _arenas(r["arenas"])
        regions[reg] = regions.get(reg, 0) + 1
        for t in ths: themes[t] = themes.get(t, 0) + 1
        if region and reg != region: continue
        if theme and theme not in ths: continue
        out.append({"id": r["id"], "size": r["size"], "channels": r["n_channels"], "title": r["title"], "summary": r["summary"], "title_es": r["title_es"], "summary_es": r["summary_es"],
                    "region": reg, "themes": ths, "prev": r["prev_story"], "related": r["related_story"]})
    return {"week": week, "stories": out, "regions": regions, "themes": themes, "total": sum(regions.values())}


def story(sid: int) -> dict | None:
    db = _open()
    r = db.execute("SELECT * FROM stories WHERE id=? AND title IS NOT NULL", (sid,)).fetchone()
    if not r:
        return None
    reg, ths = _arenas(r["arenas"])
    chain, cur, seen = [], r["prev_story"], {sid}
    while cur and cur not in seen and len(chain) < 52:
        seen.add(cur)
        p = db.execute("SELECT id, week, title, title_es, size, prev_story FROM stories WHERE id=?", (cur,)).fetchone()
        if not p: break
        chain.append({"id": p["id"], "week": p["week"], "title": p["title"], "title_es": p["title_es"], "size": p["size"]}); cur = p["prev_story"]
    nxt = [{"id": n["id"], "week": n["week"], "title": n["title"], "title_es": n["title_es"], "size": n["size"]}
           for n in db.execute("SELECT id, week, title, title_es, size FROM stories WHERE prev_story=? AND title IS NOT NULL", (sid,))]
    chans = [dict(c) for c in db.execute(
        "SELECT c.username handle, c.title, COUNT(*) n FROM story_members m JOIN tg.channels c ON c.id=m.channel_id "
        "WHERE m.story_id=? GROUP BY c.id ORDER BY n DESC", (sid,))]
    posts = [{"handle": p["handle"], "title": p["ctitle"], "date": p["date"], "msg_id": p["msg_id"], "views": p["views"], "forwards": p["forwards"],
              "text": (p["text"] or "")[:400], "url": f"https://t.me/{p['handle']}/{p['msg_id']}" if p["handle"] else None}
             for p in db.execute(
                 "SELECT c.username handle, c.title ctitle, x.date, x.msg_id, x.views, x.forwards, x.text FROM story_members m "
                 "JOIN tg.messages x ON x.channel_id=m.channel_id AND x.msg_id=m.msg_id JOIN tg.channels c ON c.id=m.channel_id "
                 "WHERE m.story_id=? ORDER BY x.date LIMIT ?", (sid, MAX_POSTS))]
    return {"id": r["id"], "week": r["week"], "size": r["size"], "channels_n": r["n_channels"], "title": r["title"], "summary": r["summary"],
            "title_es": r["title_es"], "summary_es": r["summary_es"],
            "region": reg, "themes": ths, "prev": r["prev_story"], "related": r["related_story"], "chain": chain, "next": nxt,
            "channels": chans, "posts": posts, "first": posts[0]["date"] if posts else None, "last": posts[-1]["date"] if posts else None}
