"""Group one week's embedded messages into stories, link them to the previous week, label them.

Usage:
  stories.py --week 2026-W41 [--kind post|comment] [--min-size 12]   # cluster (replaces that week's stories)
  stories.py --week 2026-W41 --label [--cap 10]                       # label unlabelled stories with Haiku
  stories.py --week 2026-W41 --show [--full]                          # list stories (=prev: same story continued, ~prev: related)
  stories.py --proposals                                               # arena names the model proposed, for promotion into arenas.csv
"""
import argparse, csv, datetime as dt, json, logging, os, re, sqlite3, sys
from collections import Counter
from pathlib import Path
import numpy as np
from embed import open_vec, load_vectors, HERE, TG_DB

log = logging.getLogger("stories")
LEDGER = HERE / "data" / "label_ledger.json"
MODEL = "claude-haiku-5-5"
PRICE_IN, PRICE_OUT = 1.0, 5.0          # USD per million tokens (Haiku list price), batch = half
N_REPS, REP_CHARS = 8, 400
LINK_SIM, RELATED_SIM = 0.90, 0.85      # same story continued / related story
BATCH_POLL_S = 20

ARENAS = {r["key"]: r for r in csv.DictReader(open(HERE / "arenas.csv", encoding="utf-8"))}

SYSTEM = """You describe what a group of Telegram posts has in common. The posts were grouped automatically by similarity; they come from several channels and may be in Spanish, Russian, English or other languages.

Return only a JSON object with these fields:
- "title": at most 12 words, in English, naming the concrete story or subject the posts share. Say who did or said what, as the posts present it. No verdicts.
- "summary": one sentence in English. Start with "The posts report", "The posts claim", "The posts comment on" or similar, so that claims stay attributed to the posts.
- "arenas": a list of one to three arena keys from the list below, most fitting first.
- "language": ISO code of the dominant language of the posts.
- "new_arena": null, or a short English name for an arena that would fit better than any listed.

Rules: describe, do not evaluate. Never use words such as propaganda, disinformation, fake, hoax, clickbait, conspiracy, far-right, far-left, ultra, pro-Russian, pro-Kremlin, pro-Western, pro-Ukrainian, regime, terrorist, attack (for speech), smear, as your own description; keep them only inside a quotation if the posts use them. Do not state whether anything is true. Name actors as the posts name them. If the group is mostly channel self-promotion, use arena "housekeeping". If it is mostly audience reactions with no shared subject, use "reactions".

Arenas:
""" + "\n".join(f"- {k}: {r['en']} — {r['definition']}" for k, r in ARENAS.items())


def week_bounds(week: str):
    y, w = week.upper().split("-W")
    start = dt.date.fromisocalendar(int(y), int(w), 1)
    return start.isoformat(), (start + dt.timedelta(days=7)).isoformat()


