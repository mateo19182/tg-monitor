#!/usr/bin/env python3
"""Build site/index.html from tg.db + channels.csv + wiki.csv. Message search uses /api/search.

  python site.py [--out site]
"""
import argparse
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
    "B_es_aggregator": {"en": "Spanish-language channels listed as frequent sources of the Pravda network's Spanish pages", "es": "Canales en español citados como fuentes frecuentes de las páginas en español de la red Pravda"},
    "C_spain_node": {"en": "Channels whose operators are located in Spain, per published research", "es": "Canales cuyos administradores se sitúan en España, según investigaciones publicadas"},
    "D_spain_farright_election": {"en": "Spanish right-wing and nationalist parties, organisations and activists", "es": "Partidos, organizaciones y activistas españoles de derecha y nacionalistas"},
    "E_russian_parent": {"en": "Russian- or English-language channels of which tier A channels are editions (partial archive)", "es": "Canales en ruso o inglés de los que los canales del nivel A son ediciones (archivo parcial)"},
    "F_russian_official": {"en": "Russian state institutions and state media", "es": "Instituciones y medios estatales rusos"},
    "G_allied_state_media_es": {"en": "Spanish-language state media of other countries (partial archive)", "es": "Medios estatales en español de otros países (archivo parcial)"},
    "H_discovered_es_aggregator": {"en": "Channels not named in the consulted research; included because tracked channels forward them", "es": "Canales no citados en las investigaciones consultadas; incluidos porque los canales seguidos los reenvían"},
    "I_discussion_group": {"en": "Discussion groups linked to tracked channels (from 2025)", "es": "Grupos de debate vinculados a canales seguidos (desde 2025)"},
    "J_spain_parties": {"en": "Parliamentary Spanish parties and their leaders", "es": "Partidos españoles con representación parlamentaria y sus líderes"},
    "K_spain_left": {"en": "Spanish left-wing, anti-NATO and solidarity organisations and media", "es": "Organizaciones y medios españoles de izquierda, contrarios a la OTAN y de solidaridad"},
    "L_spain_media": {"en": "Spanish media outlets and commentators", "es": "Medios de comunicación y comentaristas españoles"},
    "M_public_channels": {"en": "Public channels of individual authors, associations and community publishers", "es": "Canales públicos de autores, asociaciones y comunidades"},
    "N_spain_institution": {"en": "Spanish state institutions", "es": "Instituciones del Estado español"},
    "O_factchecker": {"en": "Fact-checking organisations", "es": "Organizaciones de verificación"},
    "P_regional_politics": {"en": "Regional and nationalist parties, organisations and media (Catalonia, Basque Country, Galicia, others)", "es": "Partidos, organizaciones y medios regionales y nacionalistas (Cataluña, País Vasco, Galicia, otros)"},
    "Q_mobilisation": {"en": "Unions, housing, civic, professional and diaspora organisations", "es": "Sindicatos y organizaciones de vivienda, cívicas, profesionales y de diáspora"},
    "R_conspiracy_pivot": {"en": "Channels documented by Maldita.es (2022) as moving from COVID-19 content to the war in Ukraine", "es": "Canales documentados por Maldita.es (2022) como pasando de contenido sobre COVID-19 a la guerra en Ucrania"},
    "S_influencer": {"en": "Individual commentators and streamers", "es": "Comentaristas y streamers individuales"},
    "T_counterpart": {"en": "Ukrainian, EU, Israeli and Moroccan official or aligned channels", "es": "Canales oficiales o afines de Ucrania, la UE, Israel y Marruecos"},
    "U_campaign_2026": {"en": "Candidates, party branches and youth wings around the 29 November 2026 election", "es": "Candidatos, agrupaciones territoriales y juventudes en torno a las elecciones del 29 de noviembre de 2026"},
    "V_civil_society": {"en": "Civil-society organisations: environmental, feminist, consumer, health, education, rights, religious, professional", "es": "Organizaciones de la sociedad civil: ambientales, feministas, de consumidores, sanidad, educación, derechos, religiosas, profesionales"},
    "W_journalist": {"en": "Journalists' and commentators' personal and programme channels", "es": "Canales personales y de programas de periodistas y comentaristas"},
    "X_diaspora": {"en": "Diaspora and migrant-community channels in Spain (Russian, Ukrainian, Arabic, Latin American)", "es": "Canales de comunidades de diáspora e inmigrantes en España (rusa, ucraniana, árabe, latinoamericana)"},
    "Y_local": {"en": "Local news, incident and neighbourhood channels", "es": "Canales locales de noticias, sucesos y vecindario"},
    "Z_meme_finance": {"en": "Political humour, libertarian, crypto and prepper channels", "es": "Canales de humor político, libertarios, cripto y preparacionistas"},
}


def read_csv(p: Path) -> list[dict]:
    with p.open(newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if r and not next(iter(r.values())).startswith("#")]


def domain(u: str) -> str | None:
    try:
        h = urlsplit(u).hostname or ""
    except ValueError:
        return None
    return h.lower().removeprefix("www.") or None


