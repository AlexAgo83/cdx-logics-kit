#!/usr/bin/env bash
set -euo pipefail

model="${1:-qwen3}"
host="${OLLAMA_HOST:-http://127.0.0.1:11434}"

status=0

check_cmd() {
  local name="$1"
  if command -v "$name" >/dev/null 2>&1; then
    echo "✓ $name found"
  else
    echo "✗ $name missing"
    status=1
  fi
}

echo "Checking prerequisites…"
check_cmd node
check_cmd npm
check_cmd curl
check_cmd ollama

if command -v curl >/dev/null 2>&1; then
  code="$(curl -s -o /dev/null -w "%{http_code}" "${host}/api/version" || true)"
  if [[ "$code" == "200" ]]; then
    echo "✓ Ollama reachable at ${host}"
  else
    echo "✗ Ollama not reachable at ${host} (HTTP ${code})"
    status=1
  fi
fi

if command -v ollama >/dev/null 2>&1; then
  if ollama list 2>/dev/null | grep -E -q "^${model}\\b"; then
    echo "✓ Model '${model}' is installed"
  else
    echo "⚠ Model '${model}' not found (run: ollama pull ${model})"
  fi
fi

exit "$status"
