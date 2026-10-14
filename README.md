# tg-monitor

A research archive of public Telegram channels relevant to Spanish politics. The site shows
archived messages, channel statistics and weekly stories.

Project changes are recorded in [CHANGELOG.md](CHANGELOG.md).
External research leads and tool assessments are recorded in [RESEARCH_SOURCES.md](RESEARCH_SOURCES.md), with proposed pilots in [RESEARCH_NEXT_STEPS.md](RESEARCH_NEXT_STEPS.md).

The channel list comes from published research (Maldita.es' 25 most-replicated Pravda feeders,
DFRLab's Info Defense / Surf Noise networks, EK Strategies' Ceuta analysis) plus our own additions.
Each channel carries a `tier` label so the dataset can be sliced:

| tier | meaning |
|---|---|
| A_russian_project_es | Spanish editions of multilingual Russian projects (Rybar, UKR Leaks, InfoDefense, ROKOT, DD Geopolitics) |
| B_es_aggregator | Spanish-language channels listed as frequent sources of the Pravda network's Spanish pages |
| C_spain_node | Channels run from inside Spain (Herqles, Eureka News, TSA Noticias...) |
| D_spain_farright_election | Spanish right-wing and nationalist parties, organisations and activists (Vox, SALF, Falange, DN, Hazte Oír...) |
| E_russian_parent | Russian/English parent channels, for translation-lag and provenance (limited `since`) |
| F_russian_official | Embassies, MFA, TASS and state-media mirrors |
| G_allied_state_media_es | Allied state media in Spanish (Iran, Syria, Venezuela, Cuba) |
| H_discovered_es_aggregator | Spanish-language channels surfaced by forward provenance, not in any published list |
| I_discussion_group | Linked discussion groups of watched channels (audience comments; `sender_id` set; since 2025) |
| J_spain_parties | Parliamentary Spanish parties and leaders (control) |
| K_spain_left | Spanish left-wing, anti-NATO and solidarity organisations and media |
| L_spain_media | Spanish media outlets and commentators |
| M_public_channels | Public channels of individual authors, associations and community publishers |
| N_spain_institution | Spanish state institutions |
| O_factchecker | Fact-checking organisations |
| P_regional_politics | Regional and nationalist parties, organisations and media |
| Q_mobilisation | Unions, housing, civic, professional and diaspora organisations |
| R_conspiracy_pivot | Channels documented by Maldita.es (2022) as moving from COVID-19 content to the war in Ukraine |
| S_influencer | Individual commentators and streamers |
| T_counterpart | Ukrainian, EU, Israeli and Moroccan official or aligned channels |
| U_campaign_2026 | Candidates, party branches and youth wings around the 29N election |
| V_civil_society | Civil-society organisations across the spectrum |
| W_journalist | Journalists' and commentators' channels |
| X_diaspora | Diaspora and migrant-community channels in Spain |
| Y_local | Local news, incident and neighbourhood channels |
| Z_meme_finance | Political humour, libertarian, crypto and prepper channels |

## Layout

- `channels.csv`  watchlist: `handle,tier,since,source,note`. `since` bounds the initial backfill for huge channels.
- `channels_cut.csv`  channels removed from the watchlist on 2026-10-12 to keep the focus on politics and disinformation (same columns plus `cut_reason`); move a row back to `channels.csv` to collect it again.
- `collect.py`    resumable collector → `tg.db` (SQLite, WAL). First run = full history; later runs = new posts + 7-day engagement refresh. Per-channel errors are recorded in `sync_state` and never stop the run.
- `benchmark.py`  compares normal and Takeout history reads and records timing, message-id hashes and any initialization delay or retry deadline in `data/takeout-benchmark.json`.
- `sync.sh`       the only entrypoint (cron + manual). flock-guarded, logs to `sync.log`.
- `report.py`     `daily`, `sources`, `spikes`, `grep "phrase"`.
- `export.py`     `data/<handle>.jsonl.gz` + `channels.csv` + `fwd_sources.csv` + `manifest.json`, plus `stories.jsonl.gz` and `arenas.csv` when the story layer exists.
- `login.py`      two-step login (`send <phone>`, `code <code>`, `password`, `check`).
- `site.py`       builds `site/index.html` from the database: about page at `#/`, channel browser at `#/channels` (tiers grouped into seven groups, `GROUPS` in site.py), channel pages at `#/c/<handle>`, stories at `#/stories` (by week, and over time with `?view=time`), story pages at `#/s/<id>`, message search at `#/search`.
- `embed.py`      embeds message texts (≥40 chars after stripping URLs and share footers) with bge-m3 on the GPU into `vec.db`; one vector per distinct text.
- `stories.py`    groups one week's posts (or discussion-group comments) into stories by similarity, chains them to the previous week's stories, and labels each story through the Message Batches API with a neutral title, a one-line summary and one to three arenas from `arenas.csv`. Spend is tracked in `data/label_ledger.json` and capped with `--cap`.
- `arenas.csv`    two fixed axes with EN/ES names and definitions: 10 regions (where a story happens) and 14 themes (what it is about), plus two buckets (housekeeping, reactions). Each story gets one region and one or two themes. Stories carry their own open labels; the model may propose new themes (`stories.py --proposals`), which are added here by hand.
- `links.py`      links archive in `links.db`: every URL in archived messages with canonical form, domain and kind (telegram, social, shortener, content); shortener targets (`resolve`), page titles and descriptions for content URLs (`fetch`, 1 request/s per domain), and the t.me reference graph as a discovery feed (`tme`: handles referenced by watched channels but not on the watchlist). `index` and `summary` (writes `site/links.json` for the `#/links` page) run hourly from `sync.sh`.
- `search.py`     SQLite FTS5 index and search queries. Insert, text-update and delete triggers keep the index current during collection.
- `server.py`     serves `site/` and `GET /api/search` on the same origin; `serve.sh` starts it on 127.0.0.1:8788.

