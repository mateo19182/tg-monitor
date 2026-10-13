"""Group one week's embedded messages into stories, link them to the previous week, label them.

Usage:
  stories.py --week 2026-W41 [--kind post|comment] [--min-size 12]   # cluster (replaces that week's stories)
  stories.py --week 2026-W41 --label [--cap 10]                       # label unlabelled stories with Haiku
  stories.py --week 2026-W41 --show [--full]                          # list stories (=prev: same story continued, ~prev: related)
  stories.py --week 2026-W41 --map                                    # that week on the fixed 2D layout for the home page -> site/maps/
  stories.py --subjects [--label --cap 30]                            # join the year's stories into narrow subjects, name new ones
  stories.py --fit-layout                                              # fit the year's 2D layout once (data/layout2d.joblib)
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
TRIM_FLOOR, TRIM_STD = 0.60, 1.5        # a member stays only if its cosine to the story centroid >= max(floor, mean - k*std)
BATCH_POLL_S = 20

ARENAS = {r["key"]: r for r in csv.DictReader(open(HERE / "arenas.csv", encoding="utf-8"))}
REGIONS = [k for k, r in ARENAS.items() if r["axis"] == "region"]
THEMES = [k for k, r in ARENAS.items() if r["axis"] == "theme"]
BUCKETS = [k for k, r in ARENAS.items() if r["axis"] == "bucket"]

SYSTEM = """You describe what a group of Telegram posts has in common. The posts were grouped automatically by similarity; they come from several channels and may be in Spanish, Russian, English or other languages.

Return only a JSON object with these fields:
- "title": at most 12 words, in English, naming the concrete story or subject the posts share. Say who did or said what, as the posts present it. No verdicts.
- "summary": one sentence in English. Start with "The posts report", "The posts claim", "The posts comment on" or similar, so that claims stay attributed to the posts.
- "title_es" and "summary_es": the same title and summary in Spanish.
- "region": one region key from the list below: where the story happens or whom it concerns.
- "themes": one or two theme keys from the list below, most fitting first: what the story is about. "election_29n" is only for Spain's own 29 November election; elections elsewhere are "politics".
- "language": ISO code of the dominant language of the posts.
- "new_arena": null, or, when no listed theme fits the subject well, an object {"name": short English name, "definition": one sentence saying what it would cover, "closest": the key of the listed theme that comes nearest}.

Rules: describe, do not evaluate. Write as a neutral archivist would: no characterisations of channels, actors or claims (no labels such as propaganda, disinformation, far-right, pro-Russian, regime), no judgement of truth, no loaded verbs for speech (touts, slams, admits, boasts). Attribute each claim to the source named in the posts (a ministry, agency, spokesperson, outlet); never describe the channels themselves (not "pro-X channels", not "X-language channels"). If some posts deny or contradict the main claim, say so in a clause. If figures differ between posts, give the range. If the posts share a theme but not one event, title it as a roundup: "Posts on X, Y and Z". Titles in sentence case. If the group is mostly channel self-promotion, use the theme "housekeeping"; if it is mostly audience reactions with no shared subject, use "reactions".

Regions:
""" + "\n".join(f"- {k}: {ARENAS[k]['en']} — {ARENAS[k]['definition']}" for k in REGIONS) + """

