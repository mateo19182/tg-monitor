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

An archive of Telegram channels and discussion groups relevant to Spanish politics, collected ahead of the general election of 29 November 2026. Release of {built}: {messages} messages from {channels} channels and groups ({groups_n} of them discussion groups), {range} plus {stories} weekly stories ({weeks}).

The same archive is browsable at https://canales.m19182.dev.

## Files

| config | content |
|---|---|
| `messages` | One row per message: text, date, views, forwards, replies, forward origin, links, media type and Telegram media identifiers. |
| `channels` | Archived channels and groups: title, description, subscribers, tier and group, the date the archive starts from, where the channel was listed from, message counts. |
| `stories` | Weekly groups of similar posts with machine-written title and summary (English and Spanish), one region and one or two themes, and the link to the previous week's story. |
| `story_members` | The messages in each story (`story_id`, `channel_id`, `msg_id`). |
| `arenas` | The fixed lists of regions and themes used for stories. |
| `forward_sources` | Channels that archived posts were forwarded from but that are not archived themselves. |

Join messages to channels on `channel_id`, and stories to messages through `story_members` on (`channel_id`, `msg_id`). A message's original is at `https://t.me/<username>/<msg_id>` for channels with a username.

### `messages` columns

`channel_id`, `msg_id` (unique together) · `date`, `edit_date`, `fetched_at` (UTC, ISO 8601) · `text` · `sender` (discussion groups only: a pseudonym, the same for the same account across the whole dataset; empty for channel posts) · `views`, `forwards`, `replies` (as last read) · `fwd_from_channel_id`, `fwd_from_msg_id`, `fwd_from_name`, `fwd_date` (forward origin) · `reply_to_msg_id` · `grouped_id` (album) · `urls` · `media` (photo, video, document, webpage, poll...) · `media_id`, `media_size`, `media_mime`, `media_duration`, `media_w`, `media_h` (Telegram identifiers and properties; files are not included).

## Method

**Collection**
- Telegram API (MTProto), one user account, every hour. {watchlist} channels and groups on a hand-maintained list; {channels} archived at release time. Tiers by type of channel (`channels.tier`), seven groups (`channels.group`).
- Views, forwards and text re-read for 7 days after posting. Deleted posts are kept. Some large channels are archived from a start date (`channels.archived_from`). No media files. Times in UTC.
- Discussion groups: sender account ids replaced by HMAC-SHA256 (keyed, truncated), stable across releases. Sender names and usernames not included; message text unchanged and can contain personal details.

**Stories**
- Input: posts ≥ 40 characters, discussion groups excluded; URLs, handle-only lines and subscription footers removed; identical texts merged.
- Embeddings: BAAI/bge-m3. Per ISO week: UMAP (10 dimensions, cosine, 15 neighbours) → HDBSCAN (min. cluster 12, min. samples 5); members with cosine to the centroid below max(0.60, mean − 1.5 sd) dropped. ~25% of posts unassigned.
- Week to week: centroid cosine ≥ 0.90 → `prev_story`; 0.85–0.90 → `related_story`.
- Labels (`label_model`) from the 8 posts nearest the centroid: title and summary (EN, ES), 1 region, 1–2 themes from `arenas`. Not reviewed one by one.

## Limits

- Only listed channels; start dates differ between channels.
- View counts as reported by Telegram.
- No reactions or Telegram stories; comments only from listed discussion groups.
- Some channels belong to media outlets subject to EU restrictive measures (Council Regulation (EU) No 833/2014). Users are responsible for complying with the rules that apply to them.

## Licence

Our compilation, metadata, story labels and pseudonymisation are released under CC BY-NC 4.0. Message text remains the work of its authors and is included for research, journalism and teaching.
