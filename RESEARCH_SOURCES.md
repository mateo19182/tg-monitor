# Research sources and tools

This register covers external research on Russian political messaging and publishing across media. Checked on 14 October 2026 through primary publications, public repository files and small read-only checks. It is a selective source review, not a complete inventory. External interpretations remain attributed to their authors. Proposed work is detailed in [RESEARCH_NEXT_STEPS.md](RESEARCH_NEXT_STEPS.md).

## Antibot4Navalny and Metabot

Reviewed on 14 October 2026. These are sources of research leads for manual verification, not inputs to channel classification or archive labels.

- [Antibot4Navalny on X](https://x.com/antibot4navalny) can provide original post links, phrases, domains and dates to look for in the archive. The timeline could not be read directly during this review; the assessment uses public repository files and the investigations below.
- [Metabot](https://github.com/antibot4navalny/metabot) is a browser extension for X/Twitter. Its code matches account usernames against supplied label lists and highlights posts. It does not collect Telegram messages or independently detect coordinated activity. It may help manual browsing of X, but is not recommended for integration into the collection pipeline.
- [accounts_labelled](https://github.com/antibot4navalny/accounts_labelled) contains public JSON account-label lists. The inspected main file contains 1,984 keys, including numeric IDs and usernames; this is not a unique-account count. The inspected files do not supply message-level evidence for each label. They are a possible reference for a separate X study, not Telegram annotations.

There is a concrete Spanish-language research connection. [EFE Verifica's 2 May 2025 investigation](https://verifica.efe.com/apagon-espana-portugal-campana-prorrusa-desinformacion/) credits the group with identifying posts using The Independent and France 24 branding during the April 2025 Iberian blackout. EFE examined related publications on Telegram, X and other platforms. [Maldita's 5 May 2025 investigation](https://maldita.es/malditobulo/20250505/articulo-suplanta-independent-matrioska-apagon/) also cites the group and describes publication across Telegram, X and Bluesky and subsequent reproduction in larger Telegram channels and Pravda pages. These reports supply cases to inspect; their interpretations are not archive findings.

Use specific original message links, exact phrases, domains and timestamps as search leads in `tg.db`. Describe matches through archived text, observed timing, links and recorded forward provenance. The earliest archived occurrence is not necessarily the original publication. For any newly discovered channel, verify its public handle, choose the tier by what it is and record the specific discovery URL in `channels.csv`'s `source` field. External account labels and interpretations do not enter the frontend or dataset.

GitHub repository metadata checked during the review reports Metabot last pushed on 20 May 2024 and accounts_labelled on 10 October 2026. This distinguishes repository activity from extension compatibility or label accuracy. Neither repository exposed an explicit licence in the inspected tree or GitHub licence metadata; check reuse terms before redistributing their code or lists.

## Public data and search tools

### CheckFirst and DFRLab: Pravda dashboard

Links: [project description](https://checkfirst.network/project/pravda-dashboard/), [dashboard](https://portal-kombat.com/), [repository](https://github.com/CheckFirstHQ/pravda-network), [inspected JSON directory](https://github.com/CheckFirstHQ/pravda-network/tree/847f28d0af87d314d1d8a3d8404bde631db7f776/json).

The current repository contains 101 aggregate dashboard JSON files. Its README describes compressed article-level CSVs under `data/`, but that directory is absent from the inspected root. The project advertises hourly updates; GitHub's latest inspected commit was `847f28d0af87d314d1d8a3d8404bde631db7f776`, dated 14 October 2026 at 10:23:52 UTC.

The two inspected files expose `domain`, `totalArticles`, `articlesPerDay`, `topSources`, `categories`, `publicationHours`, `sourcesByDay`, `topSourceNames`, language summaries and domain inventories. Their `topSources` lists have 1,000 entries each; `sourcesByDay` covers ten named sources. They do not expose individual article or Telegram message URLs.

| File | Recorded articles | Daily series endpoints |
| --- | ---: | --- |
| [Spain](https://raw.githubusercontent.com/CheckFirstHQ/pravda-network/847f28d0af87d314d1d8a3d8404bde631db7f776/json/spain.news-pravda.com_viz.json) | 104,473 | 8 November 2024 to 14 October 2026 |
| [Spanish](https://raw.githubusercontent.com/CheckFirstHQ/pravda-network/847f28d0af87d314d1d8a3d8404bde631db7f776/json/spanish.news-pravda.com_viz.json) | 647,509 | 4 July 2023 to 14 October 2026 |

These are provider-recorded website counts, not our archive counts. The README requests attribution and research/analysis use; no explicit standard redistribution licence was located. Use the aggregates for discovery and comparison. Article/message matching requires a separate page-level sample or access to raw records.

### Hamilton 2.0 and Social Data Search

Links: [dashboard](https://securingdemocracy.org/hamilton-dashboard/), [methodology](https://securingdemocracy.org/hamilton-2-0-methodology-faqs/), [search](https://securingdemocracy.org/social-data-search/).

Coverage includes selected government and media accounts on X, Telegram, YouTube, Facebook, Instagram and TikTok, websites and ministry statements. The landing page specifies a 30-day dashboard window and two years in the companion search; older data up to five years requires contacting maintainers. Methodology describes daily refresh and monthly account-list reviews, but a live refresh timestamp was not verified.

Search supports phrases, Boolean operators and wildcards. Displayed posts are translated into English; original text is available through details. This can help find cross-platform occurrences of a phrase or event, but translation and selected coverage affect retrieval. Mentions and reposts do not establish affiliation. No documented public bulk API or explicit dataset reuse licence was located. Start with manual searches and original post links.

### Information Operations Archive

Links: [archive](https://www.io-archive.org/), [official toolbox listing](https://securingdemocracy.org/toolbox/).

The frontend returned HTTP 200. Its shipped JavaScript describes a historical Twitter/Reddit archive of more than ten million messages and includes search filters and CSV export paths. The referenced API base returned HTTP 502 during the check; a successful search/export was not verified. No explicit reuse licence was found in inspected materials. Keep as a historical reference until working data access is established.

### OSoMe labeled datasets

The [Zenodo record](https://zenodo.org/records/14189053), published 19 November 2024, covers 26 campaigns with comparison data. Access requires academic affiliation; downloads are limited to one data file per researcher per day. Its stated licence is CC BY-NC-ND 4.0. Hashed identifiers and URLs limit direct matching. It is a candidate for evaluating research methods rather than extending identified channel coverage.

## Investigations with evidence links

### VIGINUM

The French government [publications index](https://www.sgdsn.gouv.fr/viginum/publications) contains technical reports and individual case notes. The [May 2025 English Storm-1516 report](https://www.sgdsn.gouv.fr/files/files/Publications/20250507_TLP-CLEAR_NP_SGDSN_VIGINUM_Technical%20report_Storm-1516.pdf) documents 77 cases through 5 March 2025. Appendices and footnotes provide dated cases, domains, accounts and archived links; Spanish is among the content languages. It is marked TLP:CLEAR, a sharing designation rather than a copyright licence.

The [February 2024 Portal Kombat report](https://www.sgdsn.gouv.fr/files/files/20240212_NP_SGDSN_VIGINUM_RAPPORT-RESEAU-PORTAL-KOMBAT_VF.pdf) lists `pravda-es.com` for Spain. A [6 February 2026 case note](https://www.sgdsn.gouv.fr/publications/storm-1516-detection-dune-operation-dingerence-numerique-etrangere-ciblant-emmanuel) documents an X video and distribution sequence. These are bounded sets of evidence leads, not current complete inventories or archive classifications.

### CheckFirst and Reset Tech: Operation Overload

Links: [June 2025 publication](https://checkfirst.network/operation-overload-an-ai-fuelled-escalation-of-the-kremlin-linked-propaganda-effort/), [full report](https://checkfirst.network/wp-content/uploads/2025/06/Overload%C2%A02_%20Main%20Draft%20Report_compressed.pdf).

The report examines email, Telegram, X, Bluesky and TikTok. Its Telegram sample comprises seven million messages from 673 public channels, collected for 1 September 2024 to 20 March 2025, with channels selected through message links in newsroom emails. The Telegram methodology starts on printed page 51; appendix 12.6 discusses matching media identifiers. Spanish examples include cases covered by RTVE and Info Veritas.

The PDF states CC BY-SA. This does not establish that private emails or the complete message corpus are downloadable or reusable on the same terms. Use documented links and media examples as search leads. Report observed media matches, forward headers and timing; do not adopt the authors' inference from matching media identifiers to shared administration.

### Clemson Media Forensics Hub

Links: [reports](https://www.clemson.edu/centers-institutes/watt/hub/events/), [literature and data](https://www.clemson.edu/centers-institutes/watt/hub/resources/datasets.html).

The reports cover publishing and account networks across platforms, including Hungary's 2026 election and Bosnia and Herzegovina's October 2026 election. [Operation Overload: Matryoshka's Next Layer](https://open.clemson.edu/mfh_ci_reports/12/), published 25 March 2026, studies Bluesky observations from January and February 2025 with assistance from Antibot4Navalny and dTeam. That provides a direct connection to the initial research lead.

Use specific account/content examples and methods, checking raw-data availability and terms separately for each report. A case from another country does not establish an equivalent Spanish case.

### EU DisinfoLab

The [Doppelganger hub](https://www.disinfo.eu/doppelganger-hub/) links investigations, technical documentation and related reports. Its introduction says it has been updated through 2026; its older archive records a 7 July 2025 update. The [original September 2022 investigation](https://www.disinfo.eu/Doppelganger), with Qurium, documents copied news websites and social-platform distribution.

Use as a bibliography leading to original evidence. The hub itself is not a downloadable message dataset; some professional events require access. Record the underlying publication URL when extracting a lead.

### Qurium

The [Doppelganger investigations](https://www.qurium.org/doppelganger/) cover domains, hosting, redirects and service providers. [Sanctioned, Still Connected](https://www.qurium.org/doppelganger/sanctioned-still-connected-how-aezas-infrastructure-supply-chain-survived/), published 14 October 2026, uses a 22 September infrastructure snapshot and distinguishes BGP origin, subnet assignment and parent registry allocation.

This is useful for investigating domains already found in archived messages. Shared infrastructure alone does not establish a common publisher. No blanket open licence or bulk API was established in this review.

### Maldita and ATAFIMI

The [May 2026 monitoring publication](https://maldita.es/policy/20260504/epstein-iran-greenland-report-atafimi-2026/) covers January to March 2026 across Spain, Ukraine, Lithuania, Georgia, Bosnia and Herzegovina, Serbia, Argentina, Colombia, Mexico and Venezuela. It links a public report and gives Spanish-language cases for further investigation.

The [November 2025 project explanation](https://maldita.es/investigaciones/20251127/campanas-desinformacion-rusia-soldados/) describes a shared repository where partner organisations submit observations and alert one another to occurrences in other countries. A public export or API for that repository was not established. Public investigations are usable discovery sources; partner observations and editorial findings remain external judgments. Prefer original publication links and archived examples over summaries of the reports.

### EUvsDisinfo and NewsGuard

The [EUvsDisinfo database](https://euvsdisinfo.eu/disinformation-cases/) provides searchable cases, source references and editorial assessments. Its [methodology explanation](https://euvsdisinfo.eu/to-challenge-russias-ongoing-disinformation-campaigns-the-story-of-euvsdisinfo/) describes how cases are selected and assessed. Use for recurring phrases and historical examples; the assessments are not message-level archive labels.

[NewsGuard's Russia-Ukraine tracker](https://www.newsguardtech.com/special-reports/russian-disinformation-tracking-center/) publishes summaries and asks organisations to contact it for the full domain list and detailed records. Its [Media Imposter Tracking Center](https://www.newsguardtech.com/special-reports/media-imposter-tracking-center/) includes cases identified by Antibot4Navalny and VIGINUM. These are public discovery pages; complete underlying data access and terms require separate confirmation.

## Platform reports and technical research

### Meta threat-research indicators

The official [repository](https://github.com/facebook/threat-research) publishes CSV, JSON, TSV, STIX and campaign notes; its README states MIT licensing. It also cautions that sharing campaign links or engaging with them does not attribute an account to an operation.

The [September 2022 indicator CSV](https://github.com/facebook/threat-research/blob/main/indicators/csv/2022_09_removing_coordinated_inauthentic_behavior_from_china_and_russia.csv) was fetched successfully. Its columns are `indicator_type`, `indicator_value`, `comment` and `ds`. It contains 350 rows across URL, domain and Telegram-URL types. The filename includes both China and Russia cases: preserve comments and linked reports rather than assigning every row to one country. Ordinary services can also appear in campaign URL lists, so hostname overlap alone needs review. Recent entries labelled H2 2026 do not imply a completed reporting period.

This is the strongest additional machine-readable source found. The small local overlap check is recorded in [the work plan](RESEARCH_NEXT_STEPS.md).

### Google TAG and Google Threat Intelligence Group

[TAG's Q3 2025 bulletin](https://blog.google/threat-analysis-group/tag-bulletin-q3-2025/) gives platform enforcement summaries for YouTube, Blogger, Google News and Discover. It describes languages, origin assessments and removal totals, usually without original channel IDs or posts. Removal totals are not measurements of publication reach.

Google Threat Intelligence Group's [June 2026 ecosystem report](https://cloud.google.com/blog/topics/threat-intelligence/pro-russia-influence-ecosystem) and [September 2025 Polish-airspace case](https://cloud.google.com/blog/topics/threat-intelligence/pro-russia-information-operations-drone-incursions) provide named activity sets, screenshots and technical context. Extract exact evidence assets from individual reports. Public articles and commercial intelligence services have different access; no general public raw-message feed was established.

### Recorded Future and Graphika

Recorded Future's [German-election investigation](https://www.recordedfuture.com/research/stimmen-aus-moskau-russian-influence-operations-target-german-elections) supplies domains, IP addresses, ASNs, a Telegram handle and a full report PDF. It is useful for dated domain observations and infrastructure methods; provider assessments remain attributed.

[Graphika's report collection](https://www.graphika.com/reports) has public summaries, while some downloads require a business email and agreement to communications. The [Secondary Infektion page](https://www.graphika.com/reports/exposing-secondary-infektion) showed that form during inspection. Direct public PDFs for [Summit Old, Summit New](https://public-assets.graphika.com/reports/graphika_report_summit_old_summit_new.pdf) and [Cheap Tricks](https://public-assets.graphika.com/reports/Graphika_Report_Cheap_Tricks.pdf) were accessible. Check access per report rather than calling the collection open data. Useful artifacts include image/video examples, accounts and redirect sequences; a complete underlying corpus was not established.

### ISD, EEAS and DFRLab FIAT

[ISD's research collection](https://www.isdglobal.org/our-expertise/information-warfare-and-online-manipulation/foreign-information-manipulation-and-interference/) includes a [January 2025 European Telegram study](https://www.isdglobal.org/wp-content/uploads/2025/01/Behind-the-curtain-Unveiling-pro-Kremlin-ecosystems-in-Europe.pdf) with collection and coding methods. Collected messages were not verified as downloadable. Use its cases and methodology; semantic categories are the authors' annotations.

The [EEAS third threat report, March 2025](https://www.eeas.europa.eu/sites/default/files/documents/2025/EEAS-3nd-ThreatReport-March-2025-05-Digital-HD.pdf) describes infrastructure and an exposure matrix. It can inform evidence/provenance recording but is not a replacement message dataset.

[DFRLab's FIAT introduction](https://dfrlab.org/2024/10/23/dfrlab-launches-fiat-2024/) explains a [2024 dashboard](https://interference2024.org/) that records attribution allegations and assesses the supplied evidence and transparency. It tracks claims about incidents rather than all underlying publications. It is useful for separating who made a claim from what evidence they offered.

### TikTok and OpenMinds

TikTok's [reporting announcement](https://newsroom.tiktok.com/strengthening-approach-countering-influence-attempts?lang=en-GB) describes platform reporting. Its [report portal](https://www.tiktok.com/transparency/en/covert-influence-operations) was blocked to the browsing tool. The [July–December 2024 report](https://disinfocode.eu/reports/download/116) provides platform-originated descriptions. Current portal access needs manual verification; no account/post corpus was verified.

[OpenMinds](https://www.openminds.ltd/) has public research summaries and 2026 reports. Its [service description](https://www.openminds.ltd/sectors-page/stratcom) describes acquisition, monitoring and analysis. No public raw dataset or API was found in inspected pages. Use public reports for discovery and treat continuous monitoring as a service offering whose access must be checked.

## Broadcast and academic comparison sources

### GDELT and Internet Archive television tools

GDELT documents a [Visual Explorer channel inventory](https://blog.gdeltproject.org/visual-explorer-new-channel-inventory-json-file-for-programmatic-discovery/) and broadcast thumbnails/image sequences. A [19 December 2025 broadcast listing](https://api.gdeltproject.org/api/v2/tvv/tvv?date=20251219) includes 1TV, NTV, Russia-1 and Russia-24.

The documented [inventory endpoint](https://api.gdeltproject.org/api/v2/tvv/tvv?mode=chaninv) returned a response that failed JSON parsing during this check, and the main explorer timed out. The separate [caption television explorer](https://api.gdeltproject.org/api/v2/summary/summary?d=iatv) displays some coverage ending in October 2024. Do not treat these interfaces as equivalent or promise current complete coverage. A future broadcast pilot should first verify one channel/date and downloadable frames.

### BBC Monitoring

The official [public preview](https://monitoring.bbc.co.uk/?preview=true) exposes summaries and subscription prompts, including Russia-focused press reviews and media analysis. Full access requires a subscription; no public raw-feed export was verified. It is an optional source of broadcast/media context, not an open corpus for the current pilot.

### Telegram as a Battlefield

The [ICWSM 2025 paper](https://arxiv.org/abs/2501.01884) describes two author-labelled sets of 404 and 114 channels, with about 4.1 million and 1.1 million posts, spanning a year before and after the invasion. The paper was checked, but download availability and a dataset licence were not established. Keep as a methods/comparison candidate until those checks are complete; its channel categories are not our annotations.

## Reusable methods

[Information Laundromat](https://github.com/Institute-for-Strategic-Dialogue/information-laundromat) compares website indicators such as analytics IDs, verification tags, page structure and hosting. Use candidate matches to guide manual inspection of domains in `links.db`. Ordinary shared hosting or software is not evidence of common control. Compatibility and live service operation were not tested.

[DISARM 2.0 Observations](https://github.com/DISARMFoundation/DISARMframeworks-20-observable) is a beta vocabulary for describing assets, behaviours and content. It is not a Russian-source list or a detector. Its separation of observations from assessments can inform a research worksheet. Pin the version and inspect the actual licence file before reusing framework content; repository descriptions and older README licence statements differ. A full STIX/TAXII or incident-management system is unnecessary for the proposed pilot.
