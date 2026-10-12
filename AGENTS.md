# AGENTS.md

Read this before touching anything in this repo.

## What this is

A research archive of ~200 public Telegram channels relevant to Spanish politics ahead of the 29 November 2026 general election: Spanish-language editions of Russian channels, Spanish aggregators that feed the Pravda network, Spain-based operators, right-wing and left-wing parties and activists, Russian and other state media, embassies, Spanish media, discussion groups. Messages go into `tg.db` (SQLite) via `collect.py`; a static site (`site.py` → `site/`) shows per-channel stats and cited facts at https://canales.m19182.dev.

Files that matter: `channels.csv` (watchlist with tiers), `wiki.csv` (one cited fact per line), `sources.csv` (every source key), `collect.py`, `site.py`, `export.py`, `join.py`, `sync.sh`. README has the tier table and operations.

## Rules

**Neutral, always.** The archive documents what channels publish and what third parties have reported about them. It does not characterise anyone. Words like propaganda, disinformation, far-right, pro-Kremlin, hoax, bulo are only allowed inside a quotation or an attribution ("Maldita.es describes X as..."), never as our own voice. Tier descriptions name a category (who runs it, what it is an edition of, where it is based), not a verdict. If a fact cannot be written neutrally and attributed, leave it out.

**Every fact needs a source key,** and the fact must be faithful to what the source actually says, including figures and dates. Separate the source's finding from the source's opinion. Record denials and contrary findings alongside accusations (e.g. EEAS "no conclusive evidence" next to a government statement).

**Do not trust any single source blindly, including fact-checkers.** Maldita.es, Newtral, EFE Verifica and similar are useful because they publish methods and data, but they are organisations with their own funding, politics and error rate, and they are frequently contested. Treat their claims as attributed claims, not ground truth: cite them as "Maldita.es reports...", prefer primary material when it exists (court notes, official reports, the channel's own posts, our own archive), and record when another source disputes them. The same applies to government bodies (DSN, EEAS, ministers), NGOs, think tanks and newspapers on every side. When two credible sources disagree, show both.

**Prefer what the data shows.** Counts, timing, forward provenance, media ids and domains from `tg.db` are facts we can stand behind. Interpretation belongs to the reader.

**No narrative in the frontend.** The site shows channels, facts, sources and numbers. No editorial text. The one exception is the `#/method` page (decided 2026-10-12): factual description of scope, collection, stories, links and limits, in EN and ES, to be reused as the dataset card. Keep it factual and update it when the pipeline changes (thresholds, models, what is stored).

**Watchlist hygiene.** Verify a handle exists before adding it (curl `https://t.me/<handle>`, check title and subscriber count). Pick the tier by what the channel is, not by what we think of it. Add a `source` saying where the handle came from. Keep `since` on huge channels.

**Operational.** One Telethon process on the file session at a time: go through `sync.sh`. `join.py` is safe alongside (in-memory session copy). Never commit `.env`, sessions, `tg.db`, logs, `site/`, `data/`. Keep the pipeline simple; resilience over features.

**Language.** Facts and notes in English; channel titles and quotations stay in the original language. UI labels exist in EN and ES in `site.py`.
