#!/usr/bin/env bash
# Serves site/ on 127.0.0.1:8788 (expose via cloudflared). Idempotent: exits if already listening.
cd "$(dirname "$0")" || exit 1
ss -ltn | grep -q '127.0.0.1:8788 ' && exit 0
exec .venv/bin/python -m http.server 8788 --bind 127.0.0.1 --directory site >> serve.log 2>&1
