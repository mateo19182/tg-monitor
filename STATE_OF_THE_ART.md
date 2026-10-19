# Spanish political Telegram archives and clustering

Working research notes, checked on 12 October 2026. This is a selective review of the closest empirical studies, reusable datasets and methods, not a systematic literature review. Source keys are local to this document. Proposed analyses below are research plans, not results.

Project direction updated later on 12 October 2026: the author prefers a broad archive of political communication relevant to Spain, with classification, clustering and temporal description. [SUBMISSION_DRAFT.md](SUBMISSION_DRAFT.md) records that working proposal. The narrower recommendation below remains a candidate analysis; it is not the selected scope. Watchlist counts below describe the earlier review snapshot.

The strongest first paper would describe how topic similarity relates to observable content exchange among sampled public channels relevant to Spanish politics. The archive would make the evidence inspectable. Clustering would help discover themes and construct later annotations. A claim that this is the first Spanish Telegram study, or that applying BERTopic is itself new, would be wrong.

## Closest empirical work

| Source key and primary source | Sample and approach | What we can inspect | Implication for this project |
| --- | --- | --- | --- |
| M2022, [Maldita.es investigation](https://maldita.es/malditodato/20221219/clan-negacionismo-telegram/) | Maldita reports 574,414 messages from 39 selected channels, 1 January 2020 to 30 September 2022. It describes forwards, links, channel relationships and recurring terms. | Published examples, named channels and interactive charts. These establish the reported sample, not a verified complete raw-message release. | Existing channel-network and longitudinal work must be acknowledged. Maldita's channel characterizations remain attributed claims, not message-level labels. |
| M2025, [Maldita.es investigation of Pravda sources](https://maldita.es/investigaciones/20250710/canales-telegram-pravda/) | Maldita selects the 25 Telegram channels most referenced by five Pravda editions directed at Spain or Spanish speakers, November 2024 to May 2025. It measures reproduction, timing, forwards, mentions and domains. | Named channels, examples and charts. The sampling criterion describes a particular publishing relationship. | A useful source of seeds and comparison cases, but not a sample of all Spanish political Telegram. Reproducing this relationship requires collecting the relevant website records too. |
| EPJ2026, [Gómez-Romero et al.](https://link.springer.com/article/10.1140/epjds/s13688-026-00667-w) | Over 1.7 million messages from 95 Spanish-language channels, December 2019 to May 2025. Authors classify 80 as "alternative" and use 15 mainstream channels for context. They examine multimedia, views and forwards, using BERTopic and channel networks. | Channel identities are deliberately withheld. The accompanying record is Z2026 below. | Closest direct comparison. Topic modeling, media comparisons and forwarding networks are already established here. |
| IT2025, [Alvisi, Tardelli and Tesconi preprint](https://arxiv.org/html/2504.19594v1) | The authors analyze Italian chats and 2023 messages using catalog seeds, forwarding-based snowball collection, directed weighted networks, Louvain communities and LLM-assisted labels. | This preprint states that an anonymized network link will be supplied upon acceptance. It does not supply a full identified corpus in its data statement. | Topic and network community comparisons have precedents beyond Spain. Keep message clustering separate from channel community detection. |

The EPJ implementation uses multilingual MiniLM embeddings, UMAP, HDBSCAN and class-based TF-IDF. GPT-4o produces topic descriptions. It caps merged topics at 500, reports about 30% unassigned messages and uses qualitative topic inspection. Its regression specifications include channel, quarter and topic fixed effects. This project should not claim to replicate their sample because its identities are unavailable. [EPJ2026](https://link.springer.com/article/10.1140/epjds/s13688-026-00667-w)

The Italian preprint's abstract says 13,151 chats, while its methods report 15,378 collected chats, 13,144 nodes after removing isolates and 11,305 nodes in retained communities. These are not interchangeable denominators, and the abstract/methods discrepancy should be resolved before citing a single chat count. [IT2025](https://arxiv.org/html/2504.19594v1)

## Dataset precedents and access

| Source key and primary source | Records and access checked | What it supports |
| --- | --- | --- |
| Z2026, [EPJ study's Zenodo record](https://zenodo.org/records/20172760) | Public record, restricted files. The description lists sampled message metadata and topic descriptions. Its listed fields omit raw message text, exact timestamps and an identified channel mapping. | Metadata analysis subject to access. The listed release cannot independently reproduce text embeddings, exact posting lags or channel identity comparisons. |
| PUSH2020, [Pushshift dataset paper](https://ojs.aaai.org/index.php/ICWSM/article/view/7348) and [Zenodo release](https://zenodo.org/records/3607497) | Paper reports over 27,800 channels, 317 million messages and 2.2 million users. Zenodo lists downloadable compressed account, channel and message files. | A substantial public Telegram archive already exists. Value here must come from documented Spanish political sampling, current coverage, provenance and usable validation rather than raw size. |
| CORPUS2021, [Solopova, Scheffler and Popa-Wyatt data paper](https://doi.org/10.5334/johd.32) | A corpus from one channel of Donald Trump supporters, late 2016 to January 2021, with automatic offensive-language annotations and manual annotations for a selected portion. | A precedent for combining a Telegram corpus with different annotation layers. Machine-generated labels and human judgments should remain distinguishable. |

Our exporter currently includes message text, timestamps, forward fields, URLs, counters, sender IDs and media metadata, plus channel and source tables. This is an implementation description, not a promise about release contents or field completeness. The release design still needs a stable snapshot, documented inclusion rules and a deliberate treatment of discussion-group sender IDs. [LOCAL-EXPORT](export.py)

## Methods worth using

BERTopic combines transformer document embeddings, clustering and class-based TF-IDF topic representations. It is a defensible exploratory baseline, not a certificate that discovered clusters correspond to stable social categories. [BERTOPIC2022, Grootendorst](https://arxiv.org/abs/2203.05794)

Human interpretation needs its own validation. Chang et al. introduced word-intrusion and topic-intrusion tasks and found that better held-out likelihood can coincide with poorer interpretability. For this project, review sampled messages and topic assignments as well as keywords. Do not select a model solely by an automatic coherence score. [TOPICVALID2009](https://papers.neurips.cc/paper/2009/hash/f92586a25bb3145facd64ab20fd554ff-Abstract.html)

Pacheco et al. construct networks from shared behavioral traces, including content and timing. Their method motivates examining repeated texts, media or URL sequences. Here these should be reported as observed similarity or reuse. Similarity alone does not establish a shared operator, deliberate coordination or intent. [TRACE2021](https://arxiv.org/abs/2001.05658)

For a first analysis, compare a lexical baseline using TF-IDF and NMF with an embedding-based clustering pipeline. Record preprocessing, embedding model, seed, parameters and outlier share. Evaluate whether topics survive removal of channel signatures and repeated text, changes in sampling, and changes in seed. These are proposed checks, not assertions that either model performs better on this archive.

## Recommended descriptive question

**Among sampled public channels relevant to Spanish politics, how do topic similarity, explicit forwarding and repeated content overlap, and how does that relationship vary over time?**

This question concerns publishing and circulation on a digital platform. It gives clustering a purpose and permits disagreement between the different measurements. A pair of channels might discuss the same issue without forwarding each other. Another pair might exchange many posts while publishing different overall topic mixes. Both are interpretable descriptive outcomes.

Build separate measurements before combining them:

| Measurement | Operational proposal | Main qualification |
| --- | --- | --- |
| Topic similarity | Compare channel topic distributions within a shared observation window. | A topic is a model output validated by readers, not a verdict on the channel. |
| Explicit forwarding | Directed source-to-destination edges from recorded forward provenance; count observed events. | Missing or hidden provenance and unsampled destinations make this an observed subnetwork. |
| Exact text reuse | Normalize text, preserve originals and link identical substantive texts across channels. | Strip recurring signatures for this measurement; shared boilerplate is not substantive reuse. |
| Near text reuse | Similarity thresholds validated against manually reviewed pairs. | Similar reporting of a common event can create matches without copying. |
| Media reuse | Match recorded media identifiers where available; audit agreement on examples. | An identifier match is narrower than visual similarity. Missing historical media IDs need separate reporting. |
| Domain sharing | Compare distributions of linked registrable domains. | Shared links can indicate sourcing, criticism, advertising or quotation. Context determines interpretation. |
| Time | Compare first observed copies and forward timestamps in the sampled archive. | The earliest observed post need not be the original source. |

Useful outputs would include a channel coverage table, monthly topic distributions, matched-pair examples, separate forwarding and reuse networks, and a plot comparing topic similarity with exchange volume. Define the denominators before calculating percentages. Show counts weighted by messages and summaries giving equal weight to channels, because they answer different questions.

## Other research directions

These are proposed extensions, ordered by how readily they use the present archive.

1. **How much do repeated copies change the apparent agenda?** Compare topic prevalence counting every post with prevalence counting one representative per reused-text group. This asks whether publishing volume and distinct-content volume describe the same agenda.
2. **Are recurring channel communities also topic communities?** Compare partitions from forwarding and content reuse, then inspect the pairs on which they disagree. Repeat in fixed time windows and check partition stability.
3. **How do source channels and destinations differ?** Compare a channel's own posts with the subset observed elsewhere. Some topics may be common in original output but rare among copies. This requires adequate observation of both sides.
4. **How does cross-language publication relate to Spanish circulation?** Use the watched parent channels and Spanish editions to examine matched posts and observed lags. Validate translated matches manually; timestamp order alone cannot establish a translation relationship.
5. **How does a cluster become a useful annotation category?** Have readers consolidate recurring themes into a codebook, including unclear and multi-topic cases. Annotate held-out examples and train topic or publishing-function classifiers afterward.

### Related research leads

Two X posts shared on 12 October 2026 connect reported Yandex data-centre outages with changes in online activity metrics: [IrishPoliticsNL on Reddit activity](https://x.com/irishpoliticsnl/status/2109568747195240802) and [Tomasz Dechovsky on AfD-related activity](https://x.com/tomaszdechovsky/status/2109328777452962127). The latter frames its interpretation as tentative (“If confirmed”). These are leads for examining platform-level activity around infrastructure disruptions, not verified findings; any follow-up would need the underlying data, methods and alternative explanations.

For the classifier extension, start with a majority-label baseline, TF-IDF plus a linear classifier, and embeddings plus a linear classifier. Split by channel and time, and keep duplicate families in a single split. Otherwise a model may recognize a copied post or a familiar channel signature rather than generalize. Report per-label precision and recall, macro-F1, coverage and disagreement. Annotation categories should concern observable content, such as topic, language, linked source or explicit subscription request.

## Scope and sampling limits

The repository's watchlist contains 219 entries as of 12 October 2026. It combines published source lists, operator categories, parties, media, parent channels, discussion groups and discoveries through forward provenance. It is a purposive watchlist. The channel categories are collection strata, not classifier ground truth. Its archived subset changes while collection proceeds, so 219 is not a count of completely collected channels. Use the watchlist and synchronization records to freeze the actual analytic sample. [LOCAL-WATCHLIST](channels.csv), [LOCAL-METHOD](README.md)

The local Maldita coverage ledger records the 39 entries from M2022 and the 25 from M2025 separately. It preserves unresolved or inaccessible names and uncertain matches rather than treating every historical title as a verified current channel identity. [LOCAL-MALDITA](maldita-coverage.csv)

Before fitting a publishable analysis:

- Record intended versus successfully archived channels, inclusion sources, collection bounds, first and last observed posts, errors and completion status.
- Choose a common window for the main comparison, with longer histories used separately. Channel-specific `since` bounds must remain visible.
- Separate broadcast-channel output from discussion-group messages and automatically forwarded channel posts.
- Audit language at message level. Spanish-language channels can still contain copied or quoted material in other languages.
- Record when counters were fetched. Views are approximate, include forwarded copies and can count returning viewers again after roughly four days, according to Telegram's own FAQ. They do not measure unique people, belief or votes. [TG-VIEWS](https://telegram.org/faq_channels#q-what-does-the-eye-icon-mean)
- Report missing text and metadata. The present system records media metadata without downloading the underlying media files. [LOCAL-METHOD](README.md)
- Treat deletions, inaccessible channels, renamed handles and incomplete history as observation limits. Do not present an absent archived message as proof that no message existed.

The target of inference should be the specified sampled channels and observation window. A sample weighted only to its own watchlist cannot establish representativeness of all Spanish Telegram users or the Spanish electorate.

## Publication options

These fit assessments are recommendations based on the linked official scopes. Prices were checked on 12 October 2026; taxes, agreements and waivers can change the amount payable.

| Venue | Fit and required emphasis | Verified policy and fees |
| --- | --- | --- |
| Journal of Quantitative Description: Digital Media | First choice for the descriptive question about topics and content exchange. The archive supports a substantive account of digital publishing. | Quantitative description, no causal claims, mandatory LOI and no APCs. LOI must answer four questions explicitly and pays particular attention to sampling and weighting. [JQD-ABOUT](https://journalqd.org/about), [JQD-LOI](https://journalqd.org/loi) |
| Scientific Data | Strong option for a stable reusable archive with acquisition details, records, technical validation and usage notes. | Data Descriptor format; data available to reviewers initially and public in a formal repository from the second round. Current APC €2,390 / $2,690 / £2,150 before applicable taxes. [SD-GUIDE](https://www.nature.com/sdata/submission-guidelines), [SD-FEES](https://www.nature.com/sdata/open-access) |
| Journal of Open Humanities Data | Archive or annotated Spanish-language corpus, particularly with a media-studies or linguistics rationale. It has published a Telegram corpus. | Data papers are 1,000 to 1,500 words; discussion papers 3,000 to 5,000. Its scope excludes papers presenting empirical research results. An APC applies unless a requested waiver is granted; exact current price was not verified. [JOHD-ABOUT](https://openhumanitiesdata.metajnl.com/about), [CORPUS2021](https://doi.org/10.5334/johd.32) |
| EPJ Data Science | Possible after a strong substantive result on the relationship between topics, networks and circulation. | Official scope cautions against purely descriptive statistics or standard techniques on mainstream datasets. Current APC €1,690 / $1,990 / £1,340 before applicable taxes; a Database article type is also listed. [EPJ-GUIDE](https://link.springer.com/journal/13688/submission-guidelines) |

Data in Brief remains a venue to investigate, but its official guide and fee pages could not be read during this check. No current policy or price is asserted here.

Publication order needs care. Scientific Data says a prior research publication should not already disclose the same dataset identifier being described by a later Data Descriptor. If pursuing both a descriptive paper and a data paper, resolve that journal-specific condition before treating them as a routine sequence. [SD-RELATED](https://www.nature.com/sdata/policies/editorial-and-publishing-policies)

Kevin Munger's call opens LOIs from 9 to 25 October, gives LOI decisions on 1 November and sets 15 January for full manuscripts. It requires an approving report from the supplied skill file alongside the manuscript, with model and skill versions recorded. The stated division assigns standardized checks to an LLM and contribution judgments to human reviewers. The October 2026 call implies January 2027 for the full-manuscript date, although its timeline lists month and day without years. [MUNGER-CALL](https://kevinmunger.substack.com/p/an-experiment-in-ai-peer-review)

## What to claim now

We can propose a documented archive and an exploratory comparison of topics, forwards and reused content. We cannot yet claim a completed broad sample, validated clusters, classifier performance, a particular network structure, causal influence or electoral impact. The first practical research milestone is a frozen coverage audit and a small reviewed clustering pilot. That evidence should determine the final question and promised manuscript scope.
