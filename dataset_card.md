---
license: cc-by-nc-4.0
language:
- es
- ru
- en
pretty_name: Spanish Politics on Telegram
size_categories:
- 1M<n<10M
task_categories:
- text-classification
- text-retrieval
tags:
- telegram
- politics
- spain
- elections
- social-media
configs:
- config_name: messages
  data_files: messages/*.parquet
  default: true
- config_name: channels
  data_files: channels.parquet
- config_name: stories
  data_files: stories.parquet
- config_name: story_members
  data_files: story_members.parquet
- config_name: arenas
  data_files: arenas.parquet
- config_name: facts
  data_files: facts.parquet
- config_name: forward_sources
  data_files: forward_sources.parquet
extra_gated_prompt: >-
  This dataset contains posts from public Telegram channels and messages from discussion groups,
  including messages written by private individuals. Access is granted for research, journalism and
  teaching. By requesting access you agree not to attempt to re-identify pseudonymised senders, not to
  use the data to target or harass individuals, and not to redistribute the message text outside the
  terms of this licence.
extra_gated_fields:
  Name: text
  Affiliation: text
  Intended use: text
  I agree to use this dataset for research, journalism or teaching only and not to re-identify senders: checkbox
---

# Spanish Politics on Telegram

An archive of Telegram channels and discussion groups relevant to Spanish politics, collected ahead of the general election of 29 November 2026. Release of {built}: {messages} messages from {channels} channels and groups ({groups_n} of them discussion groups), {range}, plus {stories} weekly stories ({weeks}) and {facts} attributed statements from published research about the channels.

The same archive is browsable at https://canales.m19182.dev.

## Files

| config | content |
|---|---|
| `messages` | One row per message: text, date, views, forwards, replies, forward origin, links, media type and Telegram media identifiers. |
| `channels` | Archived channels and groups: title, description, subscribers, tier and group, the date the archive starts from, where the channel was listed from, message counts. |
| `stories` | Weekly groups of similar posts with machine-written title and summary (English and Spanish), one region and one or two themes, and the link to the previous week's story. |
| `story_members` | The messages in each story (`story_id`, `channel_id`, `msg_id`). |
| `arenas` | The fixed lists of regions and themes used for stories. |
| `facts` | Statements from published research about listed channels, each with its source (publisher, title, date, URL). |
| `forward_sources` | Channels that archived posts were forwarded from but that are not archived themselves. |

Join messages to channels on `channel_id`, and stories to messages through `story_members` on (`channel_id`, `msg_id`). A message's original is at `https://t.me/<username>/<msg_id>` for channels with a username.

### `messages` columns

`channel_id`, `msg_id` (unique together) · `date`, `edit_date`, `fetched_at` (UTC, ISO 8601) · `text` · `sender` (discussion groups only: a pseudonym, the same for the same account across the whole dataset; empty for channel posts) · `views`, `forwards`, `replies` (as last read) · `fwd_from_channel_id`, `fwd_from_msg_id`, `fwd_from_name`, `fwd_date` (forward origin) · `reply_to_msg_id` · `grouped_id` (album) · `urls` · `media` (photo, video, document, webpage, poll...) · `media_id`, `media_size`, `media_mime`, `media_duration`, `media_w`, `media_h` (Telegram identifiers and properties; files are not included).

## Method

**Scope.** {watchlist} Telegram channels and discussion groups relevant to Spanish politics are on the list; {channels} had been archived at the time of this release, the rest are queued. Each is placed in a tier by what it is (who runs it, what it is an edition of, where it is based), and tiers are grouped into seven groups (`channels.tier`, `channels.group`). Channels come from published research (cited in `facts`), from forwards seen in the archive, and from searches for parties, institutions, media and organisations. The list is maintained by hand.

**Collection.** Posts are read every hour through the Telegram API. Views and forwards are re-read for seven days after a post appears and then stay as they were. An edit replaces the earlier text. Posts deleted from Telegram after they were archived are kept. For some very large channels only posts from a set date are archived (`channels.archived_from`). Media files are not stored.

**Stories.** Every week, posts of at least 40 characters are compared by meaning with a multilingual text model (BAAI/bge-m3), after links, handles and subscription footers are removed. Discussion groups are left out. Posts close to each other form a story when there are at least 12 of them (UMAP to 10 dimensions, then HDBSCAN); posts far from the centre of their story are dropped. About a quarter of posts fit no story. A story is linked to one from the previous week when the cosine similarity of their centres is 0.90 or more (`prev_story`), and marked as related between 0.85 and 0.90 (`related_story`).

Titles, summaries, region and themes are written by a language model (`label_model`) from up to eight representative posts of each story. The model is instructed to describe what the posts say, to attribute claims to the channels, and not to use evaluative words. Regions and themes come from the fixed lists in `arenas`. Labels are not checked one by one and can be wrong.

**Published research.** `facts` holds statements from published research, journalism and official sources about listed channels, each with its source. They are the findings of those sources, not of this dataset. Fact-checkers, governments, researchers and media are cited in the same way, and contrary findings are included where they exist.

**Pseudonymisation.** In discussion groups, the Telegram account id of each sender is replaced by a keyed hash (HMAC-SHA256, truncated). Display names and usernames of senders are not included. Message text is unchanged and can contain names or other personal details.

## Limits

- Only channels on the list are archived; spread elsewhere on Telegram is not measured.
- Archive start dates differ between channels.
- View counts are reported by Telegram and cannot be verified.
- Reactions and Telegram stories are not collected. Comments are collected only for the discussion groups on the list.
- Which channels are on the list is a selection; tier descriptions in `channels.tier_description` state the criteria.
- Some channels belong to media outlets subject to EU restrictive measures (Council Regulation (EU) No 833/2014). Users are responsible for complying with the rules that apply to them.

## Licence

Our compilation, metadata, story labels and pseudonymisation are released under CC BY-NC 4.0. Message text remains the work of its authors and is included for research, journalism and teaching.
