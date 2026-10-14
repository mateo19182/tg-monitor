# External research pilot results

Completed on 14 October 2026 with three subagents. This executes the five proposals in [RESEARCH_NEXT_STEPS.md](RESEARCH_NEXT_STEPS.md). Production databases were opened read-only. No channels, collectors, schedules, frontend fields or dataset fields were changed. Raw observations, provider snapshots and one-off scripts are local files under ignored `data/research/`.

## What proved useful

| Pilot | Observed result | Recommendation |
| --- | --- | --- |
| 30 archive-linked Pravda articles | All fetched; five named Telegram channels; three reviewed text correspondences with archived posts | A small on-demand article inspector is useful |
| Published Spanish-relevant cases | 14 searches covering ten Spanish-relevant topics and two supplementary topics; 17 reviewed text overlaps across four cases | Use existing search with specific published phrases and dates |
| Meta indicators | Historical file: 17 link rows, 13 distinct messages; two recent files: no exact matches | Keep as an occasional research check |
| Missing CheckFirst handles | Three of seven verified; duplication reduces the shortlist to one candidate worth scope review | Review `PadresxlaVerdadE`; defer the others |
| Hamilton and broadcast access | Five searches worked; one useful X/Telegram pair; timestamp problems in a checked record | Hamilton is useful for manual discovery; broadcast integration remains unproven |

These are feasibility observations from small selected samples. Text overlap, a linked domain and a source-channel label are different measurements. None establishes common control or intent. Image and video content was not visually compared.

## 1. Article source inspection

Selected ten URLs per exact domain, equally spaced over the archived first-link timeline. Eligible URLs had dated paths ending in numeric `.html` filenames. Assets and homepages were excluded. This is not a random sample of all articles.

All 30 returned HTTP 200 and exposed source fields and publication timestamps. Five declared Telegram channel sources, all on `pravda-es.com`; the other 25 named websites. No declared Telegram source contained a message ID. Three specific Telegram message links occurred elsewhere in article bodies, with no local message matches.

Source URLs are stored in `.article__source [data-source-url]`, rather than ordinary anchor attributes. This distinction matters: a simple `href` scan misses the declared sources and can mistake an incidental body link for attribution.

One distinctive phrase per Telegram-source article was searched in its named channel within three days of the declared page date. Three candidates were manually checked against article opening text:

