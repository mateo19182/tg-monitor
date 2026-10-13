#!/usr/bin/env python3
"""Build site/index.html from tg.db + channels.csv. Message search uses /api/search.

  python site.py [--out site]
"""
import argparse
import html
import csv
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
DB = HERE / "tg.db"
DAYS = 120
TOP = 12

TIERS = {
    "A_russian_project_es": {"en": "Spanish-language editions of multilingual Russian channels", "es": "Ediciones en español de canales rusos multilingües"},
    "B_es_aggregator": {"en": "Spanish-language news aggregator channels", "es": "Canales agregadores de noticias en español"},
    "C_spain_node": {"en": "Channels operated from Spain", "es": "Canales gestionados desde España"},
    "D_spain_farright_election": {"en": "Spanish right-wing and nationalist parties, organisations and activists", "es": "Partidos, organizaciones y activistas españoles de derecha y nacionalistas"},
    "E_russian_parent": {"en": "Russian- or English-language channels of which tier A channels are editions (partial archive)", "es": "Canales en ruso o inglés de los que los canales del nivel A son ediciones (archivo parcial)"},
    "F_russian_official": {"en": "Russian state institutions and state media", "es": "Instituciones y medios estatales rusos"},
    "G_allied_state_media_es": {"en": "Spanish-language state media of other countries (partial archive)", "es": "Medios estatales en español de otros países (archivo parcial)"},
    "H_discovered_es_aggregator": {"en": "Channels found through forwards from listed channels", "es": "Canales encontrados a través de reenvíos de canales de la lista"},
    "I_discussion_group": {"en": "Discussion groups linked to tracked channels (from 2025)", "es": "Grupos de debate vinculados a canales seguidos (desde 2025)"},
    "J_spain_parties": {"en": "Parliamentary Spanish parties and their leaders", "es": "Partidos españoles con representación parlamentaria y sus líderes"},
    "K_spain_left": {"en": "Spanish left-wing, anti-NATO and solidarity organisations and media", "es": "Organizaciones y medios españoles de izquierda, contrarios a la OTAN y de solidaridad"},
    "L_spain_media": {"en": "Spanish media outlets and commentators", "es": "Medios de comunicación y comentaristas españoles"},
    "M_public_channels": {"en": "Public channels of individual authors, associations and community publishers", "es": "Canales públicos de autores, asociaciones y comunidades"},
    "N_spain_institution": {"en": "Spanish state institutions", "es": "Instituciones del Estado español"},
    "O_factchecker": {"en": "Fact-checking organisations", "es": "Organizaciones de verificación"},
    "P_regional_politics": {"en": "Regional and nationalist parties, organisations and media (Catalonia, Basque Country, Galicia, others)", "es": "Partidos, organizaciones y medios regionales y nacionalistas (Cataluña, País Vasco, Galicia, otros)"},
    "Q_mobilisation": {"en": "Unions, housing, civic, professional and diaspora organisations", "es": "Sindicatos y organizaciones de vivienda, cívicas, profesionales y de diáspora"},
    "R_conspiracy_pivot": {"en": "Channels that moved from COVID-19 content to the war in Ukraine", "es": "Canales que pasaron de contenido sobre la COVID-19 a la guerra de Ucrania"},
    "S_influencer": {"en": "Individual commentators and streamers", "es": "Comentaristas y streamers individuales"},
    "T_counterpart": {"en": "Ukrainian, EU, Israeli, Moroccan and Algerian official or aligned channels and media", "es": "Canales y medios oficiales o afines de Ucrania, la UE, Israel, Marruecos y Argelia"},
    "U_campaign_2026": {"en": "Candidates, party branches and youth wings around the 29 November 2026 election", "es": "Candidatos, agrupaciones territoriales y juventudes en torno a las elecciones del 29 de noviembre de 2026"},
    "V_civil_society": {"en": "Civil-society organisations: environmental, feminist, consumer, health, education, rights, religious, professional", "es": "Organizaciones de la sociedad civil: ambientales, feministas, de consumidores, sanidad, educación, derechos, religiosas, profesionales"},
    "W_journalist": {"en": "Journalists' and commentators' personal and programme channels", "es": "Canales personales y de programas de periodistas y comentaristas"},
    "X_diaspora": {"en": "Diaspora and migrant-community channels in Spain (Russian, Ukrainian, Arabic, Latin American)", "es": "Canales de comunidades de diáspora e inmigrantes en España (rusa, ucraniana, árabe, latinoamericana)"},
    "Y_local": {"en": "Local news, incident and neighbourhood channels", "es": "Canales locales de noticias, sucesos y vecindario"},
    "Z_meme_finance": {"en": "Political humour, libertarian, crypto and prepper channels", "es": "Canales de humor político, libertarios, cripto y preparacionistas"},
}


GROUPS = {
    "russia": {"en": "Russian state and Russia-based networks", "es": "Estado ruso y redes con base en Rusia", "tiers": ["A", "E", "F"]},
    "relays": {"en": "Spanish-language relays and aggregators", "es": "Canales en español que difunden y agregan", "tiers": ["B", "C", "H", "M", "R"]},
    "politics": {"en": "Spanish parties and political actors", "es": "Partidos y actores políticos españoles", "tiers": ["D", "J", "K", "P", "U"]},
    "media": {"en": "Spanish media, commentators and fact-checkers", "es": "Medios, comentaristas y verificadores españoles", "tiers": ["L", "O", "S", "W"]},
    "states": {"en": "Other governments' media and official channels", "es": "Medios y canales oficiales de otros gobiernos", "tiers": ["G", "T"]},
    "civic": {"en": "Civic, local and diaspora channels", "es": "Canales cívicos, locales y de la diáspora", "tiers": ["N", "Q", "V", "X", "Y", "Z"]},
    "groups": {"en": "Discussion groups", "es": "Grupos de debate", "tiers": ["I"]},
}
GROUP_OF = {t: g for g, v in GROUPS.items() for t in v["tiers"]}


def read_csv(p: Path) -> list[dict]:
    with p.open(newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r and not next(iter(r.values())).startswith("#")]


def domain(u: str) -> str | None:
    try:
        h = urlsplit(u).hostname or ""
    except ValueError:
        return None
    return h.lower().removeprefix("www.") or None


ELECTION_DAY = "2026-11-29"
ELECTION_FROM = "2026-08-01"
ELECTION_TERMS = ["elecciones generales", "29N", "29-N", "29 de noviembre", "voto por correo", "campaña electoral", "Junta Electoral"]


