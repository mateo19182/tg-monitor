#!/usr/bin/env bash
# Weekly: group last ISO week's posts into stories, label them, regroup subjects, update the map, refresh the HF dataset,
# then send a short report to Telegram through Hermes. Cron: Monday 05:00.
# Usage: stories.sh [YYYY-Www]   (defaults to the previous ISO week)
cd "$(dirname "$0")" || exit 1
week="${1:-$(date -d 'last monday' +%G-W%V)}"   # on a Monday this is the week that just ended
run=$(mktemp)
usd0=$(.venv/bin/python -c 'from stories import ledger_read; print(ledger_read()["usd"])')
{
  echo "=== $(date -Is) stories for $week"
  .venv/bin/python stories.py --week "$week" && .venv/bin/python stories.py --week "$week" --label
  .venv/bin/python stories.py --subjects --label   # regroup the year into subjects, name new ones
  .venv/bin/python stories.py --week "$week" --map
  .venv/bin/python release.py build && .venv/bin/python release.py upload   # refresh the HF dataset (visibility unchanged)
} > "$run" 2>&1
cat "$run" >> stories.log
.venv/bin/python weekly_report.py --week "$week" --log "$run" --usd0 "$usd0" > "$run.report" 2>&1 \
  || { echo "tg-monitor: weekly report for $week failed, see stories.log"; tail -5 "$run.report"; } > "$run.report.err"
[ -s "$run.report.err" ] && mv "$run.report.err" "$run.report"
"$HOME/.local/bin/hermes" send --to telegram --quiet --file "$run.report" || echo "$(date -Is) hermes send failed" >> stories.log
rm -f "$run" "$run.report" "$run.report.err"
