# tg-monitor

Dataset builder: full-history archive of Spanish-language pro-Kremlin Telegram channels and the
Spanish far-right accounts they overlap with, for the run-up to Spain's 29 Nov 2026 general election.

The channel list comes from published research (Maldita.es' 25 most-replicated Pravda feeders,
DFRLab's Info Defense / Surf Noise networks, EK Strategies' Ceuta analysis) plus our own additions.
Each channel carries a `tier` label so the dataset can be sliced:

| tier | meaning |
|---|---|
| A_russian_project_es | Spanish editions of multilingual Russian projects (Rybar, UKR Leaks, InfoDefense, ROKOT, DD Geopolitics) |
| B_es_aggregator | Spanish-language pro-Kremlin aggregators/originators, mostly anonymous |
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

## Layout

- `channels.csv`  watchlist: `handle,tier,since,source,note`. `since` bounds the initial backfill for huge channels.
- `collect.py`    resumable collector → `tg.db` (SQLite, WAL). First run = full history; later runs = new posts + 7-day engagement refresh. Per-channel errors are recorded in `sync_state` and never stop the run.
- `sync.sh`       the only entrypoint (cron + manual). flock-guarded, logs to `sync.log`.
- `report.py`     `daily`, `sources`, `spikes`, `grep "phrase"`.
- `export.py`     `data/<handle>.jsonl.gz` + `channels.csv` + `fwd_sources.csv` + `manifest.json`.
- `login.py`      two-step login (`send <phone>`, `code <code>`, `password`, `check`).
- `wiki.csv`, `sources.csv`  cited facts per channel for the site; neutral wording, every fact carries a source key.
- `site.py`       builds `site/index.html` (single self-contained page) from the database; `serve.sh` serves it on 127.0.0.1:8788.

Secrets/data never in git: `.env` (TG_API_ID/TG_API_HASH), `tgmon.session*`, `tg.db*`, logs, `data/`.

## Operations

```
crontab: 17 * * * * /home/mateo/projects/tg-monitor/sync.sh
./sync.sh                      # manual run (no-op if one is already running)
./sync.sh RybarESP herQles     # subset
.venv/bin/python collect.py --resolve "Eureka News"   # find a handle
sqlite3 tg.db 'select handle,last_ok,new_msgs,last_error from sync_state'   # health
```

## Schema (`messages`)

`channel_id, msg_id, date, text, views, forwards, replies, fwd_from_channel_id, fwd_from_msg_id,
fwd_from_name, fwd_date, reply_to_msg_id, media, urls(json), grouped_id, edit_date, fetched_at`.
Forward provenance (`fwd_from_*`) is what lets you reconstruct who feeds whom; `fwd_sources` resolves
those ids to names.

## Known gaps

- Telegram history reads are throttled (~1k msgs/min); a 60k-message channel takes about an hour.
- Channels with hidden history or that are private are recorded in `sync_state.last_error`.
- Media files are not downloaded, only typed (`photo/video/document/webpage`).
- Unresolved from the research lists: "Zluka de Novorusia. ZOV", "DMP Geopolítica".

## Hosting

- `serve.sh` serves `site/` on 127.0.0.1:8788 (crontab `@reboot`).
- Public via a dedicated locally-managed Cloudflare tunnel `tg-monitor` (`~/.cloudflared/tg-monitor.yml`,
  user unit `cloudflared-tg-monitor.service`): https://canales.m19182.dev and https://tg.m19182.dev.
- Gotcha: `cloudflared tunnel route dns` takes the tunnel from the default `~/.cloudflared/config.yml`
  regardless of the name argument. Always pass `--config tg-monitor.yml` (and `--overwrite-dns` to repoint).
