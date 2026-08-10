#!/bin/sh
# Start des API-Containers: erst Schema, dann Server.
#
# Die Migration laeuft bewusst hier und nicht als separater Release-Schritt.
# Bei einem Single-User-Dienst mit genau einer Instanz gibt es kein
# Nebenlaeufigkeitsproblem, und ein vergessener Release-Schritt waere die
# wahrscheinlichere Fehlerquelle als eine doppelt laufende Migration.
set -e

echo "[entrypoint] alembic upgrade head"
alembic upgrade head

PORT="${PORT:-8000}"
echo "[entrypoint] uvicorn auf 0.0.0.0:${PORT}"
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT}"
