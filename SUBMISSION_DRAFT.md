# Mapping political communication on Telegram in Spain

Working proposal for the Journal of Quantitative Description: Digital Media's Special Workflow Issue, announced by Kevin Munger. Started and revised 12 October 2026. Author names and affiliations remain to be added. Nothing has been submitted. [CALL]

The project aims to build a large, documented archive of public Telegram channels relevant to politics in Spain and use it to describe topics, publishing communities and change over time. The proposal leaves the classification scheme, clustering method and final observation window open. These are decisions to make through coverage audits and reviewed pilot analyses. No analytical results are claimed.

## Letter of inquiry

The following four answers follow the sequence required by the journal. [LOI]

### 1. Research question

How are political topics and publishing communities organized across public Telegram channels relevant to Spain, and how do their patterns change over time?

### 2. What the paper describes

We propose a quantitative description of political communication in a broad archive of public Telegram channels relevant to Spain. The archive will bring together party and institutional accounts, media outlets, associations, individual publishers and other public channels that regularly discuss Spanish politics. Our aim is to document a wide range of political positions and publishing roles, with channel inclusion supported by traceable sources.

The analysis will describe what these channels publish, which topics and content patterns recur across them, and how those patterns change over time. Exploratory clustering will help identify recurring themes and similarities between channels. Human review will guide the interpretation of clusters and the development of an annotation scheme. Classification will then support consistent measurement of selected topics or observable publishing practices across the archive, with performance assessed on held-out channels and periods. The specific labels and models will follow the pilot work.

The intended paper will report topic distributions, similarities and differences between channels, and temporal changes within a documented observation window. Forwarding, linked sources and repeated content are additional ways to examine relationships between publishers if coverage supports them. We will distinguish changes within a stable set of channels from changes caused by expanding the archive. The archive, sampling records, analysis code and validated annotations will also provide a basis for subsequent research.

### 3. Sample construction

The existing watchlist contains 319 entries, with collection continuing. This is a starting point rather than the final analytic sample. [LOCAL-WATCHLIST] We will expand it through documented institutional and party accounts, published channel lists, public directories and observed links or forwarding relationships. We will audit coverage across publishing roles, political positions, national and regional settings, and relevant languages. Because the current seeds include channels selected by earlier investigations, expansion will deliberately seek publishers outside those source lists.

Inclusion will require a public broadcast channel with a documented connection to political communication concerning Spain. We will record each discovery route, the evidence supporting inclusion, stable channel identifiers where available, collection bounds and inaccessible histories. Discussion groups will remain outside the main analysis. Foreign-language parent channels may support a separate source-tracing analysis; their inclusion in the principal sample will require the same relevance criteria.

Before the main analysis, we will freeze the sample and choose an observation window based on a channel-by-month coverage audit. Historical comparisons will use channels with adequate coverage in the relevant periods. Results will distinguish summaries weighted by message volume from summaries giving each channel equal weight, and show sensitivity to discovery route and incomplete coverage. This purposive sample will describe the included publishers. It will not estimate the distribution of political opinion in Spain or claim complete coverage of Spanish political Telegram.

### 4. Relevance to digital media

The project examines Telegram as a publishing and circulation environment for political communication. It asks how political discussion is distributed across public channels, which channels publish similar material, and how that organization changes over time. Classification and clustering will support a substantive description of communication on the platform. Observable forwards, links and content reuse can help distinguish similarity in subject matter from documented circulation between channels. The findings will concern publishing patterns, without inferring audience beliefs, electoral effects or common ownership from those patterns.

## Working research plan

The broad ambition is an archive spanning as much public political communication relevant to Spain as we can document. "All politics in Spain" is the collection ambition, not a claim of achieved coverage. Telegram is the present platform boundary. Coverage should include regional politics and relevant languages rather than equating politics in Spain with Spanish-language national discussion.

The first paper needs a coherent descriptive contribution within that larger project. For now, that contribution is a map of topics and publishing communities over time. The exact empirical emphasis can develop as the archive becomes more complete. If the pilot supports several questions, choose a manageable subset for this manuscript and retain the others for later work.

### Decisions to leave open during exploration

| Decision | Current direction | What should settle it |
| --- | --- | --- |
| Final channel sample | Broad public-channel coverage across publishing roles and political positions | Inclusion criteria, discovery records and coverage audit |
| Languages | Languages used in political communication relevant to Spain | Actual message composition and ability to validate the measurements |
| Observation window | Historical description with repeated monthly measurements | Comparable collection coverage and complete calendar periods |
| Clustering | Discover recurring message topics and compare channel topic profiles | Reviewed pilot results, outliers and stability across reasonable settings |
| Classification | Human-defined topics or observable publishing practices | Annotation guide, agreement and performance on unfamiliar channels and later periods |
| Temporal analysis | Topic prevalence, channel similarities and community changes | Stable cohorts, consistent measurements and sufficient observations |
| Sharing analysis | Forwards, linked domains and text or media-identifier reuse | Field completeness and validation of each signal |
| Archive release | A versioned research dataset with documented coverage | Field audit, release terms and treatment of personal identifiers |

