# External research: proposed next steps

Prepared on 14 October 2026 alongside [RESEARCH_SOURCES.md](RESEARCH_SOURCES.md). These are proposed research tasks, not changes to production collection. The source review used three subagents to check datasets, technical investigations and broader cross-platform sources.

The five pilots have now been run. [RESEARCH_PILOT_RESULTS.md](RESEARCH_PILOT_RESULTS.md) records outcomes and the narrower implementation recommendations; the plan below is retained as the original proposal.

## Recommended first task

Build a small evidence worksheet from existing archive links and published examples. Start with a bounded Pravda website sample and Spanish-language cases from VIGINUM, Overload and ATAFIMI. CheckFirst's current public JSON can help select sources and periods, but does not contain the article-level records needed for a direct message join.

Keep two relationships separate:

| Relationship | Evidence needed | Existing support |
| --- | --- | --- |
| Telegram message links to a website | URL in the archived message | `links.db` already records this |
| Website cites a Telegram channel | Source link/name on a fetched article | Requires article inspection |
| Website cites a specific Telegram message | Source URL with channel and message ID | Requires article inspection and archive lookup |
| Publications share text or media | Inspected originals and defined match rule | Text, forward fields and media IDs are available; media files are not downloaded |

These relationships do not establish affiliation, shared administration or intent. The first archived occurrence is not necessarily the original publication. The date claimed by a website is distinct from its retrieval date.

## What is already available locally

Read-only snapshot on 14 October 2026: `channels.csv` has 314 rows; `sync_state` has 314 entries with `backfill_done=1`. This collector flag does not establish complete historical coverage or current collection health.

| Exact domain | Link mentions | Distinct canonical URLs | Channel IDs | Message date endpoints, UTC |
| --- | ---: | ---: | ---: | --- |
| `spanish.news-pravda.com` | 26,915 | 25,380 | 15 | 18 November 2024 to 14 October 2026 |
| `pravda-es.com` | 19,268 | 18,548 | 22 | 4 July 2023 to 18 November 2024 |
| `spain.news-pravda.com` | 9,588 | 9,566 | 5 | 10 December 2024 to 13 October 2026 |

These counts describe rows already indexed in `links.db`, without a current-watchlist filter. A distinct canonical URL is not necessarily an article: image URLs and other resources occur. Channel counts overlap. A domain substring search is unsuitable for defining the studied network because unrelated publishers also use the word `pravda`.

The query used separately for each exact domain was:

```sql
SELECT count(*), count(DISTINCT canon), count(DISTINCT channel_id),
       min(date), max(date)
FROM links
WHERE domain = ?;
```

`links.py` stores raw URL, canonical URL, domain, message date and channel/message IDs. Its canonicalisation forces HTTPS and strips fragments, selected tracking parameters and common host prefixes. Preserve raw URLs and distinguish normalised matches from exact matches. `collect.py` stores message text, timestamps, forward provenance and media identifiers; it does not download media files. Historical posts can lack media fields.

