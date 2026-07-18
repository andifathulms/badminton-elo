#!/usr/bin/env bash
# Periodically re-rate from the latest collected data and refresh the live demo.
#
# Runs alongside `collect_h2h` (which keeps writing new stats/ranks to
# db.sqlite3): every INTERVAL seconds it takes an online-backup snapshot to a
# staging file, rates + builds derived data there, atomically swaps it into the
# served snapshot, and reloads the web container. No downtime for the collector.
#
#   scripts/refresh_ratings.sh [interval_seconds]   # default 7200 (2h)
cd "$(dirname "$0")/.." || exit 1

INTERVAL="${1:-7200}"
COMPOSE="docker compose -f docker-compose.local.yml"

refresh() {
  ts=$(date -u +%FT%TZ)
  echo "[$ts] snapshot + re-rate…"
  .venv/bin/python - <<'PY' || return 1
import sqlite3
s = sqlite3.connect("data/db.sqlite3")
d = sqlite3.connect("data/serve_stage.sqlite3")
with d:
    s.backup(d)          # online backup — safe while collect_h2h writes
s.close(); d.close()
PY
  export SQLITE_PATH="$PWD/data/serve_stage.sqlite3"
  .venv/bin/python manage.py rate >/dev/null 2>&1 || { unset SQLITE_PATH; return 1; }
  .venv/bin/python manage.py build_pairs >/dev/null 2>&1
  .venv/bin/python manage.py build_analytics >/dev/null 2>&1
  unset SQLITE_PATH
  mv -f data/serve_stage.sqlite3 data/serve.sqlite3
  $COMPOSE restart web >/dev/null 2>&1
  echo "[$ts] refreshed."
}

echo "refresher started (every ${INTERVAL}s). Ctrl-C to stop."
while true; do
  sleep "$INTERVAL"
  refresh || echo "  (refresh iteration failed; will retry next cycle)"
done
