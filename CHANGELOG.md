# Change log

## 2026-10-12

- Added a separate "Telegram archive / Archivo de Telegram" homepage with an ASCII archive cabinet, archive dates, message activity and counts of channels, messages, cited facts and sources. The channel browser is at `#/channels`; existing channel links remain at `#/c/<handle>`.
- Added message search at `#/search`, with word and quoted-phrase matching, case and Latin-accent handling, channel and inclusive UTC date filters, relevance/date ordering, and 25 results per page. Results show highlighted excerpts and original Telegram links. Search URLs retain filters and pagination for sharing and browser history.
- Added `search.py` for SQLite FTS5 queries and index maintenance, and `server.py` for the static site and `GET /api/search`. Insert, text-update and delete triggers maintain the index during collection. Searches use read-only connections and a three-second query limit. Starting with an existing index does not require a database write lock.
- Updated `serve.sh` to launch the archive server on the existing port. Verified the homepage and search API through the public site at https://canales.m19182.dev.
- Added normal/Takeout history-read benchmarking with configurable message counts and rounds, alternating read order, timing and message-id hashes. Initialization delays record a retry deadline and still measure normal reads. Benchmark results remain in ignored `data/`.
- Added repeated `--resolve` options to search for multiple channel names through one collector session. README examples use the existing `sync.sh` lock.
- Updated README terminology to describe the project as an archive and documented search and benchmark commands.
- Validation: 10 automated search tests passed, including index updates, pagination, filters, HTTP errors and startup during a database write lock. Python compilation and shell syntax checks passed. Browser checks covered EN/ES, desktop/mobile layouts, saved URLs, input validation, error states and safe rendering of message text.