Themes:
""" + "\n".join(f"- {k}: {ARENAS[k]['en']} — {ARENAS[k]['definition']}" for k in THEMES + BUCKETS)


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
    prev = vec.execute("SELECT id, centroid FROM stories WHERE week=? AND kind=?", (prev_week(week), kind)).fetchall()
    prev_ids = [p[0] for p in prev]
    prev_c = np.stack([np.frombuffer(p[1], np.float32) for p in prev]) if prev else None
    n_noise = int((labels < 0).sum()); made = 0
    old = [r[0] for r in vec.execute("SELECT id FROM stories WHERE week=? AND kind=?", (week, kind))]
    if old:  # replace this week's stories; done after clustering so the write lock is held only briefly
        vec.executemany("DELETE FROM story_members WHERE story_id=?", [(i,) for i in old])
        vec.execute("DELETE FROM stories WHERE week=? AND kind=?", (week, kind))
    trimmed = 0
    for c in sorted(set(labels) - {-1}):
        idx = np.where(labels == c)[0]
        cen = X[idx].mean(0); cen /= np.linalg.norm(cen)
        sims = X[idx] @ cen
        keep = sims >= max(TRIM_FLOOR, float(sims.mean() - TRIM_STD * sims.std()))   # drop peripheral members
        if keep.sum() >= min_size and keep.sum() < len(idx):
            trimmed += int((~keep).sum()); idx = idx[keep]
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
    log.info("%s %s: %d stories, %d/%d texts unassigned (%.0f%%), %d peripheral members trimmed, %d linked to previous week", week, kind, made, n_noise, len(hashes),
             100 * n_noise / len(hashes), trimmed, vec.execute("SELECT count(*) FROM stories WHERE week=? AND kind=? AND prev_story IS NOT NULL", (week, kind)).fetchone()[0])


LAYOUT = HERE / "data" / "layout2d.joblib"   # one 2D projection for the whole year, so a subject keeps its place across weeks
LAYOUT_FROM, LAYOUT_SAMPLE, MAP_SIZE = "2026-W01", 150_000, 1000


def layout_xy(vec, hashes):
    """Fixed 2D coordinates (0..MAP_SIZE) for these texts; computed once with the saved projection and cached in vec.db."""
    vec.execute("CREATE TABLE IF NOT EXISTS xy (hash TEXT PRIMARY KEY, x REAL, y REAL)")
    have = {}
    for i in range(0, len(hashes), 900):
        part = hashes[i:i + 900]
        have.update((h, (x, y)) for h, x, y in vec.execute(f"SELECT hash, x, y FROM xy WHERE hash IN ({','.join('?'*len(part))})", part))
    todo = [h for h in hashes if h not in have]
    if todo:
        import joblib
        m = joblib.load(LAYOUT)
        for i in range(0, len(todo), 50_000):
            part = todo[i:i + 50_000]
            U = (m["umap"].transform(load_vectors(vec, part)) - m["lo"]) / m["span"] * MAP_SIZE
            U = orient(U)
            vec.executemany("INSERT OR REPLACE INTO xy VALUES (?,?,?)", [(h, float(x), float(y)) for h, (x, y) in zip(part, U)])
            vec.commit(); have.update((h, (float(x), float(y))) for h, (x, y) in zip(part, U))
            log.info("layout: placed %d/%d texts", min(i + 50_000, len(todo)), len(todo))
    return have


LAYOUT_ORIENT = HERE / "data" / "layout2d.json"   # rotation that lays the map's long axis horizontally, and the resulting extent


def orient(U):
    o = json.loads(LAYOUT_ORIENT.read_text())
    V = (U - np.array(o["c"])) @ np.array(o["R"]) * o["k"] + np.array(o["off"])
    return np.column_stack([V[:, 0].clip(0, o["w"]), V[:, 1].clip(0, o["h"])])


def map_extent():
    o = json.loads(LAYOUT_ORIENT.read_text()); return o["w"], o["h"]


def fit_orientation(vec):
    """Rotate the cached coordinates so the principal axis is horizontal; scale so the width is MAP_SIZE. Only right after fitting: it expects unrotated coordinates."""
    P = np.array(vec.execute("SELECT x, y FROM xy").fetchall(), dtype=np.float64)
    c = P.mean(0); _, _, Vt = np.linalg.svd(P - c, full_matrices=False); R = Vt.T
    V = (P - c) @ R; lo = np.percentile(V, 0.5, 0); hi = np.percentile(V, 99.5, 0)
    k = MAP_SIZE / (hi[0] - lo[0]); off = -lo * k
    o = {"c": c.tolist(), "R": R.tolist(), "k": float(k), "off": off.tolist(), "w": MAP_SIZE, "h": int(round((hi[1] - lo[1]) * k))}
    rows = vec.execute("SELECT hash, x, y FROM xy").fetchall()
    LAYOUT_ORIENT.write_text(json.dumps(o))
    V = orient(np.array([[r[1], r[2]] for r in rows]))
    vec.executemany("UPDATE xy SET x=?, y=? WHERE hash=?", [(float(x), float(y), r[0]) for (x, y), r in zip(V, rows)]); vec.commit()
    log.info("layout: oriented, %d x %d", o["w"], o["h"])


def fit_layout(vec, kind="post"):
    """Fit the year's 2D projection on a random sample of its texts and save it (replaces cached coordinates)."""
    import umap, joblib
    start, _ = week_bounds(LAYOUT_FROM)
    hashes = sorted({h for (h,) in vec.execute("SELECT DISTINCT hash FROM msg_text WHERE kind=? AND date>=? AND hash IS NOT NULL", (kind, start))})
    rng = np.random.default_rng(0)
    sample = [hashes[i] for i in rng.choice(len(hashes), min(LAYOUT_SAMPLE, len(hashes)), replace=False)]
    log.info("layout: fitting on %d of %d texts", len(sample), len(hashes))
    m = umap.UMAP(n_components=2, n_neighbors=15, min_dist=0.1, metric="cosine", low_memory=True).fit(load_vectors(vec, sample))
    E = m.embedding_; lo = np.percentile(E, 0.5, axis=0); hi = np.percentile(E, 99.5, axis=0)
    LAYOUT.parent.mkdir(exist_ok=True); joblib.dump({"umap": m, "lo": lo, "span": float((hi - lo).max()), "from": LAYOUT_FROM}, LAYOUT)
    vec.execute("DROP TABLE IF EXISTS xy"); vec.commit()
    LAYOUT_ORIENT.write_text(json.dumps({"c": [0, 0], "R": [[1, 0], [0, 1]], "k": 1.0, "off": [0, 0], "w": MAP_SIZE, "h": MAP_SIZE}))
    layout_xy(vec, hashes)
    fit_orientation(vec)