### Candidate descriptive questions

These are options for developing the main question, not promises to answer every one in the first paper.

- Which topics occupy the most publishing activity, and does the picture change when each channel receives equal weight?
- Which channels discuss similar subjects despite having different publishing roles or observed sources?
- Do channel groupings remain stable across months, or do they change around particular periods and events?
- How much does repeated material affect the apparent prominence of a topic?
- Which categories can human readers define and classifiers measure reliably across channels and time?
- How do national and regional channels differ in the subjects and sources they publish?

Topic similarity, forwarding communities and reuse networks describe different relationships. We can compare them if the pilot makes that comparison useful, but it is no longer the required organizing question for this proposal.

### Minimum analysis for a credible first paper

Start with a frozen channel manifest and a coverage table. Distinguish missing collection, inaccessible history and genuine periods without observed posts. Document how each channel entered the sample and check which publishers the discovery process may have missed.

Fit exploratory models on a sample balanced across channels and months. Compare a simple text-based baseline with embedding-based clustering. Keep original text and a documented normalized version. Check whether copied posts, signatures or unusually prolific channels determine the clusters. Inspect representative messages, ambiguous assignments and outliers before naming clusters.

Use human review to decide whether any recurring categories warrant a classifier. Preserve the distinction between sourced channel descriptions, discovered clusters and human-assigned message labels. A channel's existing watchlist category is not a message-level training label. Separate channels, time periods and duplicate families during evaluation so that copied posts and familiar signatures do not inflate apparent performance.

For temporal description, use comparable channel sets and denominators. Report message counts alongside topic shares, missingness and the number of contributing channels. Changes in archive coverage, model assignments or retrieval practices can resemble changes in communication. Any classifier or topic model used across periods needs validation across those periods.

The main text should present a small set of interpretable findings, supported by inspected examples. No causal claims are planned. Classifiers measure the categories defined by the annotation guide; they do not establish whether a message is true or whether a publisher has a particular intent.

## Relationship to earlier research

Gómez-Romero and colleagues' 2026 EPJ Data Science study already examines over 1.7 million messages from 95 Spanish-language channels using topic modeling and forwarding networks. It also describes network communities and their topic composition. These approaches cannot be presented as new in themselves. [EPJ-2026]

The intended contribution here is a broader, inspectable sampling effort and a descriptive account of political publishing across the included channels and periods, supported by reviewed classification and clustering. Whether the coverage and resulting findings make that contribution strong enough remains to be established. Size alone will not establish novelty. The selective review in [STATE_OF_THE_ART.md](STATE_OF_THE_ART.md) records the closest studies and methods; its earlier recommendation to focus on topic similarity versus sharing remains one possible direction.

## Archive and publication outputs

The planned research package includes a dated channel manifest, discovery sources, coverage and exclusion tables, field definitions, analysis code, model versions, validation records and aggregate results. A dataset release is a central project goal. The fields and access arrangements should be specified before promising a complete downloadable text archive. Discussion-group participant records, credentials and session files are outside the proposed release.

The journal proposal concerns an empirical description using the archive. A separate data paper remains an option for documenting the archive itself, subject to the venue policies recorded in STATE_OF_THE_ART.md.

## Submission status and next decisions

The Special Workflow Issue's LOI deadline is 25 October 2026. Decisions are scheduled for 1 November, with full manuscripts due 15 January. The call does not print the year beside that later date; January 2027 follows from the October 2026 call. Accepted proposals receive the journal's manuscript-checking skill file. [CALL]

Before submitting, add the authors and affiliations, review the research question in the author's own voice, and check that the promised sample and analysis are feasible. The methods can continue developing, but the submitted LOI should give editors a clear description of what the eventual paper will describe.

No proposal or manuscript has been submitted. The project has not received the editorial skill file or an approving manuscript report.

## Sources

- [CALL] [JQD:DM Special Workflow Issue call](https://journalqd.org/special-workflow-issue), checked 12 October 2026. [Kevin Munger's announcement](https://kevinmunger.substack.com/p/an-experiment-in-ai-peer-review) provides the original context.
- [LOI] [JQD:DM letter of inquiry requirements](https://journalqd.org/loi), checked 12 October 2026.
- [EPJ-2026] Gómez-Romero, J., Cantón-Correa, J., Fajardo, W., and Molina-Solana, M. [Multimedia, engagement, and diffusion in alternative online communities: evidence from Spanish telegram channels](https://link.springer.com/article/10.1140/epjds/s13688-026-00667-w). EPJ Data Science 15, 71, 2026.
- [LOCAL-WATCHLIST] Local read-only count of [channels.csv](channels.csv) on 12 October 2026 using Python's `csv.DictReader`: 319 entries. This counts watchlist entries, not fully collected or analytically eligible channels. Collection continues.
