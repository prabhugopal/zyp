#!/usr/bin/env bash
# Starts Zyp locally. Runs in the foreground (Ctrl+C to stop).
#
# Usage:
#   ./start.sh                start on the default port (5055)
#   ./start.sh --port 9090    start on a different port
set -euo pipefail
cd "$(dirname "$0")"

PORT=5055
while [[ $# -gt 0 ]]; do
	case "$1" in
	--port)
		PORT="$2"
		shift 2
		;;
	*)
		echo "Unknown argument: $1" >&2
		echo "Usage: $0 [--port N]" >&2
		exit 1
		;;
	esac
done

if ! command -v uv >/dev/null 2>&1; then
	echo "uv is required. Install it: https://docs.astral.sh/uv/getting-started/installation/" >&2
	exit 1
fi

if ! redis-cli ping >/dev/null 2>&1; then
	echo "Redis isn't reachable at the default location." >&2
	if command -v brew >/dev/null 2>&1 && brew list redis >/dev/null 2>&1; then
		echo "Starting it via: brew services start redis"
		brew services start redis
		sleep 1
	else
		echo "Install and start Redis first (e.g. brew install redis && brew services start redis)." >&2
		exit 1
	fi
fi

if command -v lsof >/dev/null 2>&1 && lsof -ti:"$PORT" >/dev/null 2>&1; then
	echo "Port $PORT is already in use. Stop whatever's running there first, e.g.:" >&2
	echo "  lsof -ti:$PORT | xargs kill" >&2
	echo "...or start on a different port: $0 --port 9090" >&2
	exit 1
fi

echo "Starting Zyp on port $PORT (Ctrl+C to stop)..."
exec uv run uvicorn app:app --port "$PORT"