def prev_week(week: str) -> str:
    start, _ = week_bounds(week)
    d = dt.date.fromisoformat(start) - dt.timedelta(days=7)
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def cluster(vec, week: str, kind: str, min_size: int):
    start, end = week_bounds(week)
    rows = vec.execute("SELECT hash, channel_id, msg_id FROM msg_text WHERE kind=? AND date>=? AND date<? AND hash IS NOT NULL",
                       (kind, start, end)).fetchall()
    by_hash: dict[str, list] = {}
    for h, cid, mid in rows:
        by_hash.setdefault(h, []).append((cid, mid))
    hashes = list(by_hash)
    log.info("%s %s: %d messages, %d distinct texts", week, kind, len(rows), len(hashes))
    if len(hashes) < min_size * 2:
        log.warning("too few texts to cluster"); return
    X = load_vectors(vec, hashes)
    import umap
    from sklearn.cluster import HDBSCAN
    U = umap.UMAP(n_components=10, n_neighbors=15, min_dist=0.0, metric="cosine", random_state=0).fit_transform(X)
    labels = HDBSCAN(min_cluster_size=min_size, min_samples=5).fit_predict(U)
    texts = dict(vec.execute(f"SELECT hash, text FROM texts WHERE hash IN ({','.join('?'*len(hashes))})", hashes)) if len(hashes) < 30000 else None
    tiers = dict(sqlite3.connect(f"file:{TG_DB}?mode=ro", uri=True).execute("SELECT id, tier FROM channels"))
    old = [r[0] for r in vec.execute("SELECT id FROM stories WHERE week=? AND kind=?", (week, kind))]
    if old:
        vec.executemany("DELETE FROM story_members WHERE story_id=?", [(i,) for i in old])
        vec.execute("DELETE FROM stories WHERE week=? AND kind=?", (week, kind))
    prev = vec.execute("SELECT id, centroid FROM stories WHERE week=? AND kind=?", (prev_week(week), kind)).fetchall()
    prev_ids = [p[0] for p in prev]
    prev_c = np.stack([np.frombuffer(p[1], np.float32) for p in prev]) if prev else None
    n_noise = int((labels < 0).sum()); made = 0
    for c in sorted(set(labels) - {-1}):
        idx = np.where(labels == c)[0]
        cen = X[idx].mean(0); cen /= np.linalg.norm(cen)
        order = idx[np.argsort(-(X[idx] @ cen))]
        reps = []; seen = set()
        for i in order:
            h = hashes[i]; key = (texts[h] if texts else h)[:60].lower()
            if key in seen: continue
            seen.add(key); reps.append(h)
            if len(reps) == N_REPS: break
        members = [m for i in idx for m in by_hash[hashes[i]]]
        chans = {m[0] for m in members}
        link, related, best = None, None, None
        if prev_c is not None:
            sims = prev_c @ cen; j = int(sims.argmax()); best = float(sims[j])
            if best >= LINK_SIM: link = prev_ids[j]
            elif best >= RELATED_SIM: related = prev_ids[j]
        cur = vec.execute("INSERT INTO stories(week, kind, size, n_channels, centroid, rep_hashes, prev_story, prev_sim, related_story) VALUES (?,?,?,?,?,?,?,?,?)",
                          (week, kind, len(members), len(chans), cen.astype(np.float32).tobytes(), json.dumps(reps), link, best, related))
        vec.executemany("INSERT OR IGNORE INTO story_members VALUES (?,?,?)", [(cur.lastrowid, cid, mid) for cid, mid in members])
        made += 1
    vec.commit()
    log.info("%s %s: %d stories, %d/%d texts unassigned (%.0f%%), %d linked to previous week", week, kind, made, n_noise, len(hashes),
             100 * n_noise / len(hashes), vec.execute("SELECT count(*) FROM stories WHERE week=? AND kind=? AND prev_story IS NOT NULL", (week, kind)).fetchone()[0])


def relink(vec, week, kind):
    prev = vec.execute("SELECT id, centroid FROM stories WHERE week=? AND kind=?", (prev_week(week), kind)).fetchall()
    if not prev:
        log.warning("no stories for %s", prev_week(week)); return
    pid = [p[0] for p in prev]; P = np.stack([np.frombuffer(p[1], np.float32) for p in prev])
    n = 0
    for sid, cen in vec.execute("SELECT id, centroid FROM stories WHERE week=? AND kind=?", (week, kind)).fetchall():
        sims = P @ np.frombuffer(cen, np.float32); j = int(sims.argmax())
        best = float(sims[j]); link = pid[j] if best >= LINK_SIM else None; n += link is not None
        related = pid[j] if RELATED_SIM <= best < LINK_SIM else None
        vec.execute("UPDATE stories SET prev_story=?, prev_sim=?, related_story=? WHERE id=?", (link, best, related, sid))
    vec.commit(); log.info("%s %s: %d stories linked to previous week at >= %.2f", week, kind, n, LINK_SIM)


