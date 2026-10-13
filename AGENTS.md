# AGENTS.md

Read this before touching anything in this repo.

## What this is

A research archive of ~200 public Telegram channels relevant to Spanish politics ahead of the 29 November 2026 general election: Spanish-language editions of Russian channels, Spanish aggregators that feed the Pravda network, Spain-based operators, right-wing and left-wing parties and activists, Russian and other state media, embassies, Spanish media, discussion groups. Messages go into `tg.db` (SQLite) via `collect.py`; a static site (`site.py` → `site/`) shows per-channel stats and stories at https://canales.m19182.dev.

Files that matter: `channels.csv` (watchlist with tiers), `collect.py`, `site.py`, `export.py`, `join.py`, `sync.sh`. README has the tier table and operations.

## Rules

**Neutral, always.** The archive documents what channels publish. It does not characterise anyone. Words like propaganda, disinformation, far-right, pro-Kremlin, hoax, bulo never appear in our own voice. Tier descriptions name a category (who runs it, what it is an edition of, where it is based), not a verdict.

**Prefer what the data shows.** Counts, timing, forward provenance, media ids and domains from `tg.db` are facts we can stand behind. Interpretation belongs to the reader.

**No narrative in the frontend.** The site shows channels, numbers and stories. The `#/method` page (decided 2026-10-12) is a terse technical spec (collection, stories, links, limits) in EN and ES, mirrored in `dataset_card.md`; update both when thresholds, models or stored fields change.

**No statements about channels (decided 2026-10-13).** The site and the dataset carry no facts, research findings or third-party claims about channels: only what the channels publish, what the data shows, and where each handle was listed from (`channels.csv` `source`). Tier descriptions say what a channel is, without citing anyone.

**Watchlist hygiene.** Verify a handle exists before adding it (curl `https://t.me/<handle>`, check title and subscriber count). Pick the tier by what the channel is, not by what we think of it. Add a `source` saying where the handle came from. Keep `since` on huge channels.

**Operational.** One Telethon process on the file session at a time: go through `sync.sh`. `join.py` is safe alongside (in-memory session copy). Never commit `.env`, sessions, `tg.db`, logs, `site/`, `data/`. Keep the pipeline simple; resilience over features.

**Language.** Notes in English; channel titles and quotations stay in the original language. UI labels exist in EN and ES in `site.py`.