def build() -> dict:
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    watch = read_csv(HERE / "channels.csv")
    wiki = defaultdict(list)
    for r in read_csv(HERE / "wiki.csv"):
        wiki[r["handle"].lower()].append({"fact": r["fact"], "source": r["source"]})
    sources = {r["key"]: r for r in read_csv(HERE / "sources.csv")}
    arenas = {r["key"]: {"axis": r["axis"], "en": r["en"], "es": r["es"]} for r in read_csv(HERE / "arenas.csv")} if (HERE / "arenas.csv").exists() else {}

    chans = {r["id"]: dict(r) for r in db.execute("SELECT * FROM channels")}
    by_handle = {(c["username"] or str(c["id"])).lower(): c for c in chans.values()}
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
            "handle": w["handle"], "tier": w["tier"], "since": w.get("since") or None,
            "id": cid, "title": c["title"] if c else None, "about": c["about"] if c else None,
            "subs": c["participants"] if c else None, "created": (c["created_at"] or "")[:10] if c else None,
            "n": st.get("n", 0), "first": (st.get("lo") or "")[:10], "last": (st.get("hi") or "")[:10],
            "views": st.get("views"), "n_fwd": st.get("n_fwd", 0), "senders": st.get("senders", 0),
            "daily": daily.get(cid, [0] * DAYS) if cid else [0] * DAYS,
            "hours": hours.get(cid) if cid else None,
            "fwd_from": [{**label(s), "n": n} for s, n in fwd_from[cid].most_common(TOP)] if cid else [],
            "fwd_to": [{**label(s), "n": n} for s, n in fwd_to[cid].most_common(TOP)] if cid else [],
            "domains": domains[cid].most_common(TOP) if cid else [],
            "facts": wiki.get(h, []),
            "linked_note": w.get("note") if w["tier"] == "I_discussion_group" else None,
        })
    total = db.execute("SELECT COUNT(*), MIN(date), MAX(date) FROM messages").fetchone()
    return {
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "days": DAYS, "start": start, "total": total[0], "range": [(total[1] or "")[:10], (total[2] or "")[:10]],
        "daily": [sum(counts[i] for counts in daily.values()) for i in range(DAYS)],
        "tiers": TIERS, "sources": sources, "channels": out, "arenas": arenas,
    }


HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Telegram archive</title>
<style>
:root{color-scheme:light;--bg:#f7f7f4;--fg:#1a1a1a;--mute:#6b6b66;--line:#d8d8d2;--dot:#cfcfc8;--acc:#1a1a1a;--bar:#1a1a1a}
:root:not([data-theme="light"]){ @media (prefers-color-scheme: dark){ color-scheme:dark;--bg:#0f0f0e;--fg:#e6e6e0;--mute:#8a8a84;--line:#2a2a28;--dot:#2a2a28;--acc:#e6e6e0;--bar:#e6e6e0 } }
:root[data-theme="dark"]{color-scheme:dark;--bg:#0f0f0e;--fg:#e6e6e0;--mute:#8a8a84;--line:#2a2a28;--dot:#2a2a28;--acc:#e6e6e0;--bar:#e6e6e0}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--fg)}
body{font:14px/1.5 ui-monospace,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
 background-image:radial-gradient(var(--dot) .8px,transparent .9px);background-size:14px 14px;min-height:100vh}
a{color:var(--fg);text-decoration:none}a:hover{text-decoration:underline}
.wrap{max-width:1180px;margin:0 auto;padding:16px}
header{display:flex;flex-wrap:wrap;gap:8px 20px;align-items:baseline;border-bottom:1px solid var(--line);padding-bottom:10px;margin-bottom:18px}
header h1{font-size:14px;margin:0;font-weight:700}
header .r{margin-left:auto;display:flex;gap:14px}
.btn{cursor:pointer;color:var(--mute);background:none;border:0;padding:0;font:inherit}.btn:hover{color:var(--fg)}
a:focus-visible,button:focus-visible,input:focus-visible{outline:1px dashed var(--fg);outline-offset:4px}
main{display:grid;grid-template-columns:220px 1fr;gap:28px}main>*{min-width:0}#view{overflow-wrap:anywhere}.tw{overflow-x:auto}
nav{position:sticky;top:12px;align-self:start;max-height:calc(100vh - 24px);overflow:auto;font-size:13px}
nav h3{margin:14px 0 4px;font-size:12px;color:var(--mute);font-weight:400}
nav ul{list-style:none;margin:0;padding:0}nav li{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
nav li a{color:var(--fg)}nav li.cur a{text-decoration:underline}
h2{font-size:14px;margin:0 0 2px;font-weight:700}
.ul{color:var(--mute);margin-bottom:14px}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{text-align:left;padding:3px 10px 3px 0;vertical-align:top;border-bottom:1px solid var(--line)}
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
ol.facts{padding-left:22px}ol.facts li{margin-bottom:6px}
.src{color:var(--mute)}
section{margin-bottom:26px}
.big{font-size:22px;line-height:1.1;margin:0 0 4px}
.search{background:transparent;border:0;border-bottom:1px solid var(--line);color:var(--fg);font:inherit;padding:2px 0;width:100%;outline:none;margin-bottom:8px}
.chart{white-space:pre;line-height:1.15;overflow:auto;color:var(--bar);position:relative}
.chart .lbl{color:var(--mute)}
.tip{position:absolute;pointer-events:none;background:var(--bg);border:1px solid var(--line);padding:2px 6px;font-size:12px;display:none}
#menu{display:none}
body.home main{display:block}body.home #nav,body.home #menu,body.home #hdr{display:none}
.home-page{max-width:880px;margin:48px auto 24px}
.home-heading{display:flex;align-items:center;justify-content:space-between;gap:24px;margin-bottom:32px}
.home-heading h2{font-size:clamp(24px,4vw,36px);font-weight:400;line-height:1.2;margin:0 0 12px}
.archive-mark{font-family:inherit;font-size:12px;white-space:pre;line-height:1.2;color:var(--mute);margin:0;flex-shrink:0}
.home-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:24px;padding:22px 0;border-top:1px dashed var(--line);border-bottom:1px dashed var(--line);margin:0 0 32px}
.home-stats dt{font-size:12px;color:var(--mute)}.home-stats dd{font-size:24px;margin:4px 0 0}
.home-grid{display:grid;grid-template-columns:1fr 2fr;gap:36px}
.home-page h3{font-size:13px;font-weight:400;color:var(--mute);margin:0 0 12px}
.archive-tree{list-style:none;margin:0;padding:0}.archive-tree li{margin:8px 0}.archive-tree .branch{color:var(--mute);white-space:pre}
.home-page .chart{font-size:12px}.home-page .dates{font-size:12px;margin-top:10px}
.home-footer{border-top:1px dashed var(--line);padding-top:14px;margin-top:24px;font-size:12px;color:var(--mute)}
.message-form{margin:20px 0 24px}.message-query{display:flex;gap:16px;align-items:end}.message-query label{flex:1;min-width:0}
.message-form label{display:block;color:var(--mute);font-size:12px}
.message-form input,.message-form select{display:block;width:100%;min-width:0;background:var(--bg);color:var(--fg);font:inherit;font-size:14px;border:0;border-bottom:1px solid var(--line);border-radius:0;padding:6px 0}
.message-form button{padding:6px 0;white-space:nowrap}.message-form .hint{font-size:12px;margin-top:6px}
.message-filters{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin-top:18px}
.message-result{padding:16px 0;border-bottom:1px solid var(--line)}.message-meta{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:12px}
.message-text{white-space:pre-wrap;margin:10px 0;overflow-wrap:anywhere}.message-result .original{font-size:12px}
mark{background:var(--fg);color:var(--bg)}.pagination{display:flex;gap:18px;margin-top:20px;align-items:center;font-size:13px}
.story-row{padding:10px 0;border-bottom:1px solid var(--line)}.story-row .meta{font-size:12px;display:flex;flex-wrap:wrap;gap:4px 12px}
.story-row .meta .tag{color:var(--mute)}.story-row .sum{margin-top:4px}
.filters{display:flex;flex-wrap:wrap;gap:6px 14px;margin:10px 0 16px;font-size:13px}.filters a.on{text-decoration:underline}
.thread{padding:10px 0;border-bottom:1px solid var(--line)}.thread .wk{display:flex;gap:2px;align-items:flex-end;height:22px;margin-top:4px}.thread .wk span{display:block;width:14px;background:var(--bar);min-height:2px}.thread .wk span.gap{background:transparent;border-bottom:1px dotted var(--line)}
.chain{list-style:none;padding:0;margin:0}.chain li{margin:3px 0}
.post{padding:10px 0;border-bottom:1px solid var(--line)}.post .meta{font-size:12px;display:flex;flex-wrap:wrap;gap:4px 12px}.post .txt{white-space:pre-wrap;margin:6px 0;overflow-wrap:anywhere}
@media(max-width:760px){main{grid-template-columns:1fr;gap:12px}nav{display:none;position:static;max-height:none;border-bottom:1px solid var(--line);padding-bottom:10px}
 body.nav-open nav{display:block}#menu{display:inline}#hdr{display:none}.m-hide{display:none}.wrap{padding:12px}
 .kv{grid-template-columns:1fr;gap:0 0}.kv div:nth-child(odd){margin-top:6px}.big{font-size:18px}
 .home-page{margin-top:28px}.home-heading{gap:12px}.archive-mark{font-size:10px}.home-stats{grid-template-columns:repeat(2,1fr);gap:20px}.home-grid{grid-template-columns:1fr;gap:24px}
 .message-filters{grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.message-query{gap:12px}}
@media(max-width:380px){.archive-mark{display:none}}
</style>
</head>
<body>
<div class="wrap">
<header>
 <h1><a href="#/" id="brand">Telegram archive</a></h1>
 <span class="mute" id="hdr"></span>
 <span class="r"><button class="btn" id="menu" type="button" aria-controls="nav" aria-expanded="false">[index]</button><button class="btn" id="lang" type="button">[es]</button><button class="btn" id="theme" type="button">[dark]</button></span>
</header>
<main><nav id="nav"></nav><div id="view"></div></main>
</div>
<script id="data" type="application/json">__DATA__</script>
<script>
const D=JSON.parse(document.getElementById('data').textContent);
const T={
 en:{channels:'channels',messages:'messages',archive:'archive',tiers:'tiers',sources:'sources',handle:'handle',title:'title',tier:'tier',subs:'subscribers',posts:'posts',last:'last post',days:'last %d days',search:'search /',
  about:'description (as published by the channel)',facts:'published research',stats:'archive',created:'channel created',first:'first archived post',views:'total views',fwd:'posts that are forwards',senders:'distinct senders',
  fwdfrom:'most forwarded from',fwdto:'forwarded by tracked channels',domains:'most linked domains',none:'none',notyet:'not yet archived',perday:'posts per day',tracked:'tracked',untracked:'not tracked',
  tierlist:'tiers',built:'updated',since:'archived from',nofacts:'no published research recorded for this channel.',group:'discussion group',hours:'posts by weekday and hour (UTC)',days7:'Mo Tu We Th Fr Sa Su',
  name:'Telegram archive',home:'home',browse:'browse channels',directory:'index',indexed:'channels in index',cited:'cited facts',activity:'messages per day',period:'archive dates',light:'light',dark:'dark',
  messageSearch:'search messages',query:'text',searchGo:'search',queryHint:'Words or "quoted phrases"',allChannels:'all channels',dateFrom:'from (UTC)',dateTo:'to (UTC)',order:'order',relevance:'relevance',newest:'newest',oldest:'oldest',
  loading:'searching…',results:'results',noresults:'no matching messages.',original:'original post',previous:'previous',next:'next',page:'page',
  stories:'stories',firstPost:'first post',tierOrder:'order of tiers',threads:'story threads',weeks:'weeks',minWeeks:'at least %d weeks',week:'week',region:'region',theme:'theme',all:'all',story:'story',earlier:'earlier weeks',later:'later weeks',related:'related story',nostories:'no stories for this selection.',postsIn:'posts in this story',chans:'channels',showing:'showing',
  invalid_query:'Enter words or balanced "quoted phrases". Maximum 20 terms.',query_too_long:'Search text is limited to 300 characters.',invalid_date:'Enter a valid date.',date_range:'The start date must be on or before the end date.',invalid_sort:'Choose a valid order.',invalid_page:'Choose a valid page.',invalid_channel:'Choose a channel in the index.',invalid_request:'Check the search fields.',search_unavailable:'Search is unavailable. Try again.',search_timeout:'This search took too long. Try more words or a narrower date range.'},
 es:{channels:'canales',messages:'mensajes',archive:'archivo',tiers:'niveles',sources:'fuentes',handle:'usuario',title:'título',tier:'nivel',subs:'suscriptores',posts:'publicaciones',last:'última publicación',days:'últimos %d días',search:'buscar /',
  about:'descripción (tal como la publica el canal)',facts:'investigaciones publicadas',stats:'archivo',created:'canal creado',first:'primera publicación archivada',views:'visualizaciones totales',fwd:'publicaciones que son reenvíos',senders:'remitentes distintos',
  fwdfrom:'más reenviado desde',fwdto:'reenviado por canales seguidos',domains:'dominios más enlazados',none:'ninguno',notyet:'aún no archivado',perday:'publicaciones por día',tracked:'seguido',untracked:'no seguido',
  tierlist:'niveles',built:'actualizado',since:'archivado desde',nofacts:'no hay investigaciones publicadas registradas para este canal.',group:'grupo de debate',hours:'publicaciones por día de la semana y hora (UTC)',days7:'Lu Ma Mi Ju Vi Sá Do',
  name:'Archivo de Telegram',home:'inicio',browse:'ver canales',directory:'índice',indexed:'canales en el índice',cited:'datos con fuentes',activity:'mensajes por día',period:'fechas del archivo',light:'claro',dark:'oscuro',
  messageSearch:'buscar mensajes',query:'texto',searchGo:'buscar',queryHint:'Palabras o "frases entre comillas"',allChannels:'todos los canales',dateFrom:'desde (UTC)',dateTo:'hasta (UTC)',order:'orden',relevance:'relevancia',newest:'más recientes',oldest:'más antiguos',
  loading:'buscando…',results:'resultados',noresults:'no hay mensajes coincidentes.',original:'publicación original',previous:'anterior',next:'siguiente',page:'página',
  stories:'historias',firstPost:'primera publicación',tierOrder:'orden de niveles',threads:'hilos de historias',weeks:'semanas',minWeeks:'al menos %d semanas',week:'semana',region:'región',theme:'tema',all:'todas',story:'historia',earlier:'semanas anteriores',later:'semanas posteriores',related:'historia relacionada',nostories:'no hay historias para esta selección.',postsIn:'publicaciones en esta historia',chans:'canales',showing:'mostrando',
  invalid_query:'Introduce palabras o "frases entre comillas" cerradas. Máximo 20 términos.',query_too_long:'El texto de búsqueda está limitado a 300 caracteres.',invalid_date:'Introduce una fecha válida.',date_range:'La fecha inicial debe ser anterior o igual a la final.',invalid_sort:'Elige un orden válido.',invalid_page:'Elige una página válida.',invalid_channel:'Elige un canal del índice.',invalid_request:'Revisa los campos de búsqueda.',search_unavailable:'La búsqueda no está disponible. Inténtalo de nuevo.',search_timeout:'La búsqueda tardó demasiado. Añade palabras o reduce el intervalo de fechas.'}};
let L=localStorage.getItem('lang')==='es'?'es':'en';
const t=k=>T[L][k]||k;
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const fmt=n=>n==null?'—':Number(n).toLocaleString(L==='es'?'es-ES':'en-GB');
const BL='▁▂▃▄▅▆▇█';const SP=()=>innerWidth<=760?30:60;
function spark(a,n=60){const off=a.length-n;a=a.slice(off);const m=Math.max(1,...a);const s=new Date(D.start);s.setDate(s.getDate()+off);return '<span class="spark">'+a.map((v,i)=>{const d=new Date(s);d.setDate(d.getDate()+i);return `<span title="${d.toISOString().slice(0,10)}: ${v}">${v?BL[Math.min(7,Math.floor(v/m*7.99))]:'·'}</span>`}).join('')+'</span>'}
function bar(n,max,w=24){return '<span class="bar">'+'█'.repeat(Math.max(1,Math.round(n/max*w)))+'</span>'}
function link(c){return c.handle?`<a href="https://t.me/${esc(c.handle)}" target="_blank" rel="noopener">@${esc(c.handle)}</a>`:`<span class="mute">id ${c.id}</span>`}
function chanLink(c){return c.tracked?`<a href="#/c/${esc(c.handle||c.id)}">${esc(c.title||c.handle||c.id)}</a>`:esc(c.title||c.handle||('id '+c.id))}
function nav(cur){const byT={};D.channels.forEach(c=>(byT[c.tier]=byT[c.tier]||[]).push(c));
 let h=`<input class="search" id="q" aria-label="${t('search')}" placeholder="${t('search')}"><ul><li><a href="#/">${t('home')}</a></li><li><a href="#/search">${t('messageSearch')}</a></li><li><a href="#/stories">${t('stories')}</a></li><li><a href="#/threads">${t('threads')}</a></li><li><a href="#/channels">${t('channels')}</a></li><li><a href="#/tiers">${t('tiers')}</a></li><li><a href="#/sources">${t('sources')}</a></li></ul>`;
 for(const k of Object.keys(D.tiers)){if(!byT[k])continue;h+=`<h3>${k.slice(0,1)} · ${byT[k].length}</h3><ul>`+byT[k].map(c=>`<li class="${cur===c.handle.toLowerCase()?'cur':''}"><a href="#/c/${esc(c.handle)}">${esc(c.title||c.handle)}</a></li>`).join('')+'</ul>'}
 document.getElementById('nav').innerHTML=h;
 const q=document.getElementById('q');q.oninput=()=>{const v=q.value.toLowerCase();document.querySelectorAll('#nav li').forEach(li=>{li.style.display=li.textContent.toLowerCase().includes(v)?'':'none'})};
 document.onkeydown=e=>{if(e.key==='/'&&!e.target.closest('input,textarea,select,[contenteditable]')&&!e.ctrlKey&&!e.metaKey&&!e.altKey){e.preventDefault();if(innerWidth<=760){document.body.classList.add('nav-open');document.getElementById('menu').setAttribute('aria-expanded','true')}q.focus()}}}
function home(){
 const counts=[[t('indexed'),D.channels.length],[t('messages'),D.total],[t('cited'),D.channels.reduce((n,c)=>n+c.facts.length,0)],[t('sources'),Object.keys(D.sources).length]];
 const n=SP(),daily=D.daily.slice(-n),start=new Date(D.start+'T00:00:00Z');start.setUTCDate(start.getUTCDate()+D.days-n);
 const first=start.toISOString().slice(0,10),last=new Date(start);last.setUTCDate(last.getUTCDate()+n-1);
 document.getElementById('view').innerHTML=`<div class="home-page">
  <section class="home-heading"><div><h2>${t('name')}</h2><div class="mute">${t('period')}<br>${D.range[0]||'—'} → ${D.range[1]||'—'}</div></div>
   <pre class="archive-mark" aria-hidden="true">   .------------.
   |  ________  |
   | |___[]___| |
   |  ________  |
   | |___[]___| |
   |  ________  |
   | |___[]___| |
   '------------'</pre></section>
  <dl class="home-stats">${counts.map(([label,n])=>`<div><dt>${label}</dt><dd>${fmt(n)}</dd></div>`).join('')}</dl>
  <div class="home-grid"><section><h3>${t('directory')} /</h3><ul class="archive-tree">
   <li><span class="branch" aria-hidden="true">├── </span><a href="#/search">[${t('messageSearch')}]</a></li>
   <li><span class="branch" aria-hidden="true">├── </span><a href="#/stories">[${t('stories')}]</a></li>
   <li><span class="branch" aria-hidden="true">├── </span><a href="#/threads">[${t('threads')}]</a></li>
   <li><span class="branch" aria-hidden="true">├── </span><a href="#/channels">[${t('browse')}]</a></li>
   <li><span class="branch" aria-hidden="true">├── </span><a href="#/tiers">[${t('tiers')}]</a></li>
   <li><span class="branch" aria-hidden="true">└── </span><a href="#/sources">[${t('sources')}]</a></li>
  </ul></section><section><h3>${t('activity')} · ${t('days').replace('%d',n)}</h3>${chart(daily,first)}<div class="mute dates">${first} → ${last.toISOString().slice(0,10)}</div></section></div>
  <footer class="home-footer">${t('built')} ${D.built}</footer></div>`;
 document.onkeydown=e=>{if(e.key==='/'&&!e.target.closest('input,textarea,select,[contenteditable]')&&!e.ctrlKey&&!e.metaKey&&!e.altKey){e.preventDefault();location.hash='/search'}};
}
let searchController=null;
function searchURL(params,page=1){const p=new URLSearchParams(params);p.delete('page');if(page>1)p.set('page',page);return '#/search'+(p.size?'?'+p.toString():'')}
async function messageSearch(params){
 const options=D.channels.filter(c=>c.id).sort((a,b)=>(a.title||a.handle).localeCompare(b.title||b.handle));
 document.getElementById('view').innerHTML=`<h2>${t('messageSearch')}</h2><div class="ul">==============</div>
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
 const view=document.getElementById('view');view.innerHTML=`<h2>${t('stories')}</h2><div class="ul">=======</div><div class="mute" role="status">${t('loading')}</div>`;
 const controller=new AbortController();searchController=controller;
 try{
  let week=params.get('week');
  const wk=await (await fetch('/api/stories',{signal:controller.signal})).json();if(controller.signal.aborted)return;
  if(!wk.weeks.length){view.innerHTML=`<h2>${t('stories')}</h2><div class="ul">=======</div><p class="mute">${t('nostories')}</p>`;return}
  if(!week||!wk.weeks.some(w=>w.week===week))week=wk.weeks[0].week;
  const region=params.get('region')||'',theme=params.get('theme')||'';
  const data=await (await fetch('/api/stories?'+new URLSearchParams({week,region,theme}),{signal:controller.signal})).json();if(controller.signal.aborted)return;
  const sel=(k,v)=>storiesURL({week,region:k==='region'?v:region,theme:k==='theme'?v:theme});
  let h=`<h2>${t('stories')}</h2><div class="ul">=======</div>`;
  h+=`<div class="filters"><span class="mute">${t('week')}</span>${wk.weeks.map(w=>`<a class="${w.week===week?'on':''}" href="${esc(storiesURL({week:w.week,region,theme}))}">${esc(w.week)} <span class="mute">${fmt(w.n)}</span></a>`).join('')}</div>`;
  const keys=axis=>Object.keys(D.arenas).filter(k=>D.arenas[k].axis===axis);
  h+=`<div class="filters"><span class="mute">${t('region')}</span><a class="${region?'':'on'}" href="${esc(sel('region',''))}">${t('all')}</a>${keys('region').filter(k=>data.regions[k]).map(k=>`<a class="${region===k?'on':''}" href="${esc(sel('region',k))}">${esc(A(k))} <span class="mute">${data.regions[k]}</span></a>`).join('')}</div>`;
  h+=`<div class="filters"><span class="mute">${t('theme')}</span><a class="${theme?'':'on'}" href="${esc(sel('theme',''))}">${t('all')}</a>${keys('theme').concat(keys('bucket')).filter(k=>data.themes[k]).map(k=>`<a class="${theme===k?'on':''}" href="${esc(sel('theme',k))}">${esc(A(k))} <span class="mute">${data.themes[k]}</span></a>`).join('')}</div>`;
  h+=`<div class="mute">${t('showing')} ${fmt(data.stories.length)} / ${fmt(data.total)} · ${t('posts')}: ${fmt(data.stories.reduce((n,s)=>n+s.size,0))}</div>`;
  if(!data.stories.length)h+=`<p class="mute">${t('nostories')}</p>`;
  for(const s of data.stories)h+=`<div class="story-row"><div><a href="#/s/${s.id}">${esc(TT(s))}</a>${s.prev?` <span class="mute" title="${t('earlier')}">⟵</span>`:''}</div><div class="meta"><span>${fmt(s.size)} ${t('posts')} · ${fmt(s.channels)} ${t('chans')}</span><span class="tag">${esc(A(s.region))}</span>${s.themes.map(k=>`<span class="tag">${esc(A(k))}</span>`).join('')}</div></div>`;
  view.innerHTML=h;
 }catch(e){if(e.name!=='AbortError')view.innerHTML=`<h2>${t('stories')}</h2><div class="ul">=======</div><p class="mute">${t('search_unavailable')}</p>`}
}
async function threadsView(params){
 const view=document.getElementById('view');const min=Math.max(2,parseInt(params.get('min')||'3'));
 view.innerHTML=`<h2>${t('threads')}</h2><div class="ul">=============</div><div class="mute" role="status">${t('loading')}</div>`;
 const controller=new AbortController();searchController=controller;
 try{
  const d=await (await fetch('/api/threads?min='+min,{signal:controller.signal})).json();if(controller.signal.aborted)return;
  const allWeeks=[...new Set(d.threads.flatMap(x=>x.weeks.map(w=>w.week)))].sort();
  let h=`<h2>${t('threads')}</h2><div class="ul">=============</div><div class="filters"><span class="mute">${t('weeks')}</span>${[2,3,5,8].map(n=>`<a class="${n===min?'on':''}" href="#/threads?min=${n}">${t('minWeeks').replace('%d',n)}</a>`).join('')}</div>`;
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
  let h=`<h2>${esc(TT(s))}</h2><div class="ul">${'='.repeat(Math.min(60,TT(s).length))}</div>`;
  h+=`<div class="kv"><div>${t('week')}</div><div><a href="${esc(storiesURL({week:s.week}))}">${esc(s.week)}</a></div><div>${t('region')}</div><div><a href="${esc(storiesURL({week:s.week,region:s.region}))}">${esc(A(s.region))}</a></div><div>${t('theme')}</div><div>${s.themes.map(k=>`<a href="${esc(storiesURL({week:s.week,theme:k}))}">${esc(A(k))}</a>`).join(' · ')}</div><div>${t('posts')}</div><div>${fmt(s.size)} · ${fmt(s.channels_n)} ${t('chans')} · ${s.first?esc(s.first.slice(0,10)):''} → ${s.last?esc(s.last.slice(0,10)):''}</div></div>`;
  if(s.first_post)h+=`<div class="kv"><div>${t('firstPost')}</div><div><a href="#/c/${esc(s.first_post.handle||'')}">${esc(s.first_post.title||s.first_post.handle||'')}</a> <span class="mute">${esc(s.first_post.tier)} · ${esc((s.first_post.date||'').slice(0,16).replace('T',' '))} UTC</span></div><div>${t('tierOrder')}</div><div>${s.tier_order.map(x=>`<span title="${esc((x.date||'').slice(0,16).replace('T',' '))} UTC">${esc(x.tier)}</span>`).join(' → ')}</div></div>`;
  if(SM(s))h+=`<p>${esc(SM(s))}</p>`;
  if(s.chain.length)h+=`<section><h2>${t('earlier')}</h2><ul class="chain">${s.chain.map(c=>`<li><span class="mute">${esc(c.week)}</span> <a href="#/s/${c.id}">${esc(TT(c))}</a> <span class="mute">${fmt(c.size)}</span></li>`).join('')}</ul></section>`;
  if(s.next.length)h+=`<section><h2>${t('later')}</h2><ul class="chain">${s.next.map(c=>`<li><span class="mute">${esc(c.week)}</span> <a href="#/s/${c.id}">${esc(TT(c))}</a> <span class="mute">${fmt(c.size)}</span></li>`).join('')}</ul></section>`;
  const m=s.channels.length?s.channels[0].n:1;
  h+=`<section><h2>${t('chans')}</h2><div class="tw"><table class="list">${s.channels.map(c=>`<tr><td class="num">${fmt(c.n)}</td><td>${bar(c.n,m,innerWidth<=760?12:24)}</td><td>${c.handle?`<a href="#/c/${esc(c.handle)}">${esc(c.title||c.handle)}</a> <span class="mute">@${esc(c.handle)}</span>`:esc(c.title||'')}</td></tr>`).join('')}</table></div></section>`;
  h+=`<section><h2>${t('postsIn')}</h2>${s.posts.length<s.size?`<div class="mute">${t('showing')} ${fmt(s.posts.length)} / ${fmt(s.size)}</div>`:''}`;
  h+=s.posts.map(p=>`<article class="post"><div class="meta">${p.handle?`<a href="#/c/${esc(p.handle)}">${esc(p.title||p.handle)}</a>`:esc(p.title||'')}<time class="mute" datetime="${esc(p.date)}">${esc((p.date||'').slice(0,16).replace('T',' '))} UTC</time>${p.views!=null?`<span class="mute">${fmt(p.views)} ${t('views').replace('total ','').replace('visualizaciones totales','visualizaciones')}</span>`:''}</div><div class="txt">${esc(p.text)}${p.text.length>=400?'…':''}</div>${p.url?`<a class="original" href="${esc(p.url)}" target="_blank" rel="noopener">[${t('original')}]</a>`:''}</article>`).join('');
  h+='</section>';view.innerHTML=h;
 }catch(e){if(e.name!=='AbortError')view.innerHTML=`<p class="mute">${t('search_unavailable')}</p>`}
}
let sortKey='tier',sortDir=1;
function index(){const rows=[...D.channels].sort((a,b)=>{const x=a[sortKey],y=b[sortKey];return (x==null)-(y==null)||(x>y?1:x<y?-1:0)*sortDir||a.handle.localeCompare(b.handle)});
 const th=(k,l,cls='')=>`<th class="${cls}" data-k="${k}">${l}${sortKey===k?(sortDir>0?' ▴':' ▾'):''}</th>`;
 let h=`<p class="big">${fmt(D.channels.length)} ${t('channels')} · ${fmt(D.total)} ${t('messages')}</p><div class="ul">${t('archive')} ${D.range[0]} → ${D.range[1]} · ${t('built')} ${D.built}</div>`;
 h+=`<div class="tw"><table><tr>${th('tier',t('tier'))}${th('title',t('title'))}${th('subs',t('subs'),'num m-hide')}${th('n',t('posts'),'num')}${th('last',t('last'),'m-hide')}<th>${t('days').replace('%d',SP())}</th></tr>`;
 for(const c of rows)h+=`<tr><td class="mute">${c.tier[0]}</td><td><a href="#/c/${esc(c.handle)}">${esc(c.title||c.handle)}</a> <span class="mute">@${esc(c.handle)}</span></td><td class="num m-hide">${fmt(c.subs)}</td><td class="num">${c.n?fmt(c.n):'<span class="mute">—</span>'}</td><td class="nw m-hide">${c.last||'<span class="mute">'+t('notyet')+'</span>'}</td><td>${spark(c.daily,SP())}</td></tr>`;
 h+='</table></div>';document.getElementById('view').innerHTML=h;
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
 let h=`<h2>${esc(c.title||c.handle)}</h2><div class="ul">${'='.repeat(Math.min(60,(c.title||c.handle).length))}</div>`;
 h+=`<div><a href="#/search?channel=${esc(encodeURIComponent(c.handle.toLowerCase()))}">[${t('messageSearch')}]</a></div>`;
 h+=`<div class="kv"><div>${t('handle')}</div><div>${link(c)}</div><div>${t('tier')}</div><div>${c.tier[0]} · ${esc(D.tiers[c.tier][L])}</div>`;
 if(c.linked_note)h+=`<div>${t('group')}</div><div>${esc(c.linked_note)}</div>`;
 h+=`<div>${t('subs')}</div><div>${fmt(c.subs)}</div><div>${t('created')}</div><div>${c.created||'—'}</div></div>`;
 if(c.about)h+=`<section><h2>${t('about')}</h2><div class="about">${esc(c.about)}</div></section>`;
 h+=`<section><h2>${t('facts')}</h2>`;
 if(c.facts.length){h+='<ol class="facts">'+c.facts.map(f=>{const s=D.sources[f.source];return `<li>${esc(f.fact)} <span class="src">[<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.publisher)}, ${s.date}</a>]</span></li>`}).join('')+'</ol>'}else h+=`<p class="mute">${t('nofacts')}</p>`;
 h+='</section>';
 h+=`<section><h2>${t('stats')}</h2><div class="kv"><div>${t('posts')}</div><div>${c.n?fmt(c.n):t('notyet')}</div>`;
 if(c.n){h+=`<div>${t('first')}</div><div>${c.first}${c.since?` <span class="mute">(${t('since')} ${c.since})</span>`:''}</div><div>${t('last')}</div><div>${c.last}</div><div>${t('views')}</div><div>${fmt(c.views)}</div><div>${t('fwd')}</div><div>${fmt(c.n_fwd)} (${Math.round(c.n_fwd/c.n*100)}%)</div>`;
  if(c.senders>1)h+=`<div>${t('senders')}</div><div>${fmt(c.senders)}</div>`}
 h+='</div>';
 if(c.n)h+=`<div class="mute">${t('perday')} · ${t('days').replace('%d',D.days)}</div>`+chart(c.daily)+`<div class="mute" style="margin-top:10px">${t('hours')} · ${t('days').replace('%d',D.days)}</div>`+heat(c.hours);
 h+='</section>';
 const list=(title,items,f)=>{h+=`<section><h2>${title}</h2>`;if(!items.length){h+=`<p class="mute">${t('none')}</p></section>`;return}const m=items[0].n;h+='<div class="tw"><table class="list">'+items.map(i=>`<tr><td class="num">${fmt(i.n)}</td><td>${bar(i.n,m,innerWidth<=760?12:24)}</td><td>${f(i)}</td></tr>`).join('')+'</table></div></section>'};
 list(t('fwdfrom'),c.fwd_from,i=>`${chanLink(i)} ${i.handle?`<span class="mute">@${esc(i.handle)}</span>`:''}${i.tracked?'':' <span class="mute">·</span>'}`);
 list(t('fwdto'),c.fwd_to,i=>chanLink(i));
 list(t('domains'),c.domains.map(([d,n])=>({d,n})),i=>esc(i.d));
 document.getElementById('view').innerHTML=h}
function tiers(){let h=`<h2>${t('tierlist')}</h2><div class="ul">======</div><table>`;for(const [k,v] of Object.entries(D.tiers)){const n=D.channels.filter(c=>c.tier===k).length;h+=`<tr><td>${k[0]}</td><td class="num">${n}</td><td>${esc(v[L])}</td></tr>`}h+='</table>';document.getElementById('view').innerHTML=h}
function sources(){let h=`<h2>${t('sources')}</h2><div class="ul">=======</div><table>`;for(const s of Object.values(D.sources)){const n=D.channels.filter(c=>c.facts.some(f=>f.source===s.key)).length;h+=`<tr><td class="mute">${s.key}</td><td>${s.date}</td><td>${esc(s.publisher)}</td><td><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a></td><td class="num">${n}</td></tr>`}h+='</table>';document.getElementById('view').innerHTML=h}
function route(){if(searchController){searchController.abort();searchController=null}const hash=location.hash.replace(/^#\/?/,''),split=hash.indexOf('?'),p=split<0?hash:hash.slice(0,split),query=split<0?'':hash.slice(split+1);const m=p.match(/^c\/(.+)$/),sm=p.match(/^s\/(\d+)$/);const isHome=!p;
 document.body.classList.toggle('home',isHome);document.documentElement.lang=L;
 document.getElementById('brand').textContent=t('name');document.getElementById('menu').textContent=`[${t('directory')}]`;document.getElementById('menu').setAttribute('aria-expanded',String(document.body.classList.contains('nav-open')));
 document.title=`${t('name')}${isHome?'':' / '+(m?decodeURIComponent(m[1]):p==='search'?t('messageSearch'):p==='stories'||sm?t('stories'):p==='threads'?t('threads'):p==='tiers'?t('tiers'):p==='sources'?t('sources'):t('channels'))}`;
 if(!isHome)nav(m?decodeURIComponent(m[1]).toLowerCase():null);
 document.getElementById('hdr').textContent=`${fmt(D.channels.length)} ${t('channels')} · ${fmt(D.total)} ${t('messages')}`;
 if(isHome)home();else if(m)channel(decodeURIComponent(m[1]));else if(sm)storyView(sm[1]);else if(p==='stories')storiesView(new URLSearchParams(query));else if(p==='threads')threadsView(new URLSearchParams(query));else if(p==='search')messageSearch(new URLSearchParams(query));else if(p==='tiers')tiers();else if(p==='sources')sources();else index();window.scrollTo(0,0)}
document.getElementById('lang').onclick=()=>{L=L==='en'?'es':'en';localStorage.setItem('lang',L);document.getElementById('lang').textContent=L==='en'?'[es]':'[en]';applyTheme();route()};
document.getElementById('lang').textContent=L==='en'?'[es]':'[en]';
const th=document.getElementById('theme');let dark=(localStorage.getItem('theme')||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'))==='dark';
function applyTheme(){document.documentElement.dataset.theme=dark?'dark':'light';th.textContent=`[${t(dark?'light':'dark')}]`}applyTheme();
th.onclick=()=>{dark=!dark;localStorage.setItem('theme',dark?'dark':'light');applyTheme()};
document.getElementById('menu').onclick=()=>{const open=document.body.classList.toggle('nav-open');document.getElementById('menu').setAttribute('aria-expanded',String(open))};
window.onhashchange=()=>{document.body.classList.remove('nav-open');route()};route();
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
