#!/usr/bin/env bash
# One-time (idempotent) environment setup: installs Ollama, starts it, pulls the local model, and
# syncs the uv-managed Python environment. Safe to re-run.
#
# Usage:
#   ./setup.sh                 set up everything
#   ./setup.sh --skip-ollama   only sync the Python env (use with model_provider: anthropic)
set -euo pipefail
cd "$(dirname "$0")"

DEFAULT_MODEL="llama3.2:3b"
SKIP_OLLAMA=false
for arg in "$@"; do
	case "$arg" in
	--skip-ollama) SKIP_OLLAMA=true ;;
	*)
		echo "Unknown argument: $arg" >&2
		echo "Usage: $0 [--skip-ollama]" >&2
		exit 1
		;;
	esac
done

if ! command -v uv >/dev/null 2>&1; then
	echo "uv is required. Install it: https://docs.astral.sh/uv/getting-started/installation/" >&2
	exit 1
fi

if [ "$SKIP_OLLAMA" = false ]; then
	if ! command -v ollama >/dev/null 2>&1 && ! command -v brew >/dev/null 2>&1; then
		echo "Neither ollama nor brew found. Install Ollama manually from https://ollama.com," >&2
		echo "or re-run with --skip-ollama to use model_provider: anthropic instead." >&2
		exit 1
	fi

	if ! command -v ollama >/dev/null 2>&1; then
		echo "Installing Ollama via Homebrew..."
		brew install ollama
	else
		echo "Ollama already installed."
	fi

	if ! curl -s -o /dev/null --max-time 2 http://localhost:11434/api/version; then
		echo "Starting the Ollama service..."
		if command -v brew >/dev/null 2>&1; then
			brew services start ollama
		else
			echo "Start it yourself: ollama serve &" >&2
		fi
		for _ in $(seq 1 10); do
			curl -s -o /dev/null --max-time 2 http://localhost:11434/api/version && break
			sleep 1
		done
	else
		echo "Ollama service already running."
	fi

	if ollama list 2>/dev/null | awk '{print $1}' | grep -qx "$DEFAULT_MODEL"; then
		echo "Model $DEFAULT_MODEL already pulled."
	else
		echo "Pulling $DEFAULT_MODEL (~2GB, one-time download)..."
		ollama pull "$DEFAULT_MODEL"
	fi
fi

echo "Syncing Python environment..."
uv sync

echo ""
echo "Setup complete. Next steps:"
echo "  uv run python cli.py run --scenario greenfield"
echo ""
echo "Model backend defaults to local Ollama ($DEFAULT_MODEL, zero cost)."
echo "To use Claude instead, set in config.yaml: model_provider: anthropic (needs ANTHROPIC_API_KEY)."