Secrets/data never in git: `.env` (TG_API_ID/TG_API_HASH, ANTHROPIC_API_KEY), `tgmon.session*`, `tg.db*`, `vec.db*`, `links.db*`, logs, `data/`.

Stories:
```
.venv/bin/python embed.py --since 2026-09-28            # embed new texts (hourly runs embed increments)
.venv/bin/python stories.py --week 2026-W41             # cluster that week's posts into stories
.venv/bin/python stories.py --week 2026-W41 --label     # label unlabelled stories (batch, cached system prompt)
.venv/bin/python stories.py --week 2026-W41 --show --full
.venv/bin/python stories.py --week 2026-W41 --kind comment   # same for discussion-group comments
```
`stories.sh` runs this for the previous week every Monday at 05:00 (cron). Discussion-group comments are excluded from embedding and stories for now (`embed.py --comments` to include them).
A story is a group of similar posts within one ISO week; members far from the group's centre are left unassigned. Channel promotion (subscribe calls, livestream alerts, catalogues) is labelled with the `housekeeping` bucket and excluded from story counts. `=id` marks the same story continued from the previous week (centroid cosine ≥ 0.90), `~id` a related story (0.85–0.90). About a quarter of posts stay unassigned.

## Dataset release

`release.py build` writes `data/release/` (Parquet + README card from `dataset_card.md`); `release.py upload` pushes it to https://huggingface.co/datasets/mateo-19182/spanish-politics-telegram (private + gated; `--public` makes it visible, downloads stay gated). Needs `HF_TOKEN` in `.env`; `HF_SALT` is generated on first build and keeps sender pseudonyms stable across releases. Never publish the salt.

## Operations

```
crontab: 17 * * * * /path/to/tg-monitor/sync.sh
./sync.sh                      # manual run (no-op if one is already running)
./sync.sh RybarESP herQles     # subset
./sync.sh --benchmark-takeout RybarESP infodefSPAIN  # compare history reads without archive writes
./sync.sh --resolve "Eureka News" --resolve "Rybar"   # find handles; repeat --resolve for multiple names
sqlite3 tg.db 'select handle,last_ok,new_msgs,last_error from sync_state'   # health
.venv/bin/python -m unittest -v test_search
.venv/bin/python search.py --index --rebuild  # repair the search index if message rows were rewritten
```

## Message search

The server initialises the full-text index on its first start. Searches read the database through
a read-only connection and include only channels in `channels.csv`. Words are combined with AND;
double quotes search a phrase. Matching ignores case and Latin accents. Results contain excerpts
with marked matches, channel names, UTC dates, and links to the original Telegram messages.

`GET /api/search?q=texto&channel=handle&from=2026-01-01&to=2026-10-12&sort=newest&page=1`

Only `q` is required. Dates include both endpoints in UTC. `sort` is `relevance` by default,
or `newest` or `oldest`. Pages contain up to 25 results. Search text is limited to 300 characters
and 20 words or quoted phrases. Responses return `total`, `page`, `page_size`, `has_next`, and
`results`; invalid parameters return HTTP 400 with an error code. Queries have a three-second
execution limit. Search parameters live in the page URL so searches can be bookmarked or shared.

The HTTP and page code use the search request/result contract; SQLite queries and index maintenance
live in `search.py`. A later database migration can replace that implementation.

## Schema (`messages`)

`channel_id, msg_id, date, text, views, forwards, replies, fwd_from_channel_id, fwd_from_msg_id,
fwd_from_name, fwd_date, reply_to_msg_id, media, urls(json), grouped_id, edit_date, fetched_at`.
Forward provenance (`fwd_from_*`) is what lets you reconstruct who feeds whom; `fwd_sources` resolves
those ids to names.

## Known gaps

- The 12 October 2026 paired benchmark measured about 6,300 messages/minute with normal pacing and 16,500 with Takeout. These were short history reads, not sustained collection with database writes. See `./sync.sh --benchmark-takeout`; raw results stay in ignored `data/takeout-benchmark.json`.
- Channels with hidden history or that are private are recorded in `sync_state.last_error`.
- Media files are not downloaded, only typed (`photo/video/document/webpage`).
- `maldita-coverage.csv` records matches and unresolved identities for the 39-channel December 2022 and 25-channel July 2025 samples. Six entries are unavailable, unresolved or awaiting access approval; one existing channel is a probable renamed match. `ZOVNR` is already included. "DMP Geopolítica" remains unresolved in other consulted research.

## Hosting

- `serve.sh` serves `site/` and message search on 127.0.0.1:8788 (crontab `@reboot`).
- Public via a dedicated locally-managed Cloudflare tunnel `tg-monitor` (`~/.cloudflared/tg-monitor.yml`,
  user unit `cloudflared-tg-monitor.service`): https://canales.m19182.dev and https://tg.m19182.dev.
- Gotcha: `cloudflared tunnel route dns` takes the tunnel from the default `~/.cloudflared/config.yml`
  regardless of the name argument. Always pass `--config tg-monitor.yml` (and `--overwrite-dns` to repoint).

## Licence

Code: MIT (`LICENSE`). Dataset: CC BY-NC 4.0 (see `dataset_card.md`).
