#!/usr/bin/env python3
"""Quick read-outs from tg.db.

  python report.py daily [--days 90]        # posts per day per channel
  python report.py sources [--days 30]      # most-forwarded origin channels
  python report.py spikes [--days 90]       # days where a channel posted >2x its median
  python report.py grep "voto por correo"   # messages matching a phrase (last 30 days)
"""
import argparse
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent / "tg.db"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["daily", "sources", "spikes", "grep"])
    ap.add_argument("arg", nargs="?")
    ap.add_argument("--days", type=int, default=90)
    a = ap.parse_args()
    db = sqlite3.connect(DB)
    if a.cmd == "daily":
        rows = db.execute(
            "SELECT c.username, substr(m.date,1,10) d, COUNT(*) n, SUM(m.views) v FROM messages m "
            "JOIN channels c ON c.id=m.channel_id WHERE m.date >= date('now', ?) "
            "GROUP BY 1,2 ORDER BY 1,2", (f"-{a.days} days",)).fetchall()
        for u, d, n, v in rows:
            print(f"{u:20s} {d} {n:5d} posts {v or 0:10d} views")
    elif a.cmd == "sources":
        rows = db.execute(
            "SELECT COALESCE('@'||s.username, s.title, m.fwd_from_channel_id) src, COUNT(*) n, "
            "COUNT(DISTINCT m.channel_id) nch FROM messages m LEFT JOIN fwd_sources s ON s.channel_id=m.fwd_from_channel_id "
            "WHERE m.fwd_from_channel_id IS NOT NULL AND m.date >= date('now', ?) "
            "GROUP BY 1 ORDER BY 2 DESC LIMIT 40", (f"-{a.days} days",)).fetchall()
        for src, n, nch in rows:
            print(f"{n:6d} fwds from {src} (into {nch} watched channels)")
    elif a.cmd == "spikes":
        rows = db.execute(
            "WITH d AS (SELECT channel_id, substr(date,1,10) day, COUNT(*) n FROM messages "
            "WHERE date >= date('now', ?) GROUP BY 1,2), "
            "med AS (SELECT channel_id, AVG(n) avg_n FROM d GROUP BY 1) "
            "SELECT c.username, d.day, d.n, ROUND(d.n/med.avg_n,1) ratio FROM d JOIN med USING(channel_id) "
            "JOIN channels c ON c.id=d.channel_id WHERE d.n > 2*med.avg_n ORDER BY ratio DESC LIMIT 40",
            (f"-{a.days} days",)).fetchall()
        for u, day, n, r in rows:
            print(f"{u:20s} {day} {n:5d} posts  x{r} vs avg")
    elif a.cmd == "grep":
        rows = db.execute(
            "SELECT c.username, m.date, m.views, substr(replace(m.text, char(10), ' '),1,160) FROM messages m "
            "JOIN channels c ON c.id=m.channel_id WHERE m.text LIKE ? AND m.date >= date('now','-30 days') "
            "ORDER BY m.date DESC LIMIT 50", (f"%{a.arg}%",)).fetchall()
        for u, d, v, t in rows:
            print(f"{d[:16]} @{u} [{v}] {t}")


if __name__ == "__main__":
    main()
