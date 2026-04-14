#!/bin/bash
set -euo pipefail

COUNT="${1:-2}"
BASE_PORT="${2:-5001}"

pids=()

for ((i=0; i<COUNT; i++)); do
  PORT=$((BASE_PORT + i))
  PORT_PIDS="$(lsof -ti tcp:${PORT} 2>/dev/null || true)"
  if [[ -n "$PORT_PIDS" ]]; then
    while IFS= read -r pid; do
      pids+=("$pid")
    done <<< "$PORT_PIDS"
  fi
done

if (( ${#pids[@]} )); then
  kill "${pids[@]}" 2>/dev/null || true
fi