def week_map(vec, week: str, kind: str = "post"):
    """One week's distinct texts on the fixed layout, with their story ids -> site/maps/<week>.json; then refresh site/maps/stories.json."""
    start, end = week_bounds(week)
    hashes = sorted({h for (h,) in vec.execute("SELECT hash FROM msg_text WHERE kind=? AND date>=? AND date<? AND hash IS NOT NULL", (kind, start, end))})
    if not hashes:
        log.warning("no texts for %s", week); return
    story_of = {}
    for sid, h in vec.execute("SELECT m.story_id, t.hash FROM story_members m JOIN stories s ON s.id=m.story_id JOIN msg_text t "
                              "ON t.channel_id=m.channel_id AND t.msg_id=m.msg_id WHERE s.week=? AND s.kind=?", (week, kind)):
        story_of[h] = sid
    xy = layout_xy(vec, hashes)
    stories = vec.execute("SELECT id, title, title_es, size FROM stories WHERE week=? AND kind=? ORDER BY size DESC", (week, kind)).fetchall()
    idx = {s[0]: i for i, s in enumerate(stories)}
    mw, mh = map_extent()
    inside = lambda x, y: 0 < x < mw and 0 < y < mh      # the outermost 0.5% are clipped to the edge by orient(); leave them off the map
    pts = [[round(xy[h][0]), round(xy[h][1]), idx.get(story_of.get(h), -1)] for h in hashes if inside(*xy[h])]
    out = {"week": week, "n": len(hashes), "assigned": sum(p[2] >= 0 for p in pts), "w": mw, "h": mh,
           "stories": [{"id": i, "title": t, "title_es": te, "size": n} for i, t, te, n in stories], "points": pts}
    d = HERE / "site" / "maps"; d.mkdir(parents=True, exist_ok=True)
    tmp = d / f"{week}.json.tmp"
    tmp.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"); tmp.replace(d / f"{week}.json")
    weeks = sorted(p.stem for p in d.glob("????-W??.json"))
    (d / "index.json.tmp").write_text(json.dumps(weeks)); (d / "index.json.tmp").replace(d / "index.json")
    log.info("%s map: %d texts, %d in %d stories", week, out["n"], out["assigned"], len(stories))
    story_dots(vec, kind)


