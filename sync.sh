#!/usr/bin/env bash
# Single entrypoint for both cron and manual runs. flock guarantees one collector at a time;
# a second invocation exits immediately. Resumable, so an interrupted run is just picked up next hour.
# After collecting, rebuilds the static site.
cd "$(dirname "$0")" || exit 1
flock -n .sync.lock bash -c '.venv/bin/python collect.py "$@" && .venv/bin/python site.py' _ "$@" >> sync.log 2>&1
