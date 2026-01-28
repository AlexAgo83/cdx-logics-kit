#!/usr/bin/env bash
set -euo pipefail

model="${1:-qwen3}"
dry="${DRY_RUN:-}"

run() {
  if [[ -n "$dry" ]]; then
    echo "+ $*"
  else
    "$@"
  fi
}

if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required. Install it from https://brew.sh and re-run."
  exit 1
fi

if ! command -v ollama >/dev/null 2>&1; then
  run brew install ollama
fi

if brew services list >/dev/null 2>&1; then
  run brew services start ollama
else
  echo "brew services not available; start Ollama manually with: ollama serve"
fi

if [[ -n "${model}" ]]; then
  run ollama pull "${model}"
fi

echo "Done. Ollama default URL: ${OLLAMA_HOST:-http://127.0.0.1:11434}"
