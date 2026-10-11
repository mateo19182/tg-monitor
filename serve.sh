#!/usr/bin/env bash
# Serves site/ and message search on 127.0.0.1:8788. Idempotent: exits if already listening.
cd "$(dirname "$0")" || exit 1
ss -ltn | grep -q '127.0.0.1:8788 ' && exit 0
exec .venv/bin/python server.py >> serve.log 2>&1