Two archive-linked pages were fetched during this review. Both returned HTTP 200 through a direct request, though the web browsing tool could not open them. [One article](https://spanish.news-pravda.com/world/2025/04/23/409888.html) exposes an `article:published_time` value of `2025-04-23T06:40:39Z` and a source link to `t.me/Eurekapress` without a message ID. The [second page](https://spanish.news-pravda.com/spain/2025/05/22/440623.html) did not expose a Telegram URL in the simple URL scan. This is a two-page feasibility check, not an evaluated parser or coverage estimate.

## Ordered work plan

| Priority | Task | Concrete output | Completion criterion |
| --- | --- | --- | --- |
| 1 | Snapshot CheckFirst's Spain and Spanish aggregate JSON | Two local files, manifest with commit, retrieval time, URL and checksum | Parse actual schema, record truncation and licence status |
| 2 | Select 30 article URLs from existing archive links | Sample list stratified across exact domains and dates | Exclude assets/homepages; report eligibility rules and missing pages |
| 3 | Inspect source attribution on these articles | Worksheet with article URL, declared date, source URL/name, retrieval time and status | Every row reviewed; channel-only links distinguished from message links |
| 4 | Check 10–20 Spanish-relevant published evidence leads | Matched-message worksheet including zero results | Every lead records search rule, observation window and match review |
| 4 | Compare one dated Meta indicator file with archived links | Reviewed overlap rows with report/date and match type | Preserve provider comments; separate domain from exact URL matches |
| 5 | Review watchlist gaps suggested by CheckFirst | Small ranked list with discovery URLs | Verify handles, scope, duplicates/renames and subscriber counts before adding |
| 6 | Decide whether repeat collection is useful | Short pilot findings and effort estimate | Quantify usable source links, exact message matches and failure rates |

The sampling numbers are proposed bounds to keep the first task small. Suggested initial periods are the April 2025 Iberian blackout and a recent 2026 window covered by published monitoring. Report-defined cases are purposively selected and cannot estimate overall prevalence.

## Meta feasibility check

A direct read of the [September 2022 CSV](https://github.com/facebook/threat-research/blob/main/indicators/csv/2022_09_removing_coordinated_inauthentic_behavior_from_china_and_russia.csv) produced 350 rows: 313 domain rows, 22 other URL rows and 15 Telegram URL rows. There were 311 distinct domain indicators after lowercasing and converting `[.]` to `.`. The fetched bytes had SHA-256 `9f216a37e15c4772019d20ee620eafabf57a3876d4a7ab72fff5330fa8167d8d`.

Exact domain comparison against `links.db` found one matching domain, `rrn.world`, with 17 indexed link mentions, four distinct canonical URLs and eight channel IDs. Message dates range from 8 July 2022 to 27 February 2023. The other 310 distinct domains had no exact match in this check. These counts were not filtered to the current watchlist and do not include subdomains or redirects. Original URL and Telegram-URL rows were not matched.

This establishes that a small indicator comparison is feasible and that the old file has limited exact-domain overlap. It does not evaluate later files or confirm provider attribution. The next step is to review the 17 matched messages and the corresponding source rows, then assess a recent file rather than expand hostname matching indiscriminately.

## Aggregate source overlap and discovery candidates

A read-only comparison of CheckFirst's two `topSources` lists at commit `847f28d0af87d314d1d8a3d8404bde631db7f776` against the 314-row watchlist removed the `Telegram: ` prefix and matched handles case-insensitively:

| Aggregate file | Listed Telegram source strings | Watched strings | Absent strings |
| --- | ---: | ---: | ---: |
| Spain | 834 | 146 | 688 |
| Spanish | 810 | 125 | 685 |

These are source-string matches in truncated top-1,000 lists. They include non-Spanish sources and do not measure distinct live channels or archive completeness. Renames and reused handles need review. Counts supplied by CheckFirst describe website source appearances, not Telegram posting activity.

| Unverified handle | Spain aggregate count | Spanish aggregate count |
| --- | ---: | ---: |
| `HerederosDeLaTierra` | 4,807 | Not recorded here |
| `RTVideosES` | 2,239 | 10,756 |
| `PadresxlaVerdadE` | 2,143 | Not recorded here |
| `ingenieriasocialarchivo` | 1,080 | Not recorded here |
| `labanderaes` | 915 | Not recorded here |
| `locuracolectivaoficial` | 632 | Not recorded here |
| `SputnikMundoVideo` | Not recorded here | 5,242 |

No candidates were added. The next review should also compare `channels_cut.csv` and archive identities so deliberate exclusions and probable renames do not become automatic additions. A missing source string is a discovery lead, not a reason to broaden collection.

## Minimal research records

Store pilot files under ignored `data/research/`. Keep downloaded material and third-party judgments outside production message tables and public exports. A small CSV/JSONL workflow is sufficient initially.

| Record | Suggested fields |
| --- | --- |
| Source snapshot | Source key, organisation, publication URL/date, checked time, artifact URL, version/commit, checksum, access and licence status |
| Evidence lead | Source key, original URL, archive URL if available, platform, original-language phrase, declared publication time, selection reason |
| Local match | Lead ID, channel/message IDs, original Telegram URL, message UTC time, match type, forward fields, review status, coverage limitation |
| Web observation | Article URL/raw URL, retrieval time, HTTP status/final URL, declared date, source URL/name, source-link specificity, extraction method |

Use explicit match types such as exact message URL, canonical URL, exact phrase, media ID and manually reviewed similar text. An unresolved or zero-match row is a result worth keeping. Preserve reported interpretations only with source attribution in private research notes; do not turn them into channel facts in the site or dataset.

Media IDs can establish an observed Telegram identifier match when stored, but do not compare visual content across platforms. A future image/video study would require downloading a bounded media sample, documenting its selection and validating matching methods.

## Later options

Use Hamilton's search manually for original posts on other platforms, after the evidence worksheet is working. Use Meta's published indicators and Qurium reports for exact domain/URL comparisons; keep provider attribution attached to its source. Consider broadcast observations only when a specific question needs TV coverage and actual access has been checked.

Defer a broad cross-platform collector, automatic channel labels, commercial subscriptions and infrastructure enrichment until the pilot establishes a useful missing measurement. Research-source checks can initially be manual. Recurring monitoring and contact with source maintainers require a separate task; no schedules or outbound messages were created here.