| Article | Archived post | Page-declared time minus message time |
| --- | --- | ---: |
| [29 September 2023](https://pravda-es.com/world/2023/09/29/38889.html) | [wofnon/37795](https://t.me/wofnon/37795) | 630 seconds |
| [10 November 2023](https://pravda-es.com/world/2023/11/10/63949.html) | [albatrops/8623](https://t.me/albatrops/8623) | 567 seconds |
| [22 December 2023](https://pravda-es.com/world/2023/12/22/84476.html) | [ophiucu/32898](https://t.me/ophiucu/32898) | 518 seconds |

These are reviewed text correspondences with a named source channel, not direct message citations. Page dates are declarations observed at retrieval time. The two zero-result searches had coverage limits: SputnikMundo had no local messages, while the sampled tass_es article predates its archived history.

Implement only if this research repeats: an opt-in `links.py inspect` command taking selected URLs, extracting source URL/name and declared time, and writing JSONL under `data/research/`. Offer a short source-channel phrase lookup through existing FTS, preserving candidates for manual review. Store requested/final URLs, retrieval status/time and the raw source field. Keep this separate from hourly `fetch` until its utility is established on a larger targeted sample.

Local artifacts: `data/research/article-pilot/README.md`, `observations.json`, `phrase-check.json`, `sample.json`, HTML snapshots and scripts.

## 2. Published case searches

Fourteen bounded searches covered ten topics selected for Spanish relevance and two supplementary transnational examples. Inputs came from [Maldita's blackout investigation](https://maldita.es/malditobulo/20250505/articulo-suplanta-independent-matrioska-apagon/), its [April 2026 ATAFIMI report](https://files.maldita.es/uploads/2026/04/69f3651dc19d1.pdf), and original DANA and Ceuta investigations. Topic searches returned 135 candidates, not 135 case matches.

Manual review found 17 text overlaps across four reported cases:

| Reported case | Reviewed overlaps | Example archived post |
| --- | ---: | --- |
| Blackout text mentioning The Independent | 6 | [surf_noise_sp/46546](https://t.me/surf_noise_sp/46546) |
| AstraZeneca text | 3 | [ZOVNR/30458](https://t.me/ZOVNR/30458) |
| [DANA convoy caption](https://maldita.es/malditobulo/20241106/comitiva-rey-paginas-rusas-arabe/) | 3 | [Alviseperez/11353](https://t.me/Alviseperez/11353) |
| [Ceuta embassy-photo caption](https://maldita.es/desinfo/20260902/ceuta-campanas-desinformacion-injerencia-extranjera-fimi/) | 5 | [aquilavozdeeuropa/11943](https://t.me/aquilavozdeeuropa/11943) |

Six searches returned zero, and two candidates linked to publisher reviews. A broad Epstein selector returned 93 candidates that remain unresolved and are not counted as matches. Text search cannot establish that a photo or video is the same reported artifact. Searches include archived discussion messages; counts are not unique original publications. FTS normalises tokens, case and accents, so matches are not necessarily byte-identical phrases.

This needs no new collector. Use the existing archive search with a specific phrase and date range. Keep a small private CSV containing the report URL, query, original message URL, UTC date, match type, review status and coverage limit. Expand only the cases that produce inspectable matches. A broad topic-alert system would mainly add review work in this sample.

Local artifacts: `data/research/case-meta-pilot/case-results.json`, `case-review.json`, `summary.json` and provider-source snapshots.

## 3. Meta indicator overlap

Review of the [September 2022 provider file](https://github.com/facebook/threat-research/blob/main/indicators/csv/2022_09_removing_coordinated_inauthentic_behavior_from_china_and_russia.csv) confirmed that 17 `rrn.world` link rows represent 13 messages, four canonical URLs and eight currently watched channels. Four duplicate rows arise from URL variants. Preserve provider row comments and dates; this mixed-country file is not a uniform country label.

Two newer samples were checked at Meta commit `2d664e985e55fb754de7b1175f713e11f73cf8c8`:

- [H1 2026 sample](https://github.com/facebook/threat-research/blob/2d664e985e55fb754de7b1175f713e11f73cf8c8/indicators/meta-h1-2026-russia-based-cib-network-1.md): five URL indicators, zero exact canonical matches. Its stated scope is Sub-Saharan Africa, so the scope fit is limited.
- [H2 2026 Western-audiences sample](https://github.com/facebook/threat-research/blob/2d664e985e55fb754de7b1175f713e11f73cf8c8/indicators/meta-h2-2026-russia-cib-based-network-2.md): twenty domain/account indicators, zero exact matches. The named Telegram handle also had no reference matches. The full-report link is `TBD`, and H2 is not a completed reporting period at this check.

Checks reused `links.canonical`. Mentions of ordinary publisher or petition domains were kept separate from exact URL matches. Deduplicate output by channel/message ID, not URL row. Do not interpret zero overlap as absence of related content.

No scheduled import is warranted by these results. If repeated checks become useful, add one read-only command accepting a provider file and emitting matched messages plus unmatched indicators. Exact URL, exact domain and Telegram-handle matches must stay separate. Preserve the provider snapshot rather than turn its assessments into archive labels.

Local artifacts: `data/research/case-meta-pilot/rrn-review.json`, `meta-recent-results.json`, `meta-h2-recent-results.json` and `manifest.json`.

## 4. Channel discovery

Landing pages and recent public posts were checked for seven source strings absent from the watchlist, cut list and current archived usernames. Three exposed live titles and subscriber counts:

| Handle | Title observed | Subscribers | Recommendation |
| --- | --- | ---: | --- |
| [PadresxlaVerdadE](https://t.me/PadresxlaVerdadE) | Padres Por la Verdad España II. | 6,428 | Worth scope review; sampled posts include the November election |
| [locuracolectivaoficial](https://t.me/locuracolectivaoficial) | Locura Colectiva Oficial | 682 | Defer because sampled forwards overlap existing coverage |
| [ingenieriasocialarchivo](https://t.me/ingenieriasocialarchivo) | Ingeniería Social y Agenda 2030 | 7,877 | Lower priority after inspecting recent material |

Ten of twenty sampled Locura posts forwarded from already-watched `ellocodelacorralachannel`; all ten referenced source messages exist locally. Nine of fifteen text-bearing posts were among those forwards. That lowers the observed benefit of collecting it unless destination-level forwarding is itself the research question.

HerederosDeLaTierra, RTVideosES, labanderaes and SputnikMundoVideo returned generic pages without title/subscriber validation. `labanderaes` also occurs as an X handle; do not assume a Telegram rename from a source string. The archive contains `labanderadiario`, titled LaBandera; its relationship to `labanderaes` remains unverified.

Recommend reviewing only PadresxlaVerdadE for addition now. If selected, use an existing descriptive tier, the pinned CheckFirst discovery URL in `source`, a neutral note and a bounded initial history. No row was added during this pilot.

Local artifacts: `data/research/discovery-crossplatform/handles.json`, `recent-posts.json` and `locura-forward-review.json`.

## 5. Hamilton and broadcast discovery

Five [Hamilton searches](https://securingdemocracy.org/social-data-search/) succeeded: Spain/blackout, Valencia/floods, Spain/NATO, an exact phrase and Independent/blackout. Sampling at most ten results per query produced 42 distinct original post URLs across seven platforms. Provider totals were search counts, not reviewed relevant-case counts.

The exact phrase query found provider-preserved Spanish text in [an X post](https://twitter.com/i/web/status/1917326796028064051) and [Telegram message 14233](https://t.me/cristinamartinjimenezescritora/14233). That Telegram message exists locally. The X original was inaccessible, so its text is provider-preserved evidence.

Hamilton gives the Telegram post `2025-04-30T02:31:24Z`; both the archive and fetched Telegram embed give `2025-04-30T06:31:24Z`. The four-hour discrepancy means publication lags must use verified original timestamps. Sampled X records also supplied midnight dates rather than verified exact times. The public frontend's observed REST endpoint worked, but uses a temporary nonce and is not a documented supported bulk API.

Keep Hamilton as a manual search aid. Save selected original URLs and original-language text, with provider dates separate from independently checked dates. The optional export helper can wait until repeated use justifies maintenance.

A [GDELT request for the blackout date](https://api.gdeltproject.org/api/v2/tvv/tvv?chans=RT&date=20250428) returned HTTP 200 but only a client-rendered shell. No broadcast or transcript was inspected. Broadcast integration is not yet justified.

Local artifacts: `data/research/discovery-crossplatform/findings.md`, `hamilton-searches.json`, `hamilton-local-matches.json`, `verified-message.html` and `broadcast-check.json`.

## Proposed project work

1. Use existing search and a private evidence worksheet immediately. This was the most productive part of the pilot and requires no production changes.
2. If article comparisons will be repeated, implement the small opt-in `links.py inspect` command. Reuse FTS and canonicalisation; keep results in ignored research files.
3. Review PadresxlaVerdadE for a watchlist addition with a bounded backfill. Defer the other sampled candidates.
4. Keep Hamilton and Meta comparisons on demand. No recurring imports, broad cross-platform collector or broadcast system are supported by the measured benefit so far.
