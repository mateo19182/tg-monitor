"""Short plain-text report of a weekly stories run, for `hermes send` (Telegram). Titles and counts only, no commentary.

Usage: weekly_report.py --week 2026-W42 --log RUN_LOG --usd0 7.74
"""
import argparse, datetime as dt, re, sqlite3
from stories import week_bounds, ledger_read, HERE, TG_DB

SITE = "https://canales.m19182.dev"
TOP = 10


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", required=True); ap.add_argument("--log", required=True); ap.add_argument("--usd0", type=float, default=None)
    a = ap.parse_args()
    start, end = week_bounds(a.week)
    vec = sqlite3.connect(f"file:{HERE / 'vec.db'}?mode=ro", uri=True)
    tg = sqlite3.connect(f"file:{TG_DB}?mode=ro", uri=True)
    log = open(a.log, encoding="utf-8", errors="replace").read()

    msgs, chans = tg.execute("SELECT count(*), count(DISTINCT channel_id) FROM messages WHERE date>=? AND date<?", (start, end)).fetchone()
    texts = vec.execute("SELECT count(DISTINCT hash) FROM msg_text WHERE kind='post' AND date>=? AND date<?", (start, end)).fetchone()[0]
    st = vec.execute("SELECT id, size, n_channels, title, subject_id FROM stories WHERE kind='post' AND week=? ORDER BY size DESC", (a.week,)).fetchall()
    titled = sum(1 for s in st if s[3])
    in_st = sum(s[1] for s in st)
    last = (dt.date.fromisoformat(end) - dt.timedelta(days=1)).isoformat()
    out = [f"tg-monitor · week {a.week[-2:]} ({start} → {last})", "",
           f"{msgs:,} messages from {chans} channels/groups · {texts:,} distinct post texts",
           f"{len(st)} stories ({titled} titled), {in_st:,} posts in them"]
    subj = dict(vec.execute("SELECT id, title FROM subjects WHERE title IS NOT NULL"))
    if st:
        out += ["", "Largest stories:"]
        for i, (sid, size, nch, title, sj) in enumerate(st[:TOP], 1):
            out.append(f"{i}. {title or '(untitled)'} — {size} posts, {nch} channels" + (f" · subject: {subj[sj]}" if sj in subj else ""))
            out.append(f"   {SITE}/#/s/{sid}")
    m = re.search(r"subjects: (\d+) \((\d+) new", log)
    if m:
        out += ["", f"Subjects: {m.group(1)} in 2026, {m.group(2)} new this run"]
    usd = ledger_read()["usd"]
    out += ["", f"Haiku spend: ${usd - a.usd0:.2f} this run · ${usd:.2f} total" if a.usd0 is not None else f"Haiku spend: ${usd:.2f} total"]
    hf = re.search(r"https://huggingface.co/datasets/\S+ \((\w+)", log)
    out.append(f"HF dataset: uploaded ({hf.group(1)})" if hf else "HF dataset: NOT uploaded — see stories.log")
    problems = [l.strip() for l in log.splitlines() if re.search(r"ERROR|Traceback|Error:", l)]
    if not st:
        problems.insert(0, "no stories were made for this week")
    if titled < len(st):
        problems.append(f"{len(st) - titled} stories left untitled")
    if problems:
        out += ["", "Problems:"] + [f"- {p[:200]}" for p in problems[:8]]
    out += ["", f"Map: {SITE}/"]
    print("\n".join(out)[:4000])


if __name__ == "__main__":
    main()