def story_dots(vec, kind="post"):
    """Every story since LAYOUT_FROM as one dot at the median position of its texts -> site/maps/stories.json (month and year views)."""
    pos: dict[int, list] = {}
    for sid, x, y in vec.execute("SELECT m.story_id, xy.x, xy.y FROM stories s JOIN story_members m ON m.story_id=s.id JOIN msg_text t "
                                 "ON t.channel_id=m.channel_id AND t.msg_id=m.msg_id JOIN xy ON xy.hash=t.hash WHERE s.kind=? AND s.week>=?", (kind, LAYOUT_FROM)):
        pos.setdefault(sid, []).append((x, y))
    rows = []
    for sid, week, size, t, te in vec.execute("SELECT id, week, size, title, title_es FROM stories WHERE kind=? AND week>=? ORDER BY week, size DESC", (kind, LAYOUT_FROM)):
        if sid in pos:
            x, y = np.median(np.array(pos[sid]), axis=0)
            rows.append([sid, week, size, round(float(x)), round(float(y)), t, te])
    d = HERE / "site" / "maps"; d.mkdir(parents=True, exist_ok=True)
    (d / "stories.json.tmp").write_text(json.dumps({"w": map_extent()[0], "h": map_extent()[1], "cols": ["id", "week", "size", "x", "y", "title", "title_es"], "stories": rows},
                                                   ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (d / "stories.json.tmp").replace(d / "stories.json")
    log.info("story dots: %d stories", len(rows))


SUBJECT_DIST = 0.12      # stories join a subject when their average centroid cosine is >= 0.88 (between "related" 0.85 and "same story" 0.90)

SUBJECT_SYSTEM = """You name a recurring subject from the titles of weekly story groups. Each group was formed automatically from Telegram posts; the groups below were then joined because their content is similar across weeks.

Return only a JSON object: {"title": at most 8 words in English, "title_es": the same in Spanish}.

Name the specific, narrow subject the titles share: the actors, place and issue (e.g. "Israeli strikes in southern Lebanon", "Spanish housing decrees and evictions"). Not a single week's event, not a broad category. Describe, do not evaluate: no verdicts, no characterisation of channels or actors, no loaded words. Sentence case."""


def subjects(vec, kind="post"):
    """Join this year's weekly stories into narrow subjects (average-linkage clustering of story centroids, >= 2 weeks).
    A subject keeps its id and name while its membership overlaps the previous run's by >= 50%."""
    from sklearn.cluster import AgglomerativeClustering
    rows = vec.execute("SELECT id, week, size, centroid, arenas FROM stories WHERE kind=? AND week>=?", (kind, LAYOUT_FROM)).fetchall()
    if len(rows) < 2:
        return
    C = np.stack([np.frombuffer(r[3], np.float32) for r in rows])
    lab = AgglomerativeClustering(n_clusters=None, metric="precomputed", linkage="average",
                                  distance_threshold=SUBJECT_DIST).fit_predict(1 - np.clip(C @ C.T, -1, 1))
    groups: dict[int, list] = {}
    for r, l in zip(rows, lab):
        groups.setdefault(int(l), []).append(r)
    groups = [g for g in groups.values() if len({r[1] for r in g}) >= 2]
    old = [(sid, set(json.loads(m)), t) for sid, m, t in vec.execute("SELECT id, members, title FROM subjects")]
    used, keep, n_new = set(), {}, 0
    vec.execute("UPDATE stories SET subject_id=NULL WHERE kind=?", (kind,))
    for g in groups:
        ids = {r[0] for r in g}
        match = max(((len(ids & m) / len(ids | m), sid) for sid, m, _ in old if sid not in used), default=(0, None))
        reg, th = Counter(), Counter()
        for r in g:
            a = json.loads(r[4]) if r[4] else []
            if a: reg[a[0]] += r[2]; th.update({t: r[2] for t in a[1:2]})
        weeks = sorted({r[1] for r in g})
        vals = (reg.most_common(1)[0][0] if reg else None, th.most_common(1)[0][0] if th else None, len(g), len(weeks),
                sum(r[2] for r in g), weeks[0], weeks[-1], json.dumps(sorted(ids)))
        if match[0] >= 0.5:
            sid = match[1]; used.add(sid)
            vec.execute("UPDATE subjects SET region=?, theme=?, n_stories=?, n_weeks=?, size=?, first_week=?, last_week=?, members=? WHERE id=?", vals + (sid,))
        else:
            sid = vec.execute("INSERT INTO subjects(region, theme, n_stories, n_weeks, size, first_week, last_week, members) VALUES (?,?,?,?,?,?,?,?)", vals).lastrowid
            n_new += 1
        keep[sid] = ids
        vec.executemany("UPDATE stories SET subject_id=? WHERE id=?", [(sid, i) for i in ids])
    gone = [sid for sid, _, _ in old if sid not in keep]
    vec.executemany("DELETE FROM subjects WHERE id=?", [(s,) for s in gone])
    vec.commit()
    log.info("subjects: %d (%d new, %d kept, %d dropped), %d of %d stories in one", len(keep), n_new, len(keep) - n_new, len(gone),
             sum(len(v) for v in keep.values()), len(rows))


def label_subjects(vec, cap):
    """Name unnamed subjects from their stories' titles, as one batch."""
    from dotenv import load_dotenv
    load_dotenv(HERE / ".env")
    import anthropic, time
    client = anthropic.Anthropic()
    todo = []
    for sid, members in vec.execute("SELECT id, members FROM subjects WHERE title IS NULL"):
        ids = json.loads(members)
        st = vec.execute(f"SELECT week, size, title FROM stories WHERE id IN ({','.join('?'*len(ids))}) AND title IS NOT NULL ORDER BY size DESC", ids).fetchall()
        if len(st) < 2: continue          # name it once its stories are titled
        pick = sorted(st[:16], key=lambda r: r[0])
        todo.append((sid, "Story titles (week: title):\n" + "\n".join(f"{w}: {t}" for w, _, t in pick)))
    spent = ledger_read()["usd"]; est = len(todo) * 0.0007
    log.info("naming %d subjects (spent $%.3f, estimate +$%.2f, cap $%.2f)", len(todo), spent, est, cap)
    if not todo: return
    if spent + est > cap:
        log.error("would exceed the spend cap, not submitting"); return
    system = [{"type": "text", "text": SUBJECT_SYSTEM, "cache_control": {"type": "ephemeral"}}]
    batch = client.messages.batches.create(requests=[{"custom_id": f"j{sid}", "params": {"model": MODEL, "max_tokens": 200, "thinking": {"type": "disabled"},
                                                       "system": system, "messages": [{"role": "user", "content": u}]}} for sid, u in todo])
    log.info("batch %s submitted", batch.id)
    while client.messages.batches.retrieve(batch.id).processing_status != "ended":
        time.sleep(BATCH_POLL_S)
    ok = bad = 0
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    for res in client.messages.batches.results(batch.id):
        sid = int(res.custom_id[1:])
        if res.result.type != "succeeded":
            bad += 1; continue
        ledger_add(res.result.message.usage, batch=True)
        try:
            j = parse_reply(res.result.message)
            vec.execute("UPDATE subjects SET title=?, title_es=?, labelled_at=?, model=? WHERE id=?", (j.get("title"), j.get("title_es"), now, MODEL, sid)); ok += 1
        except (json.JSONDecodeError, AttributeError):
            bad += 1
    vec.commit()
    log.info("subjects: %d named, %d failed, total spend $%.3f", ok, bad, ledger_read()["usd"])


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
    region = j.get("region") if j.get("region") in REGIONS else "?"
    themes = [t for t in (j.get("themes") or []) if t in THEMES + BUCKETS][:2] or ["?"]
    if region in ("latin_america", "united_states", "asia_pacific", "africa", "middle_east", "russia_ukraine") and "election_29n" in themes:
        # the 29-N theme is Spain's election only; elections elsewhere are "politics" (diaspora stories keep it via spain/maghreb/europe/global)
        themes = [t for t in themes if t != "election_29n"] + (["politics"] if "politics" not in themes else [])
        themes = themes[:2] or ["politics"]
    arenas = [region] + themes        # stored as [region, theme, (theme)]
    na = j.get("new_arena")
    if isinstance(na, str): na = {"name": na}
    if na and na.get("name"):
        week = vec.execute("SELECT week FROM stories WHERE id=?", (sid,)).fetchone()[0]
        vec.execute("INSERT OR REPLACE INTO arena_proposals VALUES (?,?,?,?,?)", (sid, week, na["name"], na.get("definition"), na.get("closest")))
    vec.execute("UPDATE stories SET title=?, summary=?, title_es=?, summary_es=?, arenas=?, note=?, labelled_at=?, model=? WHERE id=?",
                (j.get("title"), j.get("summary"), j.get("title_es"), j.get("summary_es"), json.dumps(arenas), json.dumps({"language": j.get("language"), "new_arena": j.get("new_arena")}),
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
        reqs.append({"custom_id": f"s{sid}", "params": {"model": MODEL, "max_tokens": 700, "thinking": {"type": "disabled"}, "system": system,
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
    """Arena names the model proposed, grouped by name, with definitions, weeks and example stories. Promote by adding a row to arenas.csv."""
    groups: dict[str, list] = {}
    for sid, week, name, definition, closest, title in vec.execute(
            "SELECT p.story_id, p.week, p.name, p.definition, p.closest, s.title FROM arena_proposals p JOIN stories s ON s.id=p.story_id"):
        k = re.sub(r"[^a-z ]", "", (name or "").lower()).strip()
        groups.setdefault(k, []).append((week, name, definition, closest, sid, title))
    for k, items in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        weeks = sorted({i[0] for i in items}); closest = Counter(i[3] for i in items if i[3]).most_common(1)
        print(f"\n{len(items):3d}× {items[0][1]}   weeks: {', '.join(weeks)}   closest listed: {closest[0][0] if closest else '-'}")
        defs = [i[2] for i in items if i[2]]
        if defs: print(f"      def: {defs[0][:160]}")
        for i in items[:3]: print(f"      {i[4]}: {(i[5] or '')[:100]}")
    if not groups: print("no proposals")


def show(vec, week, kind, full=False):
    rows = vec.execute("SELECT id, size, n_channels, arenas, title, prev_story, related_story, note, summary FROM stories WHERE week=? AND kind=? ORDER BY size DESC", (week, kind)).fetchall()
    for sid, size, nch, arenas, title, prev, rel, note, summary in rows:
        na = (json.loads(note) or {}).get("new_arena") if note else None
        if isinstance(na, dict): na = na.get("name")
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
    ap.add_argument("--map", action="store_true"); ap.add_argument("--fit-layout", action="store_true")
    ap.add_argument("--subjects", action="store_true")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    vec = open_vec()
    if a.proposals:
        proposals(vec); return
    if a.fit_layout:
        fit_layout(vec, a.kind); return
    if a.subjects:
        subjects(vec, a.kind)
        if a.label: label_subjects(vec, a.cap)
        return
    if not a.week:
        ap.error("--week is required")
    if a.clear_labels:
        vec.execute("UPDATE stories SET title=NULL, summary=NULL, title_es=NULL, summary_es=NULL, arenas=NULL, note=NULL WHERE week=? AND kind=?", (a.week, a.kind)); vec.commit()
    if a.map:
        week_map(vec, a.week, a.kind); return
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
