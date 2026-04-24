#!/usr/bin/env bash

set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
THEME="${CAPTURE_THEME:-}"
THEME_VARIANT="${CAPTURE_THEME_VARIANT:-all}"
UI="${CAPTURE_UI:-all}"
OUT_DIR="${CAPTURE_OUT_DIR:-/tmp/darklab_shell-ui-capture}"

usage() {
  cat <<EOF
Usage:
  scripts/capture_ui_screenshots.sh [options]

Options:
  --theme <name|all|default>  Theme to capture. Unset/default uses the app default.
  --theme-variant <light|dark|all>  Restrict --theme all to one color-scheme family. Default: ${THEME_VARIANT}
  --ui <desktop|mobile|all>   Which UI pack(s) to capture. Default: all.
  --out-dir <dir>             Output directory. Relative paths resolve from repo root. Default: ${OUT_DIR}
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --theme)
      THEME="$2"
      shift 2
      ;;
    --theme-variant)
      THEME_VARIANT="$2"
      shift 2
      ;;
    --ui)
      UI="$2"
      shift 2
      ;;
    --out-dir)
      OUT_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

case "$UI" in
  desktop|mobile|all) ;;
  *)
    echo "Invalid --ui value: ${UI}" >&2
    usage >&2
    exit 1
    ;;
esac

case "$THEME_VARIANT" in
  light|dark|all) ;;
  *)
    echo "Invalid --theme-variant value: ${THEME_VARIANT}" >&2
    usage >&2
    exit 1
    ;;
esac

if [[ -n "$THEME" && "$THEME" != "all" && "$THEME" != "default" ]]; then
  if [[ ! -f "$ROOT_DIR/app/conf/themes/${THEME}.yaml" ]]; then
    echo "Unknown theme: ${THEME}" >&2
    exit 1
  fi
fi

cd "$ROOT_DIR"

mkdir -p "$OUT_DIR"

run_capture() {
  local config="$1"
  echo "Running ${config} ..."
  RUN_CAPTURE=1 CAPTURE_THEME="$THEME" CAPTURE_THEME_VARIANT="$THEME_VARIANT" CAPTURE_OUT_DIR="$OUT_DIR" \
    npx playwright test --config "$config"
}

if [[ "$UI" == "desktop" || "$UI" == "all" ]]; then
  run_capture config/playwright.capture.desktop.config.js
fi

if [[ "$UI" == "mobile" || "$UI" == "all" ]]; then
  run_capture config/playwright.capture.mobile.config.js
fi

echo ""
echo "Screenshots written to ${OUT_DIR}"
