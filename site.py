#!/usr/bin/env python3
"""Build site/index.html: a single self-contained page (data embedded) from tg.db + channels.csv + wiki.csv.

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
    "D_spain_farright_election": {"en": "Spanish political parties, candidates and activists", "es": "Partidos, candidatos y activistas políticos españoles"},
    "E_russian_parent": {"en": "Russian- or English-language channels of which tier A channels are editions (partial archive)", "es": "Canales en ruso o inglés de los que los canales del nivel A son ediciones (archivo parcial)"},
    "F_russian_official": {"en": "Russian state institutions and state media", "es": "Instituciones y medios estatales rusos"},
    "G_allied_state_media_es": {"en": "Spanish-language state media of other countries (partial archive)", "es": "Medios estatales en español de otros países (archivo parcial)"},
    "H_discovered_es_aggregator": {"en": "Channels not named in the consulted research; included because tracked channels forward them", "es": "Canales no citados en las investigaciones consultadas; incluidos porque los canales seguidos los reenvían"},
    "I_discussion_group": {"en": "Discussion groups linked to tracked channels (from 2025)", "es": "Grupos de debate vinculados a canales seguidos (desde 2025)"},
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
        "tiers": TIERS, "sources": sources, "channels": out,
    }


HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>channel index</title>
<style>
:root{--bg:#f7f7f4;--fg:#1a1a1a;--mute:#6b6b66;--line:#d8d8d2;--dot:#cfcfc8;--acc:#1a1a1a;--bar:#1a1a1a}
:root:not([data-theme="light"]){ @media (prefers-color-scheme: dark){ --bg:#0f0f0e;--fg:#e6e6e0;--mute:#8a8a84;--line:#2a2a28;--dot:#2a2a28;--acc:#e6e6e0;--bar:#e6e6e0 } }
:root[data-theme="dark"]{--bg:#0f0f0e;--fg:#e6e6e0;--mute:#8a8a84;--line:#2a2a28;--dot:#2a2a28;--acc:#e6e6e0;--bar:#e6e6e0}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--fg)}
body{font:14px/1.5 ui-monospace,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace;
 background-image:radial-gradient(var(--dot) .8px,transparent .9px);background-size:14px 14px;min-height:100vh}
a{color:var(--fg);text-decoration:none}a:hover{text-decoration:underline}
.wrap{max-width:1180px;margin:0 auto;padding:16px}
header{display:flex;flex-wrap:wrap;gap:8px 20px;align-items:baseline;border-bottom:1px solid var(--line);padding-bottom:10px;margin-bottom:18px}
header h1{font-size:14px;margin:0;font-weight:700}
header .r{margin-left:auto;display:flex;gap:14px}
.btn{cursor:pointer;color:var(--mute)}.btn:hover{color:var(--fg)}
main{display:grid;grid-template-columns:220px 1fr;gap:28px}
nav{position:sticky;top:12px;align-self:start;max-height:calc(100vh - 24px);overflow:auto;font-size:13px}
nav h3{margin:14px 0 4px;font-size:12px;color:var(--mute);font-weight:400}
nav ul{list-style:none;margin:0;padding:0}nav li{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
nav li a{color:var(--fg)}nav li.cur a{text-decoration:underline}
h2{font-size:14px;margin:0 0 2px;font-weight:700}
.ul{color:var(--mute);margin-bottom:14px}
table{border-collapse:collapse;width:100%;font-size:13px}
th,td{text-align:left;padding:3px 10px 3px 0;vertical-align:top;border-bottom:1px solid var(--line)}
td.nw{white-space:nowrap}table.list{width:auto}table.list td{padding-right:16px}
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
@media(max-width:760px){main{grid-template-columns:1fr}nav{position:static;max-height:none}}
</style>
</head>
<body>
<div class="wrap">
<header>
 <h1><a href="#/">channel index</a></h1>
 <span class="mute" id="hdr"></span>
 <span class="r"><span class="btn" id="lang">[es]</span><span class="btn" id="theme">[dark]</span></span>
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
  tierlist:'tiers',built:'built',since:'archived from',nofacts:'no published research recorded for this channel.',group:'discussion group'},
 es:{channels:'canales',messages:'mensajes',archive:'archivo',tiers:'niveles',sources:'fuentes',handle:'usuario',title:'título',tier:'nivel',subs:'suscriptores',posts:'publicaciones',last:'última publicación',days:'últimos %d días',search:'buscar /',
  about:'descripción (tal como la publica el canal)',facts:'investigaciones publicadas',stats:'archivo',created:'canal creado',first:'primera publicación archivada',views:'visualizaciones totales',fwd:'publicaciones que son reenvíos',senders:'remitentes distintos',
  fwdfrom:'más reenviado desde',fwdto:'reenviado por canales seguidos',domains:'dominios más enlazados',none:'ninguno',notyet:'aún no archivado',perday:'publicaciones por día',tracked:'seguido',untracked:'no seguido',
  tierlist:'niveles',built:'generado',since:'archivado desde',nofacts:'no hay investigaciones publicadas registradas para este canal.',group:'grupo de debate'}};
let L=localStorage.getItem('lang')||'en';
const t=k=>T[L][k]||k;
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const fmt=n=>n==null?'—':Number(n).toLocaleString(L==='es'?'es-ES':'en-GB');
const BL='▁▂▃▄▅▆▇█';
function spark(a,n=60){const off=a.length-n;a=a.slice(off);const m=Math.max(1,...a);const s=new Date(D.start);s.setDate(s.getDate()+off);return '<span class="spark">'+a.map((v,i)=>{const d=new Date(s);d.setDate(d.getDate()+i);return `<span title="${d.toISOString().slice(0,10)}: ${v}">${v?BL[Math.min(7,Math.floor(v/m*7.99))]:'·'}</span>`}).join('')+'</span>'}
function bar(n,max,w=24){return '<span class="bar">'+'█'.repeat(Math.max(1,Math.round(n/max*w)))+'</span>'}
function link(c){return c.handle?`<a href="https://t.me/${esc(c.handle)}" target="_blank" rel="noopener">@${esc(c.handle)}</a>`:`<span class="mute">id ${c.id}</span>`}
function chanLink(c){return c.tracked?`<a href="#/c/${esc(c.handle||c.id)}">${esc(c.title||c.handle||c.id)}</a>`:esc(c.title||c.handle||('id '+c.id))}
function nav(cur){const byT={};D.channels.forEach(c=>(byT[c.tier]=byT[c.tier]||[]).push(c));
 let h=`<input class="search" id="q" placeholder="${t('search')}"><ul><li><a href="#/">${t('channels')}</a></li><li><a href="#/tiers">${t('tiers')}</a></li><li><a href="#/sources">${t('sources')}</a></li></ul>`;
 for(const k of Object.keys(D.tiers)){if(!byT[k])continue;h+=`<h3>${k.slice(0,1)} · ${byT[k].length}</h3><ul>`+byT[k].map(c=>`<li class="${cur===c.handle.toLowerCase()?'cur':''}"><a href="#/c/${esc(c.handle)}">${esc(c.title||c.handle)}</a></li>`).join('')+'</ul>'}
 document.getElementById('nav').innerHTML=h;
 const q=document.getElementById('q');q.oninput=()=>{const v=q.value.toLowerCase();document.querySelectorAll('#nav li').forEach(li=>{li.style.display=li.textContent.toLowerCase().includes(v)?'':'none'})};
 document.onkeydown=e=>{if(e.key==='/'&&document.activeElement!==q){e.preventDefault();q.focus()}}}
let sortKey='tier',sortDir=1;
function index(){const rows=[...D.channels].sort((a,b)=>{const x=a[sortKey],y=b[sortKey];return (x==null)-(y==null)||(x>y?1:x<y?-1:0)*sortDir||a.handle.localeCompare(b.handle)});
 const th=(k,l,cls='')=>`<th class="${cls}" data-k="${k}">${l}${sortKey===k?(sortDir>0?' ▴':' ▾'):''}</th>`;
 let h=`<p class="big">${fmt(D.channels.length)} ${t('channels')} · ${fmt(D.total)} ${t('messages')}</p><div class="ul">${t('archive')} ${D.range[0]} → ${D.range[1]} · ${t('built')} ${D.built}</div>`;
 h+=`<table><tr>${th('tier',t('tier'))}${th('title',t('title'))}${th('subs',t('subs'),'num')}${th('n',t('posts'),'num')}${th('last',t('last'))}<th>${t('days').replace('%d',60)}</th></tr>`;
 for(const c of rows)h+=`<tr><td class="mute">${c.tier[0]}</td><td><a href="#/c/${esc(c.handle)}">${esc(c.title||c.handle)}</a> <span class="mute">@${esc(c.handle)}</span></td><td class="num">${fmt(c.subs)}</td><td class="num">${c.n?fmt(c.n):'<span class="mute">—</span>'}</td><td class="nw">${c.last||'<span class="mute">'+t('notyet')+'</span>'}</td><td>${spark(c.daily)}</td></tr>`;
 h+='</table>';document.getElementById('view').innerHTML=h;
 document.querySelectorAll('th[data-k]').forEach(e=>e.onclick=()=>{const k=e.dataset.k;if(sortKey===k)sortDir=-sortDir;else{sortKey=k;sortDir=1}index()})}
function chart(a){const H=8,W=a.length,m=Math.max(1,...a);const rows=[];for(let r=H;r>=1;r--){let s=String(Math.round(m*r/H)).padStart(6)+' ┤';for(let i=0;i<W;i++){const v=a[i]/m*H;s+=v>=r?'█':v>=r-.5?'▄':' '}rows.push(s)}
 rows.push('       └'+'─'.repeat(W));const s=D.start,lab=[];for(let i=0;i<W;i+=30){const d=new Date(s);d.setDate(d.getDate()+i);lab.push(d.toISOString().slice(5,10).padEnd(30))}rows.push('        '+lab.join(''));return `<div class="chart">${rows.map(r=>esc(r)).join('\n')}</div>`}
function channel(handle){const c=D.channels.find(x=>x.handle.toLowerCase()===handle.toLowerCase());if(!c){document.getElementById('view').innerHTML='?';return}
 let h=`<h2>${esc(c.title||c.handle)}</h2><div class="ul">${'='.repeat(Math.min(60,(c.title||c.handle).length))}</div>`;
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
 if(c.n)h+=`<div class="mute">${t('perday')} · ${t('days').replace('%d',D.days)}</div>`+chart(c.daily);
 h+='</section>';
 const list=(title,items,f)=>{h+=`<section><h2>${title}</h2>`;if(!items.length){h+=`<p class="mute">${t('none')}</p></section>`;return}const m=items[0].n;h+='<table class="list">'+items.map(i=>`<tr><td class="num">${fmt(i.n)}</td><td>${bar(i.n,m)}</td><td>${f(i)}</td></tr>`).join('')+'</table></section>'};
 list(t('fwdfrom'),c.fwd_from,i=>`${chanLink(i)} ${i.handle?`<span class="mute">@${esc(i.handle)}</span>`:''}${i.tracked?'':' <span class="mute">·</span>'}`);
 list(t('fwdto'),c.fwd_to,i=>chanLink(i));
 list(t('domains'),c.domains.map(([d,n])=>({d,n})),i=>esc(i.d));
 document.getElementById('view').innerHTML=h}
function tiers(){let h=`<h2>${t('tierlist')}</h2><div class="ul">======</div><table>`;for(const [k,v] of Object.entries(D.tiers)){const n=D.channels.filter(c=>c.tier===k).length;h+=`<tr><td>${k[0]}</td><td class="num">${n}</td><td>${esc(v[L])}</td></tr>`}h+='</table>';document.getElementById('view').innerHTML=h}
function sources(){let h=`<h2>${t('sources')}</h2><div class="ul">=======</div><table>`;for(const s of Object.values(D.sources)){const n=D.channels.filter(c=>c.facts.some(f=>f.source===s.key)).length;h+=`<tr><td class="mute">${s.key}</td><td>${s.date}</td><td>${esc(s.publisher)}</td><td><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a></td><td class="num">${n}</td></tr>`}h+='</table>';document.getElementById('view').innerHTML=h}
function route(){const p=location.hash.replace(/^#\/?/,'');const m=p.match(/^c\/(.+)$/);nav(m?decodeURIComponent(m[1]).toLowerCase():null);
 document.getElementById('hdr').textContent=`${fmt(D.channels.length)} ${t('channels')} · ${fmt(D.total)} ${t('messages')}`;
 if(m)channel(decodeURIComponent(m[1]));else if(p==='tiers')tiers();else if(p==='sources')sources();else index();window.scrollTo(0,0)}
document.getElementById('lang').onclick=()=>{L=L==='en'?'es':'en';localStorage.setItem('lang',L);document.getElementById('lang').textContent=L==='en'?'[es]':'[en]';route()};
document.getElementById('lang').textContent=L==='en'?'[es]':'[en]';
const th=document.getElementById('theme');let dark=(localStorage.getItem('theme')||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'))==='dark';
function applyTheme(){document.documentElement.dataset.theme=dark?'dark':'light';th.textContent=dark?'[light]':'[dark]'}applyTheme();
th.onclick=()=>{dark=!dark;localStorage.setItem('theme',dark?'dark':'light');applyTheme()};
window.onhashchange=route;route();
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
