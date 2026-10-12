#!/usr/bin/env bash
# Weekly: group last ISO week's posts into stories and label them. Cron: Monday 05:00.
# Usage: stories.sh [YYYY-Www]   (defaults to the previous ISO week)
cd "$(dirname "$0")" || exit 1
week="${1:-$(date -d 'last monday' +%G-W%V)}"   # on a Monday this is the week that just ended
{
  echo "=== $(date -Is) stories for $week"
  .venv/bin/python stories.py --week "$week" && .venv/bin/python stories.py --week "$week" --label --cap 10
  .venv/bin/python stories.py --week "$week" --map
} >> stories.log 2>&1
