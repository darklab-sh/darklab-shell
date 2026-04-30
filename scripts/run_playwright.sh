#!/usr/bin/env bash
set -euo pipefail

stop_servers=1
has_config=0
ui_mode=0
ci_mode=0
webserver_logs=0
force_color=0
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
  playwright_args=(--config config/playwright.parallel.config.js "${playwright_args[@]}")
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

if ((stop_servers)); then
  bash scripts/playwright/stop_e2e_servers.sh \
    "${PLAYWRIGHT_PROJECT_COUNT:-5}" \
    "${PLAYWRIGHT_BASE_PORT:-5001}"
fi

if [[ -x node_modules/.bin/playwright ]]; then
  exec node_modules/.bin/playwright test "${playwright_args[@]}"
fi

exec npx playwright test "${playwright_args[@]}"
