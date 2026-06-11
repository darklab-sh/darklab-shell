#!/usr/bin/env bash
set -euo pipefail

stop_servers=1
has_config=0
ui_mode=0
ci_mode=0
webserver_logs=0
force_color=0
serial_mode=0
web_server_timeout=""
playwright_args=()

while (($#)); do
  case "$1" in
    --ci)
      ci_mode=1
      shift
      ;;
    --debug-logs|--webserver-logs)
      webserver_logs=1
      shift
      ;;
    --force-color)
      force_color=1
      shift
      ;;
    --serial)
      serial_mode=1
      shift
      ;;
    --server-timeout)
      shift
      if (($# == 0)); then
        echo "run_playwright.sh: --server-timeout requires milliseconds" >&2
        exit 2
      fi
      web_server_timeout="$1"
      shift
      ;;
    --server-timeout=*)
      web_server_timeout="${1#--server-timeout=}"
      shift
      ;;
    --no-stop-servers)
      stop_servers=0
      shift
      ;;
    --config)
      has_config=1
      playwright_args+=("$1")
      shift
      if (($#)); then
        playwright_args+=("$1")
        shift
      fi
      ;;
    --config=*)
      has_config=1
      playwright_args+=("$1")
      shift
      ;;
    --ui)
      ui_mode=1
      playwright_args+=("$1")
      shift
      ;;
    *)
      playwright_args+=("$1")
      shift
      ;;
  esac
done

if ((has_config == 0)); then
  playwright_args=(--config .tooling/playwright.parallel.config.js "${playwright_args[@]}")
fi

if ((webserver_logs)); then
  export PW_WEBSERVER_LOGS=1
else
  unset PW_WEBSERVER_LOGS
fi

if ((ci_mode)) && [[ "$ui_mode" -eq 0 ]]; then
  export CI=1
fi

if ((force_color)); then
  export FORCE_COLOR=1
  unset NO_COLOR
else
  unset FORCE_COLOR
  unset NO_COLOR
fi

if ((serial_mode)); then
  export PLAYWRIGHT_PROJECT_COUNT=1
fi

# Playwright's optional TS/ESM transform loader uses Node's deprecated
# module.register() API under Node 26. The e2e suite is plain JS, so skip it.
export PW_DISABLE_TS_ESM="${PW_DISABLE_TS_ESM:-1}"

if [[ -n "$web_server_timeout" ]]; then
  if [[ ! "$web_server_timeout" =~ ^[0-9]+$ || "$web_server_timeout" -lt 1000 ]]; then
    echo "run_playwright.sh: --server-timeout must be an integer >= 1000" >&2
    exit 2
  fi
  export PLAYWRIGHT_WEB_SERVER_TIMEOUT="$web_server_timeout"
fi

ASSET_BUNDLE_MODE="${ASSET_BUNDLE_MODE:-${PW_ASSET_BUNDLE_MODE:-}}"
if [[ "$ASSET_BUNDLE_MODE" == "bundle" ]]; then
  if ! npm run assets:check; then
    echo "run_playwright.sh: asset_bundle_mode=bundle requires current committed build output; run assets:sync" >&2
    exit 1
  fi
  export ASSET_BUNDLE_MODE
fi

if [[ -z "${PW_E2E_SERVER_LOG_DIR:-}" ]]; then
  PW_E2E_SERVER_LOG_DIR="$PWD/test-results/e2e-server-logs/$(date +%Y%m%d-%H%M%S)-$$"
  export PW_E2E_SERVER_LOG_DIR
fi
mkdir -p "$PW_E2E_SERVER_LOG_DIR"

print_server_diagnostics() {
  local log_dir="${PW_E2E_SERVER_LOG_DIR:-}"
  local tail_lines="${PW_E2E_SERVER_LOG_TAIL_LINES:-120}"
  [[ -n "$log_dir" && -d "$log_dir" ]] || return 0

  shopt -s nullglob
  local logs=("$log_dir"/*.log)
  shopt -u nullglob
  ((${#logs[@]})) || return 0

  printf '\n[e2e] isolated server log tails from %s\n' "$log_dir" >&2
  for log in "${logs[@]}"; do
    printf '\n[e2e] ---- %s ----\n' "${log#"$PWD"/}" >&2
    tail -n "$tail_lines" "$log" >&2 || true
  done
}

if ((stop_servers)); then
  bash scripts/playwright/stop_e2e_servers.sh \
    "${PLAYWRIGHT_PROJECT_COUNT:-5}" \
    "${PLAYWRIGHT_BASE_PORT:-5001}"
fi

if [[ -x node_modules/.bin/playwright ]]; then
  runner=(node_modules/.bin/playwright)
else
  runner=(npx playwright)
fi

set +e
"${runner[@]}" test "${playwright_args[@]}"
status=$?
set -e

if ((status != 0)); then
  print_server_diagnostics
fi

exit "$status"
