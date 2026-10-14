# Research sources and tools

## Antibot4Navalny and Metabot

Reviewed on 14 October 2026. These are sources of research leads for manual verification, not inputs to channel classification or archive labels.

- [Antibot4Navalny on X](https://x.com/antibot4navalny) can provide original post links, phrases, domains and dates to look for in the archive. The timeline could not be read directly during this review; the assessment uses public repository files and the investigations below.
- [Metabot](https://github.com/antibot4navalny/metabot) is a browser extension for X/Twitter. Its code matches account usernames against supplied label lists and highlights posts. It does not collect Telegram messages or independently detect coordinated activity. It may help manual browsing of X, but is not recommended for integration into the collection pipeline.
- [accounts_labelled](https://github.com/antibot4navalny/accounts_labelled) contains public JSON account-label lists. The inspected main file contains 1,984 keys, including numeric IDs and usernames; this is not a unique-account count. The inspected files do not supply message-level evidence for each label. They are a possible reference for a separate X study, not Telegram annotations.

There is a concrete Spanish-language research connection. [EFE Verifica's 2 May 2025 investigation](https://verifica.efe.com/apagon-espana-portugal-campana-prorrusa-desinformacion/) credits the group with identifying posts using The Independent and France 24 branding during the April 2025 Iberian blackout. EFE examined related publications on Telegram, X and other platforms. [Maldita's 5 May 2025 investigation](https://maldita.es/malditobulo/20250505/articulo-suplanta-independent-matrioska-apagon/) also cites the group and describes publication across Telegram, X and Bluesky and subsequent reproduction in larger Telegram channels and Pravda pages. These reports supply cases to inspect; their interpretations are not archive findings.

Use specific original message links, exact phrases, domains and timestamps as search leads in `tg.db`. Describe matches through archived text, observed timing, links and recorded forward provenance. The earliest archived occurrence is not necessarily the original publication. For any newly discovered channel, verify its public handle, choose the tier by what it is and record the specific discovery URL in `channels.csv`'s `source` field. External account labels and interpretations do not enter the frontend or dataset.

GitHub repository metadata checked during the review reports Metabot last pushed on 20 May 2024 and accounts_labelled on 10 October 2026. This distinguishes repository activity from extension compatibility or label accuracy. Neither repository exposed an explicit licence in the inspected tree or GitHub licence metadata; check reuse terms before redistributing their code or lists.
