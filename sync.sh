#!/usr/bin/env bash
# Single entrypoint for both cron and manual runs. flock guarantees one collector at a time;
# a second invocation exits immediately. Resumable, so an interrupted run is just picked up next hour.
# After collecting, rebuilds the static site and embeds the new message texts (embed.py, GPU, seconds).
cd "$(dirname "$0")" || exit 1
# Embedding and links are independent of each other: a busy .embed.lock must not skip the links index.
flock -n .sync.lock bash -c '.venv/bin/python collect.py "$@" && .venv/bin/python site.py; flock -n .embed.lock .venv/bin/python embed.py; .venv/bin/python links.py index && .venv/bin/python links.py summary' _ "$@" >> sync.log 2>&1