def ledger_read():
    if LEDGER.exists():
        return json.loads(LEDGER.read_text())
    return {"usd": 0.0, "input_tokens": 0, "output_tokens": 0, "calls": 0}


def ledger_add(usage, batch=True):
    L = ledger_read()
    cw = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cr = getattr(usage, "cache_read_input_tokens", 0) or 0
    cost = (usage.input_tokens * PRICE_IN + cw * PRICE_IN * 1.25 + cr * PRICE_IN * 0.1 + usage.output_tokens * PRICE_OUT) / 1e6
    if batch: cost *= 0.5
    L["input_tokens"] += usage.input_tokens + cw + cr; L["output_tokens"] += usage.output_tokens; L["calls"] += 1
    L["usd"] = L.get("usd", 0.0) + cost
    LEDGER.parent.mkdir(exist_ok=True); LEDGER.write_text(json.dumps(L, indent=1))
    return L


def story_context(vec, sid):
    reps = json.loads(vec.execute("SELECT rep_hashes FROM stories WHERE id=?", (sid,)).fetchone()[0])
    texts = dict(vec.execute(f"SELECT hash, text FROM texts WHERE hash IN ({','.join('?'*len(reps))})", reps))
    tg = sqlite3.connect(f"file:{TG_DB}?mode=ro", uri=True)
    chan = dict(tg.execute("SELECT id, coalesce(username, title) FROM channels"))
    tiers = dict(tg.execute("SELECT id, tier FROM channels"))
    members = vec.execute("SELECT channel_id FROM story_members WHERE story_id=?", (sid,)).fetchall()
    cc = Counter(chan.get(m[0], str(m[0])) for m in members)
    tc = Counter((tiers.get(m[0]) or "?")[:1] for m in members)
    head = (f"Group of {len(members)} posts from {len(cc)} channels. Top channels: "
            + ", ".join(f"{c} ({n})" for c, n in cc.most_common(5)) + ". Tiers: " + ", ".join(f"{t}:{n}" for t, n in tc.most_common()) + ".\n\nRepresentative posts:\n")
    body = "\n".join(f"{i+1}. {texts[h][:REP_CHARS]}" for i, h in enumerate(reps[:N_REPS]) if h in texts)
    return head + body


def parse_reply(msg):
    raw = next((b.text for b in msg.content if getattr(b, "type", "") == "text"), "").strip()
    raw = re.sub(r"^```(?:json)?|```$", "", raw, flags=re.M).strip()
    return json.loads(raw)


def store_label(vec, sid, j):
    arenas = [a for a in j.get("arenas", []) if a in ARENAS] or ["?"]
    vec.execute("UPDATE stories SET title=?, summary=?, arenas=?, note=?, labelled_at=?, model=? WHERE id=?",
                (j.get("title"), j.get("summary"), json.dumps(arenas), json.dumps({"language": j.get("language"), "new_arena": j.get("new_arena")}),
                 dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), MODEL, sid))


