#!/usr/bin/env bash
# Weekly: group last ISO week's posts into stories, label them, refresh the HF dataset. Cron: Monday 05:00.
# Usage: stories.sh [YYYY-Www]   (defaults to the previous ISO week)
cd "$(dirname "$0")" || exit 1
week="${1:-$(date -d 'last monday' +%G-W%V)}"   # on a Monday this is the week that just ended
{
  echo "=== $(date -Is) stories for $week"
  .venv/bin/python stories.py --week "$week" && .venv/bin/python stories.py --week "$week" --label --cap 30
  .venv/bin/python stories.py --subjects --label --cap 30   # regroup the year into subjects, name new ones
  .venv/bin/python stories.py --week "$week" --map
  .venv/bin/python release.py build && .venv/bin/python release.py upload   # refresh the HF dataset (visibility unchanged)
} >> stories.log 2>&1