def election(db, chans: dict, tier_of: dict, watch: list) -> dict:
    """29N page: daily posts matching ELECTION_TERMS by group, election_29n stories, party/candidate channels, linked pages."""
    q = " OR ".join('"' + t.replace("-", " ") + '"' for t in ELECTION_TERMS)
    start = date.fromisoformat(ELECTION_FROM); n_days = (date.today() - start).days + 1
    daily = defaultdict(lambda: [0] * n_days); hits = defaultdict(int); recent = set()
    since14 = (date.today() - timedelta(days=13)).isoformat()
    try:
        rows = db.execute("SELECT m.channel_id, m.msg_id, substr(m.date,1,10) FROM message_search s JOIN messages m ON m.rowid = s.rowid "
                          "WHERE message_search MATCH ? AND m.date >= ?", (q, ELECTION_FROM)).fetchall()
    except sqlite3.Error:
        rows = []
    for cid, mid, d in rows:
        i = (date.fromisoformat(d) - start).days
        if 0 <= i < n_days:
            g = GROUP_OF.get((tier_of.get(cid) or "?")[0], "other")
            daily[g][i] += 1; daily[""][i] += 1
        if d >= (date.today() - timedelta(days=29)).isoformat():
            hits[cid] += 1
        if d >= since14:
            recent.add((cid, mid))
    out = {"day": ELECTION_DAY, "start": ELECTION_FROM, "terms": ELECTION_TERMS, "daily": dict(daily), "stories": [], "parties": [], "pages": []}
    if (HERE / "vec.db").exists():
        try:
            vec = sqlite3.connect(f"file:{HERE / 'vec.db'}?mode=ro", uri=True)
            # the label model sometimes tags other countries' elections with election_29n: keep region spain only
            out["stories"] = [{"id": i, "week": w, "title": t, "title_es": te, "size": n, "channels": c} for i, w, t, te, n, c, ar in vec.execute(
                "SELECT id, week, title, title_es, size, n_channels, arenas FROM stories WHERE kind='post' AND title IS NOT NULL AND arenas LIKE '%\"election_29n\"%' "
                "ORDER BY week DESC, size DESC LIMIT 100") if (json.loads(ar) or [None])[0] in ("spain", "maghreb")][:60]
        except sqlite3.Error:
            pass
    # parliamentary parties (J) and campaign channels (U)
    weeks = 8; w0 = date.today() - timedelta(days=7 * weeks - 1)
    wk = defaultdict(lambda: [0] * weeks)
    for cid, d, n in db.execute("SELECT channel_id, substr(date,1,10), COUNT(*) FROM messages WHERE date >= ? GROUP BY 1, 2", (w0.isoformat(),)):
        if (tier_of.get(cid) or "")[:1] in ("J", "U"):
            wk[cid][min(weeks - 1, (date.fromisoformat(d) - w0).days // 7)] += n
    views = dict(db.execute("SELECT channel_id, AVG(views) FROM messages WHERE date >= ? AND fwd_from_channel_id IS NULL GROUP BY 1",
                            ((date.today() - timedelta(days=30)).isoformat(),)))
    by_handle = {(c["username"] or str(c["id"])).lower(): c for c in chans.values()}
    for w in watch:
        if w["tier"][:1] not in ("J", "U"):
            continue
        c = by_handle.get(w["handle"].lower()); cid = c["id"] if c else None
        out["parties"].append({"handle": w["handle"], "title": c["title"] if c else None, "tier": w["tier"][0], "archived": bool(c),
                               "weeks": wk[cid] if cid else None, "views": round(views[cid]) if cid and views.get(cid) is not None else None, "hits": hits.get(cid, 0)})
    out["parties"].sort(key=lambda r: (not r["archived"], -(r["weeks"] or [0])[-1], (r["title"] or r["handle"]).lower()))
    # pages linked from matching posts, last 14 days
    if recent and (HERE / "links.db").exists():
        try:
            ldb = sqlite3.connect(f"file:{HERE / 'links.db'}?mode=ro", uri=True)
            agg = defaultdict(lambda: [0, set(), "", None])
            for cid, mid, canon, dom, title in ldb.execute(
                    "SELECT l.channel_id, l.msg_id, l.canon, l.domain, p.title FROM links l LEFT JOIN pages p ON p.canon = l.canon "
                    "WHERE l.date >= ? AND l.kind = 'content'", (since14,)):
                if (cid, mid) in recent and urlsplit(canon).path not in ("", "/"):  # outlet homepages are mostly post footers
                    a = agg[canon]; a[0] += 1; a[1].add(cid); a[2] = dom; a[3] = title
            out["pages"] = [{"url": u, "n": a[0], "channels": len(a[1]), "domain": a[2], "title": html.unescape(a[3]) if a[3] else None}
                            for u, a in sorted(agg.items(), key=lambda x: (-len(x[1][1]), -x[1][0]))[:25]]
        except sqlite3.Error:
            pass
    return out


def build() -> dict:
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    watch = read_csv(HERE / "channels.csv")
    arenas = {r["key"]: {"axis": r["axis"], "en": r["en"], "es": r["es"]} for r in read_csv(HERE / "arenas.csv")} if (HERE / "arenas.csv").exists() else {}

    chans = {r["id"]: dict(r) for r in db.execute("SELECT * FROM channels")}
    by_handle = {(c["username"] or str(c["id"])).lower(): c for c in chans.values()}
    tier_by_id = {by_handle[w["handle"].lower()]["id"]: w["tier"] for w in watch if w["handle"].lower() in by_handle}
    fwd_names = {r["channel_id"]: dict(r) for r in db.execute("SELECT * FROM fwd_sources")}

    today = date.today()
    start = (today - timedelta(days=DAYS - 1)).isoformat()
    daily = defaultdict(lambda: [0] * DAYS)
    for cid, d, n in db.execute("SELECT channel_id, substr(date,1,10), COUNT(*) FROM messages WHERE date >= ? GROUP BY 1,2", (start,)):
        i = (date.fromisoformat(d) - date.fromisoformat(start)).days
        if 0 <= i < DAYS:
            daily[cid][i] = n

    has_sender = "sender_id" in {r[1] for r in db.execute("PRAGMA table_info(messages)")}
    senders = "COUNT(DISTINCT sender_id)" if has_sender else "0"
    hours = defaultdict(lambda: [[0] * 24 for _ in range(7)])  # [weekday][hour], UTC
    for cid, wd, hr, n in db.execute(
        "SELECT channel_id, CAST(strftime('%w', date) AS INT), CAST(strftime('%H', date) AS INT), COUNT(*) "
        "FROM messages WHERE date >= ? GROUP BY 1,2,3", (start,)):
        hours[cid][(wd + 6) % 7][hr] = n  # Monday first
    stats = {r["channel_id"]: dict(r) for r in db.execute(
        "SELECT channel_id, COUNT(*) n, MIN(date) lo, MAX(date) hi, SUM(views) views, "
        f"SUM(fwd_from_channel_id IS NOT NULL) n_fwd, {senders} senders FROM messages GROUP BY 1")}

    monthly = defaultdict(dict)  # channel -> 'YYYY-MM' -> n, full archive
    for cid, m, n in db.execute("SELECT channel_id, substr(date,1,7), COUNT(*) FROM messages GROUP BY 1,2"):
        monthly[cid][m] = n
    since30 = (today - timedelta(days=30)).isoformat()
    recent = {cid: (round(v) if v is not None else None, n) for cid, v, n in db.execute(
        "SELECT channel_id, AVG(views), COUNT(*) FROM messages WHERE date >= ? AND fwd_from_channel_id IS NULL GROUP BY 1", (since30,))}
    shares = {cid: (med, lnk) for cid, med, lnk in db.execute(
        "SELECT channel_id, SUM(media IS NOT NULL AND media != 'webpage'), SUM(urls IS NOT NULL AND urls NOT IN ('', '[]')) FROM messages GROUP BY 1")}

    def months(cid) -> dict | None:
        mm = monthly.get(cid)
        if not mm:
            return None
        lo = min(mm); y, mo = map(int, lo.split("-")); out = []
        while f"{y:04d}-{mo:02d}" <= max(mm):
            out.append(mm.get(f"{y:04d}-{mo:02d}", 0)); mo += 1
            if mo > 12: y, mo = y + 1, 1
        return {"start": lo, "n": out}

    ch_stories = defaultdict(list); ch_regions = defaultdict(Counter); ch_themes = defaultdict(Counter)
    if (HERE / "vec.db").exists():
        try:
            vec = sqlite3.connect(f"file:{HERE / 'vec.db'}?mode=ro", uri=True)
            for cid, sid, wk, ti, ti_es, ar, n in vec.execute(
                    "SELECT m.channel_id, s.id, s.week, s.title, s.title_es, s.arenas, COUNT(*) FROM story_members m JOIN stories s ON s.id = m.story_id "
                    "WHERE s.kind = 'post' AND s.title IS NOT NULL GROUP BY 1, 2"):
                al = json.loads(ar) if ar else []
                if al: ch_regions[cid][al[0]] += n
                for th in al[1:]: ch_themes[cid][th] += n
                ch_stories[cid].append({"id": sid, "week": wk, "title": ti, "title_es": ti_es, "n": n})
        except sqlite3.Error:
            pass

    fwd_from = defaultdict(Counter)  # channel -> origin -> n
    fwd_to = defaultdict(Counter)    # origin -> watched channel -> n
    for cid, src, n in db.execute("SELECT channel_id, fwd_from_channel_id, COUNT(*) FROM messages WHERE fwd_from_channel_id IS NOT NULL GROUP BY 1,2"):
        fwd_from[cid][src] = n
        fwd_to[src][cid] = n

    domains = defaultdict(Counter)
    for cid, urls in db.execute("SELECT channel_id, urls FROM messages WHERE urls != '[]'"):
        for u in json.loads(urls):
            d = domain(u)
            if d and d != "t.me":
                domains[cid][d] += 1

    def label(cid: int) -> dict:
        c = chans.get(cid)
        if c:
            return {"id": cid, "handle": c["username"], "title": c["title"], "tracked": True}
        f = fwd_names.get(cid)
        return {"id": cid, "handle": f and f["username"], "title": f and f["title"], "tracked": False}

    out = []
    for w in watch:
        h = w["handle"].lower()
        c = by_handle.get(h)
        cid = c["id"] if c else None
        st = stats.get(cid, {}) if cid else {}
        out.append({
            "handle": w["handle"], "tier": w["tier"], "group": GROUP_OF.get(w["tier"][0], "civic"), "since": w.get("since") or None,
            "id": cid, "title": c["title"] if c else None, "about": c["about"] if c else None,
            "subs": c["participants"] if c else None, "created": (c["created_at"] or "")[:10] if c else None,
            "n": st.get("n", 0), "first": (st.get("lo") or "")[:10], "last": (st.get("hi") or "")[:10],
            "views": st.get("views"), "n_fwd": st.get("n_fwd", 0), "senders": st.get("senders", 0),
            "daily": daily.get(cid, [0] * DAYS) if cid else [0] * DAYS,
            "hours": hours.get(cid) if cid else None,
            "fwd_from": [{**label(s), "n": n} for s, n in fwd_from[cid].most_common(TOP)] if cid else [],
            "fwd_to": [{**label(s), "n": n} for s, n in fwd_to[cid].most_common(TOP)] if cid else [],
            "domains": domains[cid].most_common(TOP) if cid else [],
            "months": months(cid) if cid else None,
            "views30": recent.get(cid, (None, 0))[0] if cid else None, "n30": recent.get(cid, (None, 0))[1] if cid else 0,
            "n_media": shares.get(cid, (0, 0))[0] if cid else 0, "n_links": shares.get(cid, (0, 0))[1] if cid else 0,
            "regions": ch_regions[cid].most_common() if cid else [], "themes": ch_themes[cid].most_common(8) if cid else [],
            "stories": sorted(ch_stories[cid], key=lambda x: (x["week"], x["n"]), reverse=True)[:10] if cid else [],
            "n_stories": len(ch_stories[cid]) if cid else 0,
            "linked_note": w.get("note") if w["tier"] == "I_discussion_group" else None,
        })
    total = db.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM messages").fetchone()
    stories = 0
    if (HERE / "vec.db").exists():
        try:
            stories = sqlite3.connect(f"file:{HERE / 'vec.db'}?mode=ro", uri=True).execute("SELECT COUNT(*) FROM stories WHERE kind='post' AND title IS NOT NULL").fetchone()[0]
        except sqlite3.Error:
            stories = 0
    return {
        "stories": stories, "groups": GROUPS,
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "days": DAYS, "start": start, "total": total[0], "range": [(total[1] or "")[:10], (total[2] or "")[:10]],
        "daily": [sum(counts[i] for counts in daily.values()) for i in range(DAYS)],
        "tiers": TIERS, "channels": out, "arenas": arenas,
        "election": election(db, chans, tier_by_id, watch),
    }


HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Spanish Politics on Telegram</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cstyle%3Erect%7Bfill:%231a1a1a%7D@media(prefers-color-scheme:dark)%7Brect%7Bfill:%23e6e6e0%7D%7D%3C/style%3E%3Crect x='1' y='1' width='7' height='7'/%3E%3Crect x='8' y='8' width='7' height='7'/%3E%3C/svg%3E">
<style>
:root{color-scheme:light;--bg:#f7f7f4;--fg:#1a1a1a;--mute:#6b6b66;--line:#d8d8d2;--dot:#cfcfc8;--acc:#1a1a1a;--bar:#1a1a1a}
:root:not([data-theme="light"]){ @media (prefers-color-scheme: dark){ color-scheme:dark;--bg:#0f0f0e;--fg:#e6e6e0;--mute:#8a8a84;--line:#2a2a28;--dot:#2a2a28;--acc:#e6e6e0;--bar:#e6e6e0 } }
:root[data-theme="dark"]{color-scheme:dark;--bg:#0f0f0e;--fg:#e6e6e0;--mute:#8a8a84;--line:#2a2a28;--dot:#2a2a28;--acc:#e6e6e0;--bar:#e6e6e0}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--fg)}
body{font:15px/1.6 ui-monospace,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;min-height:100vh}
a{color:var(--fg);text-decoration:none}a:hover{text-decoration:underline}
.wrap{max-width:1180px;margin:0 auto;padding:16px}
header{display:flex;flex-wrap:wrap;gap:8px 20px;align-items:baseline;border-bottom:1px solid var(--line);padding-bottom:10px;margin-bottom:18px}
header h1{font-size:20px;line-height:1;margin:0;font-weight:400}
header .r{margin-left:auto;display:flex;gap:14px}
.btn{cursor:pointer;color:var(--mute);background:none;border:0;padding:0;font:inherit}.btn:hover{color:var(--fg)}
a:focus-visible,button:focus-visible,input:focus-visible{outline:1px dashed var(--fg);outline-offset:4px}
main{display:block}#view{overflow-wrap:anywhere}.tw{overflow-x:auto}.tw table{min-width:640px}td,th{overflow-wrap:normal}
#top{display:flex;flex-wrap:wrap;gap:4px 30px}#top a{color:var(--mute)}#top a.on{color:var(--fg);text-decoration:underline}
nav{position:sticky;top:12px;align-self:start;max-height:calc(100vh - 24px);overflow:auto;font-size:14px}
nav h3{margin:14px 0 4px;font-size:12px;color:var(--mute);font-weight:400}
nav ul{list-style:none;margin:0;padding:0}nav li{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
nav li a{color:var(--fg)}nav li.cur a{text-decoration:underline}
h2{font-size:15px;margin:0 0 10px;font-weight:700}
.ul{display:none}
.prose,.prose p,p.sum,.story-row .sum,.post .txt,.message-text,.about{font-family:system-ui,-apple-system,"Segoe UI",Roboto,"Helvetica Neue",sans-serif;font-size:16px;line-height:1.55}
.prose{max-width:72ch}.prose p{margin:0 0 12px}
.tabs{display:flex;gap:18px;margin:0 0 14px;border-bottom:1px solid var(--line)}.tabs a{padding:6px 0;color:var(--mute)}.tabs a.on{color:var(--fg);border-bottom:2px solid var(--fg)}
details.legend{margin-top:22px}details.legend summary{cursor:pointer;color:var(--mute)}details.legend table{margin-top:8px}
table{border-collapse:collapse;width:100%;font-size:14px}
th,td{text-align:left;padding:5px 12px 5px 0;vertical-align:top;border-bottom:1px solid var(--line)}
td.nw{white-space:nowrap}table.list{width:auto}table.list td{padding-right:16px}table.list td:nth-child(2){white-space:nowrap}
th{color:var(--mute);font-weight:400;cursor:pointer;white-space:nowrap}
td.num,th.num{text-align:right}
.spark{letter-spacing:-1px;white-space:nowrap;color:var(--bar)}
.spark span{cursor:default}
.mute{color:var(--mute)}
.kv{display:grid;grid-template-columns:max-content 1fr;gap:2px 16px;margin:10px 0 18px}
.kv div:nth-child(odd){color:var(--mute)}
.about{white-space:pre-wrap;border-left:1px solid var(--line);padding-left:12px;margin:8px 0 18px}
.bar{display:inline-block;color:var(--bar);letter-spacing:-1px}

.src{color:var(--mute)}
section{margin-bottom:26px}
.big{font-size:22px;line-height:1.1;margin:0 0 4px}
.search{background:transparent;border:0;border-bottom:1px solid var(--line);color:var(--fg);font:inherit;padding:2px 0;width:100%;outline:none;margin-bottom:8px}
.chart{white-space:pre;line-height:1.15;overflow:auto;color:var(--bar);position:relative}
.chart .lbl{color:var(--mute)}
.tip{position:absolute;pointer-events:none;background:var(--bg);border:1px solid var(--line);padding:2px 6px;font-size:12px;display:none}
body.home main{display:block}
.home-page{margin:20px 0 0}
.home-heading{margin-bottom:18px}.home-heading h2{font-size:clamp(22px,3vw,30px);font-weight:400;line-height:1.2;margin:0 0 6px}.home-heading .mute{font-size:13px}
.home-main{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:32px;align-items:start}
.home-stats{display:grid;grid-template-columns:1fr;gap:10px;padding:0 0 16px;border-bottom:1px dashed var(--line);margin:0 0 18px}
.home-stats div{display:flex;justify-content:space-between;align-items:baseline;gap:12px}.home-stats dt{font-size:12px;color:var(--mute)}.home-stats dd{font-size:20px;margin:0}
.home-page h3{font-size:13px;font-weight:400;color:var(--mute);margin:0 0 10px}
.archive-tree{list-style:none;margin:0;padding:0}.archive-tree li{margin:8px 0}.archive-tree .branch{color:var(--mute);white-space:pre}
.home-page .chart{font-size:11px;line-height:1.15}
.home-footer{border-top:1px dashed var(--line);padding-top:12px;margin-top:18px;font-size:13px;color:var(--mute)}
.message-form{margin:20px 0 24px}.message-query{display:flex;gap:16px;align-items:end}.message-query label{flex:1;min-width:0}
.message-form label{display:block;color:var(--mute);font-size:12px}
.message-form input,.message-form select{display:block;width:100%;min-width:0;background:var(--bg);color:var(--fg);font:inherit;font-size:14px;border:0;border-bottom:1px solid var(--line);border-radius:0;padding:6px 0}
.message-form button{padding:6px 0;white-space:nowrap}.message-form .hint{font-size:12px;margin-top:6px}
.message-filters{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin-top:18px}
.message-result{padding:16px 0;border-bottom:1px solid var(--line)}.message-meta{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12px}
.message-text{white-space:pre-wrap;margin:10px 0;overflow-wrap:anywhere}.message-result .original{font-size:12px}
mark{background:var(--fg);color:var(--bg)}.pagination{display:flex;gap:18px;margin-top:20px;align-items:center;font-size:13px}
.story-row{padding:12px 0;border-bottom:1px solid var(--line)}.story-row .meta{font-size:13px;display:flex;flex-wrap:wrap;gap:4px 12px}
.story-row .meta .tag{color:var(--mute)}.story-row .sum{margin-top:4px}
.filters{display:flex;flex-wrap:wrap;gap:6px 14px;margin:10px 0 16px;font-size:14px}.filters a.on{text-decoration:underline}
.thread{padding:10px 0;border-bottom:1px solid var(--line)}.thread .wk{display:flex;gap:2px;align-items:flex-end;height:22px;margin-top:4px}.thread .wk span{display:block;width:14px;background:var(--bar);min-height:2px}.thread .wk span.gap{background:transparent;border-bottom:1px dotted var(--line)}
#wmap canvas{display:block;width:100%;max-width:100%;touch-action:manipulation;cursor:crosshair}#wmap h3{display:flex;gap:6px;height:2em;align-items:baseline;margin:0}#wmap h3 a{color:inherit}#wmap .hov{color:var(--fg);font-size:13px;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}#wmap .hov.mute{color:var(--mute)}
.prose h3{font-size:16px;margin:22px 0 6px}.prose ul{margin:0 0 12px;padding-left:20px}.prose li{margin-bottom:4px}
.chain{list-style:none;padding:0;margin:0}.chain li{margin:3px 0}
.post{padding:12px 0;border-bottom:1px solid var(--line)}.post .meta{font-size:13px;display:flex;flex-wrap:wrap;gap:4px 12px}.post .txt{white-space:pre-wrap;margin:6px 0;overflow-wrap:anywhere}
@media(max-width:760px){.m-hide{display:none}.wrap{padding:12px}#top{width:100%;order:3;gap:6px 22px}
 .kv{grid-template-columns:1fr;gap:0 0}.kv div:nth-child(odd){margin-top:6px}.big{font-size:18px}
 .home-page{margin-top:12px}.home-main{grid-template-columns:1fr;gap:20px}.home-grid{grid-template-columns:1fr;gap:24px}
 .message-filters{grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.message-query{gap:12px}}
</style>
</head>
<body>
<div class="wrap">
<header>
 <h1><a href="#/" id="brand" aria-label="Spanish Politics on Telegram" title="Spanish Politics on Telegram">▚</a></h1>
 <span id="top"></span>
 <span class="r"><button class="btn" id="lang" type="button">[es]</button><button class="btn" id="theme" type="button">[dark]</button></span>
</header>
<main><div id="view"></div></main>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const T={
 en:{channels:'channels',messages:'messages',archive:'archive',tiers:'tiers',sources:'sources',handle:'handle',title:'title',tier:'tier',subs:'subscribers',posts:'posts',last:'last post',days:'last %d days',search:'search /',
  about:'description (as published by the channel)',stats:'archive',created:'channel created',first:'first archived post',views:'total views',fwd:'posts that are forwards',senders:'distinct senders',
  fwdfrom:'most forwarded from',fwdto:'forwarded by tracked channels',domains:'most linked domains',none:'none',notyet:'not yet archived',perday:'posts per day',tracked:'tracked',untracked:'not tracked',
  tierlist:'tiers',built:'updated',since:'archived from',group:'discussion group',hours:'posts by weekday and hour (UTC)',days7:'Mo Tu We Th Fr Sa Su',
  name:'Spanish Politics on Telegram',home:'home',browse:'browse channels',directory:'index',indexed:'channels in index',activity:'messages per day',period:'archive dates',light:'light',dark:'dark',
  messageSearch:'search messages',query:'text',searchGo:'search',queryHint:'Words or "quoted phrases"',allChannels:'all channels',dateFrom:'from (UTC)',dateTo:'to (UTC)',order:'order',relevance:'relevance',newest:'newest',oldest:'oldest',
  loading:'searching…',results:'results',noresults:'no matching messages.',original:'original post',previous:'previous',next:'next',page:'page',
  stories:'stories',firstPost:'first post',tierOrder:'order of tiers',threads:'story threads',thisWeek:'by week',overTime:'over time',groupLabel:'group',legend:'tiers inside the groups',sections:'sections',aboutPage:'about',
  aboutText:'<p>A public archive of Telegram channels relevant to Spanish politics.</p>',weeks:'weeks',minWeeks:'at least %d weeks',week:'week',region:'region',theme:'theme',all:'all',story:'story',earlier:'earlier weeks',later:'later weeks',related:'related story',nostories:'no stories for this selection.',postsIn:'posts in this story',chans:'channels',showing:'showing',
  invalid_query:'Enter words or balanced "quoted phrases". Maximum 20 terms.',query_too_long:'Search text is limited to 300 characters.',invalid_date:'Enter a valid date.',date_range:'The start date must be on or before the end date.',invalid_sort:'Choose a valid order.',invalid_page:'Choose a valid page.',invalid_channel:'Choose a channel in the index.',invalid_request:'Check the search fields.',search_unavailable:'Search is unavailable. Try again.',search_timeout:'This search took too long. Try more words or a narrower date range.',monthly:'posts per month · full archive',views30:'average views per own post, last 30 days',withMedia:'posts with photo, video or file',withLinks:'posts with links',storiesIn:'appears in %d stories',byRegion:'posts in stories by region',byTheme:'posts in stories by theme',recentStories:'latest stories',links:'links',method:'method',linkKinds:'links by type',content:'web pages',social:'social networks',telegram:'Telegram',shortener:'shortened links',colLinks:'links',kind:'type',sharedUrls:'pages linked by the most channels · last 7 days · all groups',tmeRefs:'Telegram channels outside the list, linked by the most listed channels',w7:'7 days',w30:'30 days',wall:'all',allGroups:'all groups',lastRef:'last',window:'period',noLinks:'link statistics are not available yet.',e29n:'29N',eTitle:'General election · 29 November 2026',daysTo:'%d days to go',eDay:'election day',daysSince:'%d days since the election',ePosts:'posts containing election terms, per day',eTerms:'terms',eByGroup:'by group',last7:'last 7 days',sinceStart:'since %s',eStories:'stories with the theme “29N election”',eParties:'parties and candidates',perWeek:'posts per week, last 8 weeks',avgViews:'avg views, 30 days',eHits:'posts with election terms, 30 days',queued:'queued',ePages:'pages linked from posts with election terms · last 14 days',noneYet:'none yet.'},
 es:{channels:'canales',messages:'mensajes',archive:'archivo',tiers:'niveles',sources:'fuentes',handle:'usuario',title:'título',tier:'nivel',subs:'suscriptores',posts:'publicaciones',last:'última publicación',days:'últimos %d días',search:'buscar /',
  about:'descripción (tal como la publica el canal)',stats:'archivo',created:'canal creado',first:'primera publicación archivada',views:'visualizaciones totales',fwd:'publicaciones que son reenvíos',senders:'remitentes distintos',
  fwdfrom:'más reenviado desde',fwdto:'reenviado por canales seguidos',domains:'dominios más enlazados',none:'ninguno',notyet:'aún no archivado',perday:'publicaciones por día',tracked:'seguido',untracked:'no seguido',
  tierlist:'niveles',built:'actualizado',since:'archivado desde',group:'grupo de debate',hours:'publicaciones por día de la semana y hora (UTC)',days7:'Lu Ma Mi Ju Vi Sá Do',
  name:'Política española en Telegram',home:'inicio',browse:'ver canales',directory:'índice',indexed:'canales en el índice',activity:'mensajes por día',period:'fechas del archivo',light:'claro',dark:'oscuro',
  messageSearch:'buscar mensajes',query:'texto',searchGo:'buscar',queryHint:'Palabras o "frases entre comillas"',allChannels:'todos los canales',dateFrom:'desde (UTC)',dateTo:'hasta (UTC)',order:'orden',relevance:'relevancia',newest:'más recientes',oldest:'más antiguos',
  loading:'buscando…',results:'resultados',noresults:'no hay mensajes coincidentes.',original:'publicación original',previous:'anterior',next:'siguiente',page:'página',
  stories:'historias',firstPost:'primera publicación',tierOrder:'orden de niveles',threads:'hilos de historias',thisWeek:'por semana',overTime:'en el tiempo',groupLabel:'grupo',legend:'niveles dentro de los grupos',sections:'secciones',aboutPage:'acerca de',
  aboutText:'<p>Un archivo público de canales de Telegram relevantes para la política española.</p>',weeks:'semanas',minWeeks:'al menos %d semanas',week:'semana',region:'región',theme:'tema',all:'todas',story:'historia',earlier:'semanas anteriores',later:'semanas posteriores',related:'historia relacionada',nostories:'no hay historias para esta selección.',postsIn:'publicaciones en esta historia',chans:'canales',showing:'mostrando',
  invalid_query:'Introduce palabras o "frases entre comillas" cerradas. Máximo 20 términos.',query_too_long:'El texto de búsqueda está limitado a 300 caracteres.',invalid_date:'Introduce una fecha válida.',date_range:'La fecha inicial debe ser anterior o igual a la final.',invalid_sort:'Elige un orden válido.',invalid_page:'Elige una página válida.',invalid_channel:'Elige un canal del índice.',invalid_request:'Revisa los campos de búsqueda.',search_unavailable:'La búsqueda no está disponible. Inténtalo de nuevo.',search_timeout:'La búsqueda tardó demasiado. Añade palabras o reduce el intervalo de fechas.',monthly:'publicaciones por mes · archivo completo',views30:'visualizaciones medias por publicación propia, últimos 30 días',withMedia:'publicaciones con foto, vídeo o archivo',withLinks:'publicaciones con enlaces',storiesIn:'aparece en %d historias',byRegion:'publicaciones en historias por región',byTheme:'publicaciones en historias por tema',recentStories:'historias más recientes',links:'enlaces',method:'método',linkKinds:'enlaces por tipo',content:'páginas web',social:'redes sociales',telegram:'Telegram',shortener:'enlaces acortados',colLinks:'enlaces',kind:'tipo',sharedUrls:'páginas enlazadas por más canales · últimos 7 días · todos los grupos',tmeRefs:'Canales de Telegram fuera de la lista, enlazados por más canales de la lista',w7:'7 días',w30:'30 días',wall:'todo',allGroups:'todos los grupos',lastRef:'último',window:'periodo',noLinks:'las estadísticas de enlaces aún no están disponibles.',e29n:'29N',eTitle:'Elecciones generales · 29 de noviembre de 2026',daysTo:'faltan %d días',eDay:'día de las elecciones',daysSince:'%d días desde las elecciones',ePosts:'publicaciones con términos electorales, por día',eTerms:'términos',eByGroup:'por grupo',last7:'últimos 7 días',sinceStart:'desde %s',eStories:'historias con el tema «elecciones 29N»',eParties:'partidos y candidatos',perWeek:'publicaciones por semana, últimas 8 semanas',avgViews:'visualizaciones medias, 30 días',eHits:'publicaciones con términos electorales, 30 días',queued:'en cola',ePages:'páginas enlazadas desde publicaciones con términos electorales · últimos 14 días',noneYet:'aún ninguna.'}};
let L=localStorage.getItem('lang')==='es'?'es':'en';
const t=k=>T[L][k]||k;
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const fmt=n=>n==null?'—':Number(n).toLocaleString(L==='es'?'es-ES':'en-GB');
const BL='▁▂▃▄▅▆▇█';const SP=()=>innerWidth<=760?30:60;
function spark(a,n=60){const off=a.length-n;a=a.slice(off);const m=Math.max(1,...a);const s=new Date(D.start);s.setDate(s.getDate()+off);return '<span class="spark">'+a.map((v,i)=>{const d=new Date(s);d.setDate(d.getDate()+i);return `<span title="${d.toISOString().slice(0,10)}: ${v}">${v?BL[Math.min(7,Math.floor(v/m*7.99))]:'·'}</span>`}).join('')+'</span>'}
function bar(n,max,w=24){return '<span class="bar">'+'█'.repeat(Math.max(1,Math.round(n/max*w)))+'</span>'}
function link(c){return c.handle?`<a href="https://t.me/${esc(c.handle)}" target="_blank" rel="noopener">@${esc(c.handle)}</a>`:`<span class="mute">id ${c.id}</span>`}
function chanLink(c){return c.tracked?`<a href="#/c/${esc(c.handle||c.id)}">${esc(c.title||c.handle||c.id)}</a>`:esc(c.title||c.handle||('id '+c.id))}
const G=k=>D.groups[k]?D.groups[k][L]:k;
function nav(cur){document.getElementById('top').innerHTML=[['',t('aboutPage')],['29n',t('e29n')],['channels',t('channels')],['stories',t('stories')],['links',t('links')],['search',t('searchGo')],['method',t('method')]].map(([k,l])=>`<a class="${cur===k?'on':''}" href="#/${k}">${l}</a>`).join('')}
function home(){
 const counts=[[t('channels'),D.channels.length],[t('messages'),D.total],[t('stories'),D.stories]];
 const n=30,daily=D.daily.slice(-n),start=new Date(D.start+'T00:00:00Z');start.setUTCDate(start.getUTCDate()+D.days-n);
 const first=start.toISOString().slice(0,10);
 document.getElementById('view').innerHTML=`<div class="home-page">
  <section class="home-heading"><h2>${t('name')}</h2><div class="mute">${D.range[0]||'—'} → ${D.range[1]||'—'} · ${t('aboutText').replace(/<\/?p>/g,'')}</div></section>
  <div class="home-main"><section id="wmap"></section>
  <aside class="home-side"><dl class="home-stats">${counts.map(([label,n])=>`<div><dt>${label}</dt><dd>${fmt(n)}</dd></div>`).join('')}</dl>
  <section><h3>${t('activity')} · ${t('days').replace('%d',n)}</h3>${chart(daily,first)}</section>
  <footer class="home-footer">${t('built')} ${D.built}</footer></aside></div></div>`;weekMap();
 document.onkeydown=e=>{if(e.key==='/'&&!e.target.closest('input,textarea,select,[contenteditable]')&&!e.ctrlKey&&!e.metaKey&&!e.altKey){e.preventDefault();location.hash='/search'}};
}
let searchController=null;
function searchURL(params,page=1){const p=new URLSearchParams(params);p.delete('page');if(page>1)p.set('page',page);return '#/search'+(p.size?'?'+p.toString():'')}
async function messageSearch(params){
 const options=D.channels.filter(c=>c.id).sort((a,b)=>(a.title||a.handle).localeCompare(b.title||b.handle));
 document.getElementById('view').innerHTML=`<h2>${t('messageSearch')}</h2>
  <form class="message-form" id="message-form"><div class="message-query"><label>${t('query')}<input type="search" name="q" id="message-q" required maxlength="300" value="${esc(params.get('q')||'')}" autocomplete="off"></label><button class="btn" type="submit">[${t('searchGo')}]</button></div><div class="mute hint">${t('queryHint')}</div>
   <div class="message-filters"><label>${t('channels')}<select name="channel"><option value="">${t('allChannels')}</option>${options.map(c=>`<option value="${esc(c.handle.toLowerCase())}">${esc(c.title||c.handle)} · @${esc(c.handle)}</option>`).join('')}</select></label>
    <label>${t('dateFrom')}<input type="date" name="from" value="${esc(params.get('from')||'')}"></label><label>${t('dateTo')}<input type="date" name="to" value="${esc(params.get('to')||'')}"></label>
    <label>${t('order')}<select name="sort">${['relevance','newest','oldest'].map(s=>`<option value="${s}">${t(s)}</option>`).join('')}</select></label></div>
  </form><div id="search-status" class="mute" role="status"></div><div id="search-results"></div>`;
 const form=document.getElementById('message-form'),input=document.getElementById('message-q');
 form.elements.channel.value=(params.get('channel')||'').replace(/^@/,'').toLowerCase();form.elements.sort.value=params.get('sort')||'relevance';
 form.onsubmit=e=>{e.preventDefault();const p=new URLSearchParams();for(const [k,v] of new FormData(form)){if(v&&(k!=='sort'||v!=='relevance'))p.set(k,v)}const url=searchURL(p);if(location.hash===url)route();else location.hash=url};
 document.onkeydown=e=>{if(e.key==='/'&&!e.target.closest('input,textarea,select,[contenteditable]')&&!e.ctrlKey&&!e.metaKey&&!e.altKey){e.preventDefault();input.focus()}};
 if(!params.get('q')){input.focus();return}
 const status=document.getElementById('search-status'),results=document.getElementById('search-results'),controller=new AbortController();searchController=controller;
 status.textContent=t('loading');results.setAttribute('aria-busy','true');
 try{
  const response=await fetch('/api/search?'+params.toString(),{signal:controller.signal});const data=await response.json();if(controller.signal.aborted)return;
  if(!response.ok){status.textContent=t(data.error in T[L]?data.error:'search_unavailable');return}
  status.textContent=data.total?`${fmt(data.total)} ${t('results')} · ${t('page')} ${fmt(data.page)} / ${fmt(Math.ceil(data.total/data.page_size))}`:t('noresults');
  let h=data.results.map(r=>`<article class="message-result"><div class="message-meta"><a href="#/c/${esc(encodeURIComponent(r.handle))}">${esc(r.title||r.handle)} <span class="mute">@${esc(r.handle)}</span></a><time class="mute" datetime="${esc(r.date)}">${esc(new Date(r.date).toISOString().slice(0,16).replace('T',' '))} UTC · #${r.msg_id}</time></div><div class="message-text">${r.snippet.map(p=>p.match?`<mark>${esc(p.text)}</mark>`:esc(p.text)).join('')}</div><a class="original" href="${esc(r.url)}" target="_blank" rel="noopener">[${t('original')}]</a></article>`).join('');
  if(data.page>1||data.has_next){h+='<div class="pagination">';if(data.page>1)h+=`<a href="${esc(searchURL(params,data.page-1))}">[${t('previous')}]</a>`;if(data.has_next)h+=`<a href="${esc(searchURL(params,data.page+1))}">[${t('next')}]</a>`;h+='</div>'}results.innerHTML=h;
 }catch(e){if(e.name!=='AbortError')status.textContent=t('search_unavailable')}
 finally{if(!controller.signal.aborted)results.setAttribute('aria-busy','false')}
}
const A=k=>D.arenas[k]?D.arenas[k][L]:k;const TT=s=>(L==='es'&&s.title_es)||s.title||'';const SM=s=>(L==='es'&&s.summary_es)||s.summary||'';
function storiesURL(p){const q=new URLSearchParams();for(const k of ['week','region','theme'])if(p[k])q.set(k,p[k]);return '#/stories'+(q.size?'?'+q.toString():'')}
async function storiesView(params){
 const view=document.getElementById('view');view.innerHTML=`<h2>${t('stories')}</h2><div class="mute" role="status">${t('loading')}</div>`;
 const controller=new AbortController();searchController=controller;
 try{
  let week=params.get('week');
  const wk=await (await fetch('/api/stories',{signal:controller.signal})).json();if(controller.signal.aborted)return;
  if(!wk.weeks.length){view.innerHTML=`<h2>${t('stories')}</h2><p class="mute">${t('nostories')}</p>`;return}
  if(!week||!wk.weeks.some(w=>w.week===week))week=wk.weeks[0].week;
  const region=params.get('region')||'',theme=params.get('theme')||'';
  const data=await (await fetch('/api/stories?'+new URLSearchParams({week,region,theme}),{signal:controller.signal})).json();if(controller.signal.aborted)return;
  const sel=(k,v)=>storiesURL({week,region:k==='region'?v:region,theme:k==='theme'?v:theme});
  let h=`<h2>${t('stories')}</h2>`+tabs('week');
  h+=`<div class="filters"><span class="mute">${t('week')}</span>${wk.weeks.map(w=>`<a class="${w.week===week?'on':''}" href="${esc(storiesURL({week:w.week,region,theme}))}">${esc(w.week)} <span class="mute">${fmt(w.n)}</span></a>`).join('')}</div>`;
  const keys=axis=>Object.keys(D.arenas).filter(k=>D.arenas[k].axis===axis);
  h+=`<div class="filters"><span class="mute">${t('region')}</span><a class="${region?'':'on'}" href="${esc(sel('region',''))}">${t('all')}</a>${keys('region').filter(k=>data.regions[k]).map(k=>`<a class="${region===k?'on':''}" href="${esc(sel('region',k))}">${esc(A(k))} <span class="mute">${data.regions[k]}</span></a>`).join('')}</div>`;
  h+=`<div class="filters"><span class="mute">${t('theme')}</span><a class="${theme?'':'on'}" href="${esc(sel('theme',''))}">${t('all')}</a>${keys('theme').concat(keys('bucket')).filter(k=>data.themes[k]).map(k=>`<a class="${theme===k?'on':''}" href="${esc(sel('theme',k))}">${esc(A(k))} <span class="mute">${data.themes[k]}</span></a>`).join('')}</div>`;
  h+=`<div class="mute">${t('showing')} ${fmt(data.stories.length)} / ${fmt(data.total)} · ${t('posts')}: ${fmt(data.stories.reduce((n,s)=>n+s.size,0))}</div>`;
  if(!data.stories.length)h+=`<p class="mute">${t('nostories')}</p>`;
  for(const s of data.stories)h+=`<div class="story-row"><div><a href="#/s/${s.id}">${esc(TT(s))}</a>${s.prev?` <span class="mute" title="${t('earlier')}">⟵</span>`:''}</div><div class="meta"><span>${fmt(s.size)} ${t('posts')} · ${fmt(s.channels)} ${t('chans')}</span><span class="tag">${esc(A(s.region))}</span>${s.themes.map(k=>`<span class="tag">${esc(A(k))}</span>`).join('')}</div></div>`;
  view.innerHTML=h;
 }catch(e){if(e.name!=='AbortError')view.innerHTML=`<h2>${t('stories')}</h2><p class="mute">${t('search_unavailable')}</p>`}
}
const tabs=cur=>`<div class="tabs"><a class="${cur==='week'?'on':''}" href="#/stories">${t('thisWeek')}</a><a class="${cur==='time'?'on':''}" href="#/stories?view=time">${t('overTime')}</a></div>`;
async function threadsView(params){
 const view=document.getElementById('view');const min=Math.max(2,parseInt(params.get('min')||'3'));
 view.innerHTML=`<h2>${t('threads')}</h2><div class="mute" role="status">${t('loading')}</div>`;
 const controller=new AbortController();searchController=controller;
 try{
  const d=await (await fetch('/api/threads?min='+min,{signal:controller.signal})).json();if(controller.signal.aborted)return;
  const allWeeks=[...new Set(d.threads.flatMap(x=>x.weeks.map(w=>w.week)))].sort();
  let h=`<h2>${t('stories')}</h2>`+tabs('time')+`<div class="filters"><span class="mute">${t('weeks')}</span>${[2,3,5,8].map(n=>`<a class="${n===min?'on':''}" href="#/stories?view=time&min=${n}">${t('minWeeks').replace('%d',n)}</a>`).join('')}</div>`;
  h+=`<div class="mute">${fmt(d.threads.length)} · ${allWeeks[0]||''} → ${allWeeks[allWeeks.length-1]||''}</div>`;
  if(!d.threads.length)h+=`<p class="mute">${t('nostories')}</p>`;
  for(const x of d.threads){const by={};x.weeks.forEach(w=>by[w.week]=w);const m=Math.max(...x.weeks.map(w=>w.size));const first=allWeeks.indexOf(x.weeks[0].week),last=allWeeks.indexOf(x.weeks[x.weeks.length-1].week);
   h+=`<div class="thread"><div><a href="#/s/${x.id}">${esc(TT(x))}</a></div><div class="meta story-row" style="padding:0;border:0"><div class="meta"><span>${x.n_weeks} ${t('weeks')} · ${fmt(x.total)} ${t('posts')}</span><span class="tag">${esc(A(x.region))}</span>${x.themes.map(k=>`<span class="tag">${esc(A(k))}</span>`).join('')}</div></div>`;
   h+=`<div class="wk" title="${esc(x.weeks.map(w=>w.week+': '+w.size).join(' · '))}">${allWeeks.slice(first,last+1).map(w=>by[w]?`<span style="height:${Math.max(2,Math.round(by[w].size/m*22))}px" title="${w}: ${by[w].size}"></span>`:`<span class="gap"></span>`).join('')}</div></div>`}
  view.innerHTML=h;
 }catch(e){if(e.name!=='AbortError')view.innerHTML=`<h2>${t('threads')}</h2><p class="mute">${t('search_unavailable')}</p>`}
}
async function storyView(id){
 const view=document.getElementById('view');view.innerHTML=`<div class="mute" role="status">${t('loading')}</div>`;
 const controller=new AbortController();searchController=controller;
 try{
  const r=await fetch('/api/story?id='+encodeURIComponent(id),{signal:controller.signal});if(controller.signal.aborted)return;
  if(!r.ok){view.innerHTML=`<p class="mute">${t('nostories')}</p>`;return}
  const s=await r.json();
  let h=`<h2>${esc(TT(s))}</h2>`;
  h+=`<div class="kv"><div>${t('week')}</div><div><a href="${esc(storiesURL({week:s.week}))}">${esc(s.week)}</a></div><div>${t('region')}</div><div><a href="${esc(storiesURL({week:s.week,region:s.region}))}">${esc(A(s.region))}</a></div><div>${t('theme')}</div><div>${s.themes.map(k=>`<a href="${esc(storiesURL({week:s.week,theme:k}))}">${esc(A(k))}</a>`).join(' · ')}</div><div>${t('posts')}</div><div>${fmt(s.size)} · ${fmt(s.channels_n)} ${t('chans')} · ${s.first?esc(s.first.slice(0,10)):''} → ${s.last?esc(s.last.slice(0,10)):''}</div></div>`;
  if(s.first_post)h+=`<div class="kv"><div>${t('firstPost')}</div><div><a href="#/c/${esc(s.first_post.handle||'')}">${esc(s.first_post.title||s.first_post.handle||'')}</a> <span class="mute">${esc(s.first_post.tier)} · ${esc((s.first_post.date||'').slice(0,16).replace('T',' '))} UTC</span></div><div>${t('tierOrder')}</div><div>${s.tier_order.map(x=>`<span title="${esc((x.date||'').slice(0,16).replace('T',' '))} UTC">${esc(x.tier)}</span>`).join(' → ')}</div></div>`;
  if(SM(s))h+=`<p class="sum">${esc(SM(s))}</p>`;
  if(s.chain.length)h+=`<section><h2>${t('earlier')}</h2><ul class="chain">${s.chain.map(c=>`<li><span class="mute">${esc(c.week)}</span> <a href="#/s/${c.id}">${esc(TT(c))}</a> <span class="mute">${fmt(c.size)}</span></li>`).join('')}</ul></section>`;
  if(s.next.length)h+=`<section><h2>${t('later')}</h2><ul class="chain">${s.next.map(c=>`<li><span class="mute">${esc(c.week)}</span> <a href="#/s/${c.id}">${esc(TT(c))}</a> <span class="mute">${fmt(c.size)}</span></li>`).join('')}</ul></section>`;
  const m=s.channels.length?s.channels[0].n:1;
  h+=`<section><h2>${t('chans')}</h2><div class="tw"><table class="list">${s.channels.map(c=>`<tr><td class="num">${fmt(c.n)}</td><td>${bar(c.n,m,innerWidth<=760?12:24)}</td><td>${c.handle?`<a href="#/c/${esc(c.handle)}">${esc(c.title||c.handle)}</a> <span class="mute">@${esc(c.handle)}</span>`:esc(c.title||'')}</td></tr>`).join('')}</table></div></section>`;
  h+=`<section><h2>${t('postsIn')}</h2>${s.posts.length<s.size?`<div class="mute">${t('showing')} ${fmt(s.posts.length)} / ${fmt(s.size)}</div>`:''}`;
  h+=s.posts.map(p=>`<article class="post"><div class="meta">${p.handle?`<a href="#/c/${esc(p.handle)}">${esc(p.title||p.handle)}</a>`:esc(p.title||'')}<time class="mute" datetime="${esc(p.date)}">${esc((p.date||'').slice(0,16).replace('T',' '))} UTC</time>${p.views!=null?`<span class="mute">${fmt(p.views)} ${t('views').replace('total ','').replace('visualizaciones totales','visualizaciones')}</span>`:''}</div><div class="txt">${esc(p.text)}${p.text.length>=400?'…':''}</div>${p.url?`<a class="original" href="${esc(p.url)}" target="_blank" rel="noopener">[${t('original')}]</a>`:''}</article>`).join('');
  h+='</section>';view.innerHTML=h;
 }catch(e){if(e.name!=='AbortError')view.innerHTML=`<p class="mute">${t('search_unavailable')}</p>`}
}
let sortKey='group',sortDir=1;
let groupFilter='';
function index(){const rows=[...D.channels].filter(c=>!groupFilter||c.group===groupFilter).sort((a,b)=>{const x=a[sortKey],y=b[sortKey];return (x==null)-(y==null)||(x>y?1:x<y?-1:0)*sortDir||a.handle.localeCompare(b.handle)});
 const th=(k,l,cls='')=>`<th class="${cls}" data-k="${k}">${l}${sortKey===k?(sortDir>0?' ▴':' ▾'):''}</th>`;
 let h=`<p class="big">${fmt(D.channels.length)} ${t('channels')} · ${fmt(D.total)} ${t('messages')}</p><div class="mute">${t('archive')} ${D.range[0]} → ${D.range[1]} · ${t('built')} ${D.built}</div>`;
 h+=`<div class="filters"><span class="mute">${t('groupLabel')}</span><a class="${groupFilter?'':'on'}" href="#" data-g="">${t('all')}</a>${Object.keys(D.groups).map(k=>`<a class="${groupFilter===k?'on':''}" href="#" data-g="${k}">${esc(G(k))} <span class="mute">${D.channels.filter(c=>c.group===k).length}</span></a>`).join('')}</div>`;
 h+=`<div class="tw"><table><tr>${th('group',t('groupLabel'),'m-hide')}${th('title',t('title'))}${th('subs',t('subs'),'num m-hide')}${th('n',t('posts'),'num')}${th('last',t('last'),'m-hide')}<th>${t('days').replace('%d',SP())}</th></tr>`;
 for(const c of rows)h+=`<tr><td class="mute nw m-hide" title="${esc(D.tiers[c.tier][L])}">${esc(G(c.group))}</td><td class="nw"><a href="#/c/${esc(c.handle)}">${esc(c.title||c.handle)}</a> <span class="mute m-hide">@${esc(c.handle)}</span></td><td class="num m-hide">${fmt(c.subs)}</td><td class="num">${c.n?fmt(c.n):'<span class="mute">—</span>'}</td><td class="nw m-hide">${c.last||'<span class="mute">'+t('notyet')+'</span>'}</td><td>${spark(c.daily,SP())}</td></tr>`;
 h+='</table></div>';
 h+=`<details class="legend"><summary>${t('legend')}</summary><table>${Object.keys(D.groups).map(g=>D.groups[g].tiers.filter(x=>Object.keys(D.tiers).some(k=>k[0]===x)).map(x=>{const k=Object.keys(D.tiers).find(k=>k[0]===x);const n=D.channels.filter(c=>c.tier===k).length;return n?`<tr><td class="mute nw">${esc(G(g))}</td><td class="mute">${x}</td><td class="num">${n}</td><td>${esc(D.tiers[k][L])}</td></tr>`:''}).join('')).join('')}</table></details>`;
 document.getElementById('view').innerHTML=h;
 document.querySelectorAll('.filters a[data-g]').forEach(a=>a.onclick=e=>{e.preventDefault();groupFilter=a.dataset.g;index()});
 document.querySelectorAll('th[data-k]').forEach(e=>e.onclick=()=>{const k=e.dataset.k;if(sortKey===k)sortDir=-sortDir;else{sortKey=k;sortDir=1}index()})}
function chart(a,start=D.start){const H=8,W=a.length,m=Math.max(1,...a);const rows=[];for(let r=H;r>=1;r--){let s=String(Math.round(m*r/H)).padStart(6)+' ┤';for(let i=0;i<W;i++){const v=a[i]/m*H;s+=v>=r?'█':v>=r-.5?'▄':' '}rows.push(s)}
 rows.push('       └'+'─'.repeat(W));const lab=[];for(let i=0;i<W;i+=30){const d=new Date(start+'T00:00:00Z');d.setUTCDate(d.getUTCDate()+i);lab.push(d.toISOString().slice(5,10).padEnd(Math.min(30,W-i)))}rows.push('        '+lab.join(''));return `<div class="chart">${rows.map(r=>esc(r)).join('\n')}</div>`}
function heat(hm){if(!hm)return '';const G=' ·░▒▓█';const m=Math.max(1,...hm.flat());const days=t('days7').split(' ');
 let out='      '+Array.from({length:24},(_,h)=>String(h).padStart(2,'0')).join(' ')+'\n';
 hm.forEach((row,d)=>{out+=days[d].padEnd(5)+' '+row.map(v=>{const g=v?G[Math.min(5,1+Math.floor(v/m*4.99))]:' ';return g+g}).join(' ')+'\n'});
 const tot=hm.flat().reduce((a,b)=>a+b,0);const byH=Array.from({length:24},(_,h)=>hm.reduce((a,r)=>a+r[h],0));
 const peak=byH.indexOf(Math.max(...byH));const wk=hm.slice(0,5).flat().reduce((a,b)=>a+b,0)/5,we=hm.slice(5).flat().reduce((a,b)=>a+b,0)/2;
 return `<div class="chart">${esc(out)}</div><div class="mute">${L==='es'?'hora pico':'peak hour'} ${String(peak).padStart(2,'0')}:00 UTC (${(peak+2)%24}:00 Madrid, ${(peak+3)%24}:00 Moscow) · ${L==='es'?'fin de semana / laborable':'weekend / weekday'} ${(we/Math.max(1,wk)).toFixed(2)}</div>`}
function channel(handle){const c=D.channels.find(x=>x.handle.toLowerCase()===handle.toLowerCase());if(!c){document.getElementById('view').innerHTML='?';return}
 let h=`<h2>${esc(c.title||c.handle)}</h2>`;
 h+=`<div><a href="#/search?channel=${esc(encodeURIComponent(c.handle.toLowerCase()))}">[${t('messageSearch')}]</a></div>`;
 h+=`<div class="kv"><div>${t('handle')}</div><div>${link(c)}</div><div>${t('groupLabel')}</div><div>${esc(G(c.group))}</div><div>${t('tier')}</div><div>${c.tier[0]} · ${esc(D.tiers[c.tier][L])}</div>`;
 if(c.linked_note)h+=`<div>${t('group')}</div><div>${esc(c.linked_note)}</div>`;
 h+=`<div>${t('subs')}</div><div>${fmt(c.subs)}</div><div>${t('created')}</div><div>${c.created||'—'}</div></div>`;
 if(c.about)h+=`<section><h2>${t('about')}</h2><div class="about">${esc(c.about)}</div></section>`;
 h+=`<section><h2>${t('stats')}</h2><div class="kv"><div>${t('posts')}</div><div>${c.n?fmt(c.n):t('notyet')}</div>`;
 if(c.n){h+=`<div>${t('first')}</div><div>${c.first}${c.since?` <span class="mute">(${t('since')} ${c.since})</span>`:''}</div><div>${t('last')}</div><div>${c.last}</div><div>${t('views')}</div><div>${fmt(c.views)}</div><div>${t('fwd')}</div><div>${fmt(c.n_fwd)} (${Math.round(c.n_fwd/c.n*100)}%)</div>`;
  if(c.senders>1)h+=`<div>${t('senders')}</div><div>${fmt(c.senders)}</div>`}
 h+='</div>';
 if(c.n){h+=`<div class="kv"><div>${t('views30')}</div><div>${c.n30?fmt(c.views30):'—'}</div><div>${t('withMedia')}</div><div>${fmt(c.n_media)} (${Math.round(c.n_media/c.n*100)}%)</div><div>${t('withLinks')}</div><div>${fmt(c.n_links)} (${Math.round(c.n_links/c.n*100)}%)</div></div>`;
  if(c.months&&c.months.n.length>1)h+=`<div class="mute">${t('monthly')}</div>`+mchart(c.months)+'<div style="margin-top:10px"></div>'}
 if(c.n)h+=`<div class="mute">${t('perday')} · ${t('days').replace('%d',D.days)}</div>`+chart(c.daily)+`<div class="mute" style="margin-top:10px">${t('hours')} · ${t('days').replace('%d',D.days)}</div>`+heat(c.hours);
 h+='</section>';
 const list=(title,items,f)=>{h+=`<section><h2>${title}</h2>`;if(!items.length){h+=`<p class="mute">${t('none')}</p></section>`;return}const m=items[0].n;h+='<div class="tw"><table class="list">'+items.map(i=>`<tr><td class="num">${fmt(i.n)}</td><td>${bar(i.n,m,innerWidth<=760?12:24)}</td><td>${f(i)}</td></tr>`).join('')+'</table></div></section>'};
 list(t('fwdfrom'),c.fwd_from,i=>`${chanLink(i)} ${i.handle?`<span class="mute">@${esc(i.handle)}</span>`:''}${i.tracked?'':' <span class="mute">·</span>'}`);
 list(t('fwdto'),c.fwd_to,i=>chanLink(i));
 list(t('domains'),c.domains.map(([d,n])=>({d,n})),i=>esc(i.d));
 if(c.n_stories){const A=k=>D.arenas[k]?D.arenas[k][L]:k;h+=`<section><h2>${t('stories')}</h2><p class="mute">${t('storiesIn').replace('%d',fmt(c.n_stories))}</p></section>`;
  list(t('byRegion'),c.regions.map(([k,n])=>({k,n})),i=>`<a href="#/stories?region=${esc(i.k)}">${esc(A(i.k))}</a>`);
  list(t('byTheme'),c.themes.map(([k,n])=>({k,n})),i=>`<a href="#/stories?theme=${esc(i.k)}">${esc(A(i.k))}</a>`);
  h+=`<section><h2>${t('recentStories')}</h2>`+c.stories.map(s=>`<div class="story-row"><div class="meta"><span class="tag">${esc(s.week)}</span><span class="tag">${fmt(s.n)} ${t('posts')}</span></div><a href="#/s/${s.id}">${esc((L==='es'&&s.title_es)||s.title)}</a></div>`).join('')+'</section>'}
 document.getElementById('view').innerHTML=h}
function tiers(){let h=`<h2>${t('tierlist')}</h2><table>`;for(const [k,v] of Object.entries(D.tiers)){const n=D.channels.filter(c=>c.tier===k).length;h+=`<tr><td>${k[0]}</td><td class="num">${n}</td><td>${esc(v[L])}</td></tr>`}h+='</table>';document.getElementById('view').innerHTML=h}
function mchart(m){const a=m.n,H=6,W=a.length,mx=Math.max(1,...a);const rows=[];for(let r=H;r>=1;r--){let s=String(Math.round(mx*r/H)).padStart(6)+' ┤';for(let i=0;i<W;i++){const v=a[i]/mx*H;s+=v>=r?'█':v>=r-.5?'▄':' '}rows.push(s)}
 rows.push('       └'+'─'.repeat(W));let [y,mo]=m.start.split('-').map(Number),lab='';for(let i=0;i<W;i++){if(i===0||mo===1){const txt=String(y);if(lab.length<=i){lab=lab.padEnd(i)+txt}}if(++mo>12){mo=1;y++}}rows.push('        '+lab);return `<div class="chart">${rows.map(r=>esc(r)).join('\n')}</div>`}
let LJ=null;
function linksURL(w,g){const q=new URLSearchParams();if(w!=='30')q.set('w',w);if(g)q.set('g',g);return '#/links'+(q.size?'?'+q.toString():'')}
async function linksView(q){const v=document.getElementById('view');
 if(!LJ){v.innerHTML=`<p class="mute">${t('loading')}</p>`;try{LJ=await fetch('links.json',{cache:'no-cache'}).then(r=>{if(!r.ok)throw 0;return r.json()})}catch(e){v.innerHTML=`<p class="mute">${t('noLinks')}</p>`;return}}
 const w=['7','30','all'].includes(q.get('w'))?q.get('w'):'30',W=LJ.windows[w]||{},g=W[q.get('g')]?q.get('g'):'',cur=W[g]||{kinds:{},domains:[]};
 let h=`<h2>${t('links')}</h2><div class="tabs">${[['7',t('w7')],['30',t('w30')],['all',t('wall')]].map(([k,l])=>`<a class="${k===w?'on':''}" href="${linksURL(k,g)}">${l}</a>`).join('')}</div>`;
 h+=`<div class="filters"><a class="${g?'':'on'}" href="${linksURL(w,'')}">${t('allGroups')}</a>${Object.keys(D.groups).filter(k=>W[k]).map(k=>`<a class="${k===g?'on':''}" href="${linksURL(w,k)}">${esc(G(k))}</a>`).join('')}</div>`;
 const kinds=Object.entries(cur.kinds).sort((a,b)=>b[1]-a[1]),tot=kinds.reduce((a,[,n])=>a+n,0),km=kinds.length?kinds[0][1]:1,bw=innerWidth<=760?12:24;
 h+=`<section><h2>${t('linkKinds')}</h2><table class="list">${kinds.map(([k,n])=>`<tr><td class="num">${fmt(n)}</td><td class="num mute">${Math.round(n/tot*100)}%</td><td>${bar(n,km,innerWidth<=760?8:24)}</td><td>${esc(t(k))}</td></tr>`).join('')}</table></section>`;
 const dm=cur.domains.length?cur.domains[0][2]:1;
 h+=`<section><h2>${t('domains')}</h2><div class="tw"><table><tr><th class="num">${t('colLinks')}</th><th></th><th>domain</th><th>${t('kind')}</th><th class="num">${t('chans')}</th></tr>${cur.domains.map(([d,k,n,c])=>`<tr><td class="num">${fmt(n)}</td><td>${bar(n,dm,bw)}</td><td>${esc(d)}</td><td class="mute">${esc(t(k))}</td><td class="num">${fmt(c)}</td></tr>`).join('')}</table></div></section>`;
 h+=`<section><h2>${t('sharedUrls')}</h2>${LJ.urls.map(u=>`<div class="story-row"><div class="meta"><span class="tag">${fmt(u.channels)} ${t('chans')}</span><span class="tag">${fmt(u.n)} ${t('posts')}</span><span class="tag">${esc(u.domain)}</span></div><a href="${esc(u.url)}" target="_blank" rel="noopener nofollow">${esc(u.title||u.url)}</a></div>`).join('')}</section>`;
 const tw=w==='all'?'all':'30',tm=LJ.tme[tw]||[];
 h+=`<section><h2>${t('tmeRefs')} · ${t(tw==='all'?'wall':'w30')}</h2><div class="tw"><table><tr><th></th><th class="num">${t('chans')}</th><th class="num">${t('colLinks')}</th><th>${t('lastRef')}</th></tr>${tm.map(([hd,n,c,last])=>`<tr><td><a href="https://t.me/${esc(hd)}" target="_blank" rel="noopener">@${esc(hd)}</a></td><td class="num">${fmt(c)}</td><td class="num">${fmt(n)}</td><td class="mute">${esc(last)}</td></tr>`).join('')}</table></div></section>`;
 h+=`<footer class="home-footer">${t('built')} ${esc(LJ.built)}</footer>`;v.innerHTML=h}
const METHOD={
 en:c=>`<h2>Method</h2>
<h3>Collection</h3><ul>
<li>Telegram API (MTProto), one user account, every hour.</li>
<li>${c.n} channels and discussion groups on a hand-maintained list, ${c.a} archived so far; ${c.g} groups, tiers by type of channel.</li>
<li>Per post: text, date, edit date, views, forwards, replies, forward origin, reply id, album id, links, media type, Telegram media id, size, MIME type, duration, dimensions. No media files.</li>
<li>Views, forwards and text re-read for 7 days after posting. Deleted posts are kept. Some large channels are archived from a start date. Times in UTC.</li></ul>
<h3>Stories</h3><ul>
<li>Input: posts ≥ 40 characters, discussion groups excluded. URLs, handle-only lines and subscription footers removed; identical texts merged.</li>
<li>Embeddings: BAAI/bge-m3 (multilingual, 1024 dimensions).</li>
<li>Per ISO week: UMAP (10 dimensions, cosine, 15 neighbours) → HDBSCAN (min. cluster 12, min. samples 5). Members with cosine to the centroid below max(0.60, mean − 1.5 sd) dropped. About a third of posts end up unassigned (W38–W41: 33–34%).</li>
<li>Week to week: centroid cosine ≥ 0.90 = same story; 0.85–0.90 = related.</li>
<li>Labels: Claude Haiku 5.5 on the 8 posts nearest the centroid (≤ 400 characters each) → title and summary (EN, ES), 1 region of 10, 1–2 themes of 15. Not reviewed one by one.</li>
<li>Home page map: the latest labelled week, the same embeddings projected to 2 dimensions with UMAP (cosine, 15 neighbours, min. distance 0.1) for display only. Stories are found in the 10-dimensional projection, so some dots sit away from the rest of their story. Titles are drawn for the largest stories that fit.</li></ul>
<h3>Links</h3><ul>
<li>URLs from post text and link previews; canonical form: https, no www/m/amp, no tracking parameters, fragments or trailing slash.</li>
<li>Types: web page, social network, Telegram, shortener. Shorteners followed to the destination; page titles fetched for a subset (1 request/s per domain). Counts include forwards.</li></ul>
<h3>Limits</h3><ul>
<li>Only listed channels; start dates differ between channels.</li>
<li>View counts as reported by Telegram.</li>
<li>No reactions or Telegram stories; comments only from listed discussion groups.</li></ul>`,
 es:c=>`<h2>Método</h2>
<h3>Recogida</h3><ul>
<li>API de Telegram (MTProto), una cuenta de usuario, cada hora.</li>
<li>${c.n} canales y grupos de debate en una lista mantenida a mano, ${c.a} archivados hasta ahora; ${c.g} grupos, niveles según el tipo de canal.</li>
<li>Por publicación: texto, fecha, fecha de edición, visualizaciones, reenvíos, respuestas, origen del reenvío, id de respuesta, id de álbum, enlaces, tipo de archivo, id de archivo de Telegram, tamaño, tipo MIME, duración, dimensiones. Sin archivos multimedia.</li>
<li>Visualizaciones, reenvíos y texto se releen durante 7 días tras la publicación. Las publicaciones borradas se conservan. Algunos canales grandes se archivan desde una fecha. Horas en UTC.</li></ul>
<h3>Historias</h3><ul>
<li>Entrada: publicaciones de ≥ 40 caracteres, sin grupos de debate. Se quitan URL, líneas solo con usuarios y pies de suscripción; los textos idénticos se agrupan.</li>
<li>Vectores: BAAI/bge-m3 (multilingüe, 1024 dimensiones).</li>
<li>Por semana ISO: UMAP (10 dimensiones, coseno, 15 vecinos) → HDBSCAN (grupo mín. 12, muestras mín. 5). Se descartan miembros con coseno al centroide inferior a max(0,60, media − 1,5 de). Alrededor de un tercio de las publicaciones queda sin asignar (S38–S41: 33–34 %).</li>
<li>Entre semanas: coseno de centroides ≥ 0,90 = misma historia; 0,85–0,90 = relacionada.</li>
<li>Etiquetas: Claude Haiku 5.5 sobre las 8 publicaciones más cercanas al centroide (≤ 400 caracteres cada una) → título y resumen (EN, ES), 1 región de 10, 1–2 temas de 15. Sin revisión una a una.</li>
<li>Mapa de la portada: la última semana etiquetada, los mismos vectores proyectados a 2 dimensiones con UMAP (coseno, 15 vecinos, distancia mín. 0,1) solo para mostrarlos. Las historias se forman en la proyección de 10 dimensiones, así que algunos puntos quedan lejos del resto de su historia. Se rotulan las historias más grandes que caben.</li></ul>
<h3>Enlaces</h3><ul>
<li>URL del texto y de las vistas previas; forma canónica: https, sin www/m/amp, sin parámetros de seguimiento, fragmentos ni barra final.</li>
<li>Tipos: página web, red social, Telegram, acortador. Los acortadores se siguen hasta el destino; títulos de página para una parte (1 petición/s por dominio). Los recuentos incluyen reenvíos.</li></ul>
<h3>Límites</h3><ul>
<li>Solo canales de la lista; las fechas de inicio varían entre canales.</li>
<li>Visualizaciones según Telegram.</li>
<li>Sin reacciones ni historias de Telegram; comentarios solo de los grupos de debate de la lista.</li></ul>`};
function methodView(){document.getElementById('view').innerHTML=`<div class="prose">${METHOD[L]({n:fmt(D.channels.length),a:fmt(D.channels.filter(c=>c.n).length),g:Object.keys(D.groups).length})}</div>`;weekMap()}
let MJ=null,redrawMap=null;addEventListener('resize',()=>redrawMap&&redrawMap());
const MAPT={en:{head:'week %w',hov:'Point at a dot to see its story.',none:'unassigned'},
 es:{head:'semana %w',hov:'Señala un punto para ver su historia.',none:'sin asignar'}};
async function weekMap(){const box=document.getElementById('wmap');if(!box)return;
 if(!MJ){try{MJ=await fetch('map.json',{cache:'no-cache'}).then(r=>{if(!r.ok)throw 0;return r.json()})}catch(e){return}}
 if(!document.body.contains(box))return;const M=MJ,T=MAPT[L],P=M.points;
 box.innerHTML=`<h3><span style="white-space:nowrap"><a href="#/stories">${t('stories')}</a> · ${T.head.replace('%w',esc(M.week.replace(/^\d+-W/,'')))} ·</span><span class="hov mute">${T.hov}</span></h3><canvas></canvas>`;
 const cv=box.querySelector('canvas'),hv=box.querySelector('.hov'),pad=8;let cur=-2,sc=1,ox=0,W=0,H=0,slack=0;
 const cen=M.stories.map(()=>[[],[]]);for(const p of P)if(p[2]>=0){cen[p[2]][0].push(p[0]);cen[p[2]][1].push(p[1])}
 const med=a=>{a.sort((x,y)=>x-y);return a[a.length>>1]||0};const C=cen.map(([x,y])=>[med(x),med(y)]);
 function draw(){const cs=getComputedStyle(document.documentElement),fg=cs.getPropertyValue('--fg'),mu=cs.getPropertyValue('--mute'),dt=cs.getPropertyValue('--dot'),bg=cs.getPropertyValue('--bg'),dpr=devicePixelRatio||1;
  W=cv.clientWidth;const fit=innerWidth>760,maxH=fit?Math.max(300,innerHeight-(cv.getBoundingClientRect().top+scrollY)-24-slack):W;sc=Math.min((W-2*pad)/M.w,(maxH-2*pad)/M.h);ox=(W-M.w*sc)/2;H=Math.round(M.h*sc+2*pad);
  cv.style.height=H+'px';cv.width=W*dpr;cv.height=H*dpr;const c=cv.getContext('2d');c.setTransform(dpr,0,0,dpr,0,0);c.clearRect(0,0,W,H);
  const r=W<500?1.1:1.4,X=p=>ox+p[0]*sc,Y=p=>pad+p[1]*sc,dot=(p,col,rr)=>{c.fillStyle=col;c.fillRect(X(p)-rr,Y(p)-rr,2*rr,2*rr)};
  for(const p of P)if(p[2]<0)dot(p,dt,r);c.globalAlpha=cur>=0?.35:.8;for(const p of P)if(p[2]>=0)dot(p,mu,r);c.globalAlpha=1;
  if(cur>=0)for(const p of P)if(p[2]===cur)dot(p,fg,r+1.2);
  if(fit&&!slack){const o=document.documentElement.scrollHeight-innerHeight;if(o>0){slack=o+2;return draw()}}
  if(W<560)return;const boxes=[],n=W<800?5:8;c.font='11px '+getComputedStyle(hv).fontFamily;c.textBaseline='middle';
  for(let k=0;k<M.stories.length&&boxes.length<n;k++){if(cur>=0&&k!==cur)continue;const s=M.stories[k];let tx=(L==='es'&&s.title_es)||s.title||'';if(tx.length>44)tx=tx.slice(0,42).replace(/\s+\S*$/,'')+'…';
   const w=c.measureText(tx).width,x=Math.max(2,Math.min(W-w-2,X(C[k])-w/2)),y=Y(C[k]),bb=[x-4,y-10,x+w+4,y+10];
   if(boxes.some(o=>bb[0]<o[2]&&bb[2]>o[0]&&bb[1]<o[3]&&bb[3]>o[1]))continue;boxes.push(bb);
   c.globalAlpha=.85;c.fillStyle=bg;c.fillRect(bb[0],y-8,bb[2]-bb[0],16);c.globalAlpha=1;c.fillStyle=fg;c.fillText(tx,x,y);if(cur>=0)break}}
 function pick(e){const b=cv.getBoundingClientRect(),x=(e.clientX-b.left-ox)/sc,y=(e.clientY-b.top-pad)/sc,lim=(10/sc)**2;let best=-1,bd=lim,un=-1,ud=lim;
  for(let i=0;i<P.length;i++){const dx=P[i][0]-x,dy=P[i][1]-y,d=dx*dx+dy*dy;if(P[i][2]<0){if(d<ud){ud=d;un=i}}else if(d<bd){bd=d;best=i}}return best>=0?P[best][2]:un>=0?-1:-2}
 function show(k){if(k===cur)return;cur=k;draw();if(k===-2){hv.className='hov mute';hv.textContent=T.hov;return}
  if(k===-1){hv.className='hov mute';hv.textContent=T.none;return}const s=M.stories[k];hv.className='hov';
  hv.innerHTML=`<a href="#/s/${s.id}">${esc((L==='es'&&s.title_es)||s.title||'')}</a> <span class="mute">· ${fmt(s.size)} ${t('posts')}</span>`}
 cv.onpointermove=e=>show(pick(e));cv.onpointerleave=e=>{if(e.pointerType==='mouse')show(-2)};
 cv.onclick=e=>{const k=pick(e);if(k>=0&&e.pointerType==='mouse'&&k===cur)location.hash='#/s/'+M.stories[k].id;else show(k)};
 redrawMap=()=>{if(document.body.contains(cv)){slack=0;draw()}};draw()}
function electionView(){const E=D.election,v=document.getElementById('view');if(!E){v.innerHTML='';return}
 const today=new Date(new Date().toISOString().slice(0,10)+'T00:00:00Z'),dd=Math.round((new Date(E.day+'T00:00:00Z')-today)/864e5);
 const cd=dd>0?t('daysTo').replace('%d',dd):dd===0?t('eDay'):t('daysSince').replace('%d',-dd);
 const all=E.daily['']||[],bw=innerWidth<=760?12:24;
 let h=`<h2>${t('eTitle')}</h2><p class="big">${cd}</p>`;
 h+=`<section><div class="mute">${t('ePosts')} · ${t('sinceStart').replace('%s',E.start)}</div>${chart(all,E.start)}<div class="mute" style="font-size:13px;margin-top:8px">${t('eTerms')}: ${E.terms.map(x=>`<a href="#/search?q=${encodeURIComponent('"'+x+'"')}">"${esc(x)}"</a>`).join(' · ')}</div></section>`;
 const gs=Object.keys(D.groups).filter(g=>E.daily[g]).map(g=>({g,w:E.daily[g].slice(-7).reduce((a,b)=>a+b,0),n:E.daily[g].reduce((a,b)=>a+b,0)})).sort((a,b)=>b.w-a.w||b.n-a.n),gm=Math.max(1,...gs.map(x=>x.w));
 h+=`<section><h2>${t('eByGroup')}</h2><div class="tw"><table><tr><th></th><th class="num">${t('last7')}</th><th></th><th class="num">${t('sinceStart').replace('%s',E.start)}</th></tr>${gs.map(x=>`<tr><td>${esc(G(x.g))}</td><td class="num">${fmt(x.w)}</td><td>${bar(x.w||0,gm,bw)}</td><td class="num">${fmt(x.n)}</td></tr>`).join('')}</table></div></section>`;
 h+=`<section><h2>${t('eStories')}</h2>${E.stories.length?E.stories.map(s=>`<div class="story-row"><div class="meta"><span class="tag">${esc(s.week)}</span><span class="tag">${fmt(s.size)} ${t('posts')}</span><span class="tag">${fmt(s.channels)} ${t('chans')}</span></div><a href="#/s/${s.id}">${esc((L==='es'&&s.title_es)||s.title)}</a></div>`).join(''):`<p class="mute">${t('noneYet')}</p>`}</section>`;
 const wk=a=>'<span class="spark">'+(a||[]).map(v=>{const m=Math.max(1,...a);return v?BL[Math.min(7,Math.floor(v/m*7.99))]:'·'}).join('')+'</span>';
 h+=`<section><h2>${t('eParties')}</h2><div class="tw"><table><tr><th></th><th>${t('tier')}</th><th>${t('perWeek')}</th><th class="num">${t('avgViews')}</th><th class="num">${t('eHits')}</th></tr>${E.parties.map(p=>`<tr><td>${p.archived?`<a href="#/c/${esc(p.handle)}">${esc(p.title||p.handle)}</a>`:`${esc(p.handle)} <span class="mute">· ${t('queued')}</span>`}</td><td class="mute">${esc(p.tier)}</td><td>${p.archived?wk(p.weeks):''}</td><td class="num">${p.archived?fmt(p.views):''}</td><td class="num">${p.archived?fmt(p.hits):''}</td></tr>`).join('')}</table></div></section>`;
 h+=`<section><h2>${t('ePages')}</h2>${E.pages.length?E.pages.map(u=>`<div class="story-row"><div class="meta"><span class="tag">${fmt(u.channels)} ${t('chans')}</span><span class="tag">${fmt(u.n)} ${t('posts')}</span><span class="tag">${esc(u.domain)}</span></div><a href="${esc(u.url)}" target="_blank" rel="noopener nofollow">${esc(u.title||u.url)}</a></div>`).join(''):`<p class="mute">${t('noneYet')}</p>`}</section>`;
 v.innerHTML=h}
function route(){if(searchController){searchController.abort();searchController=null}const hash=location.hash.replace(/^#\/?/,''),split=hash.indexOf('?'),p=split<0?hash:hash.slice(0,split),query=split<0?'':hash.slice(split+1);const m=p.match(/^c\/(.+)$/),sm=p.match(/^s\/(\d+)$/);const isHome=!p;
 document.body.classList.toggle('home',isHome);document.documentElement.lang=L;
 {const b=document.getElementById('brand');b.setAttribute('aria-label',t('name'));b.title=t('name')}
 document.title=`${t('name')}${isHome?'':' / '+(m?decodeURIComponent(m[1]):p==='search'?t('messageSearch'):p==='links'?t('links'):p==='29n'?t('e29n'):p==='method'?t('method'):p==='stories'||p==='threads'||sm?t('stories'):t('channels'))}`;
 nav(isHome?'':(m?'channels':p==='search'||p==='links'||p==='method'||p==='29n'?p:(p==='stories'||p==='threads'||sm)?'stories':'channels'));
 if(isHome)home();else if(m)channel(decodeURIComponent(m[1]));else if(sm)storyView(sm[1]);else if(p==='stories'||p==='threads'){const q=new URLSearchParams(query);(p==='threads'||q.get('view')==='time')?threadsView(q):storiesView(q)}else if(p==='search')messageSearch(new URLSearchParams(query));else if(p==='links')linksView(new URLSearchParams(query));else if(p==='method')methodView();else if(p==='29n')electionView();else index();window.scrollTo(0,0)}
document.getElementById('lang').onclick=()=>{L=L==='en'?'es':'en';localStorage.setItem('lang',L);document.getElementById('lang').textContent=L==='en'?'[es]':'[en]';applyTheme();route()};
document.getElementById('lang').textContent=L==='en'?'[es]':'[en]';
const th=document.getElementById('theme');let dark=(localStorage.getItem('theme')||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'))==='dark';
function applyTheme(){document.documentElement.dataset.theme=dark?'dark':'light';th.textContent=`[${t(dark?'light':'dark')}]`}applyTheme();
th.onclick=()=>{dark=!dark;localStorage.setItem('theme',dark?'dark':'light');applyTheme();redrawMap&&redrawMap()};
window.onhashchange=()=>route();route();
let compact=innerWidth<=760;window.onresize=()=>{const next=innerWidth<=760;if(next!==compact){compact=next;if(document.body.classList.contains('home'))home()}};
</script>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "site"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    data = build()
    html = HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    (out / "index.html").write_text(html, encoding="utf-8")
    print(f"{out/'index.html'}: {len(data['channels'])} channels, {data['total']} messages, {len(html)//1024} KB")


if __name__ == "__main__":
    main()
