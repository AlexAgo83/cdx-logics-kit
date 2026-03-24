#!/usr/bin/env bash
set -euo pipefail

model="${1:-deepseek-coder-v2:16b}"
host="${OLLAMA_HOST:-http://127.0.0.1:11434}"
continue_config="${CONTINUE_CONFIG:-$HOME/.continue/config.yaml}"

status=0

note() {
  printf '%s\n' "$1"
}

check_cmd() {
  local name="$1"
  if command -v "$name" >/dev/null 2>&1; then
    note "✓ $name found"
  else
    note "✗ $name missing"
    status=1
  fi
}

note "Checking prerequisites..."
check_cmd curl
check_cmd ollama

if command -v curl >/dev/null 2>&1; then
  code="$(curl -s -o /dev/null -w "%{http_code}" "${host}/api/version" || true)"
  if [[ "$code" == "200" ]]; then
    note "✓ Ollama reachable at ${host}"
  else
    note "✗ Ollama not reachable at ${host} (HTTP ${code})"
    status=1
  fi
fi

if command -v curl >/dev/null 2>&1; then
  tags_json="$(curl -fsS "${host}/api/tags" 2>/dev/null || true)"
  if [[ -n "$tags_json" ]]; then
    if printf '%s' "$tags_json" | grep -F "\"name\":\"${model}\"" >/dev/null 2>&1; then
      note "✓ Model '${model}' is available through /api/tags"
    elif printf '%s' "$tags_json" | grep -F '"name":"deepseek-coder-v2:' >/dev/null 2>&1; then
      note "⚠ A deepseek-coder-v2 variant is installed, but not the requested tag '${model}'"
    else
      note "⚠ Model '${model}' not found through /api/tags (run: ollama pull ${model})"
    fi
  fi
fi

if command -v ollama >/dev/null 2>&1; then
  if ollama list 2>/dev/null | awk 'NR > 1 {print $1}' | grep -Fx "$model" >/dev/null 2>&1; then
    note "✓ Model '${model}' is installed locally"
  else
    note "⚠ Model '${model}' not found in 'ollama list' (run: ollama pull ${model})"
  fi
fi

if [[ -f "$continue_config" ]]; then
  note "✓ Continue config found at ${continue_config}"
  if grep -F "provider: ollama" "$continue_config" >/dev/null 2>&1; then
    note "✓ Continue config references the Ollama provider"
  else
    note "⚠ Continue config does not reference provider: ollama"
  fi

  if grep -F "model: ${model}" "$continue_config" >/dev/null 2>&1; then
    note "✓ Continue config references model: ${model}"
  elif grep -F "model: deepseek-coder-v2" "$continue_config" >/dev/null 2>&1; then
    note "⚠ Continue config references deepseek-coder-v2, but not the requested tag '${model}'"
  fi

  if grep -F "apiBase: http://localhost:11434" "$continue_config" >/dev/null 2>&1; then
    note "✓ Continue config uses the default local Ollama API base"
  fi
fi

exit "$status"
