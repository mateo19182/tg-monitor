#!/usr/bin/env bash
# Single entrypoint for both cron and manual runs. flock guarantees one collector at a time;
# a second invocation exits immediately. Resumable, so an interrupted run is just picked up next hour.
cd "$(dirname "$0")" || exit 1
exec flock -n .sync.lock .venv/bin/python collect.py "$@" >> sync.log 2>&1