def label(vec, week, kind, cap):
    """Label unlabelled stories of a week through the Message Batches API (half price), with the system prompt cached."""
    from dotenv import load_dotenv
    load_dotenv(HERE / ".env")
    import anthropic, time
    client = anthropic.Anthropic()
    todo = [r[0] for r in vec.execute("SELECT id FROM stories WHERE week=? AND kind=? AND title IS NULL ORDER BY size DESC", (week, kind))]
    spent = ledger_read()["usd"]
    est = len(todo) * 0.0015
    log.info("labelling %d stories as a batch (spent $%.3f, estimate +$%.2f, cap $%.2f)", len(todo), spent, est, cap)
    if not todo:
        return
    if spent + est > cap:
        log.error("would exceed the spend cap, not submitting"); return
    system = [{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}]
    reqs = []
    for sid in todo:
        user = story_context(vec, sid)
        if kind == "comment":
            user = user.replace("posts", "discussion-group comments", 1)
        reqs.append({"custom_id": f"s{sid}", "params": {"model": MODEL, "max_tokens": 700, "system": system,
                                                        "messages": [{"role": "user", "content": user}]}})
    batch = client.messages.batches.create(requests=reqs)
    log.info("batch %s submitted", batch.id)
    while True:
        b = client.messages.batches.retrieve(batch.id)
        c = b.request_counts
        if b.processing_status == "ended":
            break
        log.info("batch %s: %d done, %d processing", batch.id, c.succeeded + c.errored + c.expired + c.canceled, c.processing)
        time.sleep(BATCH_POLL_S)
    ok = bad = 0
    for res in client.messages.batches.results(batch.id):
        sid = int(res.custom_id[1:])
        if res.result.type != "succeeded":
            log.warning("story %d: %s", sid, res.result.type); bad += 1; continue
        L = ledger_add(res.result.message.usage, batch=True)
        try:
            store_label(vec, sid, parse_reply(res.result.message)); ok += 1
        except (json.JSONDecodeError, AttributeError) as e:
            log.warning("story %d: unparseable reply (%s)", sid, e); bad += 1
    vec.commit()
    log.info("batch %s: %d labelled, %d failed, total spend $%.3f", batch.id, ok, bad, ledger_read()["usd"])


def proposals(vec):
    """Arena names the model proposed, grouped, so they can be promoted into arenas.csv."""
    c = Counter(); ex = {}
    for sid, title, note in vec.execute("SELECT id, title, note FROM stories WHERE note IS NOT NULL"):
        na = (json.loads(note) or {}).get("new_arena")
        if na:
            k = re.sub(r"[^a-z ]", "", na.lower()).strip(); c[k] += 1; ex.setdefault(k, []).append(f"{sid}: {title}")
    for k, n in c.most_common():
        print(f"{n:3d}  {k}"); [print("       " + e[:90]) for e in ex[k][:3]]
    if not c: print("no proposals")


def show(vec, week, kind, full=False):
    rows = vec.execute("SELECT id, size, n_channels, arenas, title, prev_story, related_story, note, summary FROM stories WHERE week=? AND kind=? ORDER BY size DESC", (week, kind)).fetchall()
    for sid, size, nch, arenas, title, prev, rel, note, summary in rows:
        na = (json.loads(note) or {}).get("new_arena") if note else None
        link = f"={prev}" if prev else (f"~{rel}" if rel else "")
        print(f"{sid:5d} {size:5d} {nch:3d}ch {(','.join(json.loads(arenas)) if arenas else '-'):<28} {link:>6}  {title or '(unlabelled)'}{'  [proposes: '+na+']' if na else ''}")
        if full and summary: print(f"{'':52}{summary}")
    print(f"{len(rows)} stories")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week"); ap.add_argument("--kind", default="post", choices=["post", "comment"])
    ap.add_argument("--min-size", type=int, default=12); ap.add_argument("--label", action="store_true")
    ap.add_argument("--cap", type=float, default=10.0); ap.add_argument("--show", action="store_true")
    ap.add_argument("--relink", action="store_true"); ap.add_argument("--full", action="store_true")
    ap.add_argument("--proposals", action="store_true"); ap.add_argument("--clear-labels", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    vec = open_vec()
    if a.proposals:
        proposals(vec); return
    if not a.week:
        ap.error("--week is required")
    if a.clear_labels:
        vec.execute("UPDATE stories SET title=NULL, summary=NULL, arenas=NULL, note=NULL WHERE week=? AND kind=?", (a.week, a.kind)); vec.commit()
    if not (a.label or a.show or a.relink or a.clear_labels):
        cluster(vec, a.week, a.kind, a.min_size)
    if a.relink:
        relink(vec, a.week, a.kind)
    if a.label:
        label(vec, a.week, a.kind, a.cap)
    if a.show or a.label:
        show(vec, a.week, a.kind, a.full)


if __name__ == "__main__":
    main()
