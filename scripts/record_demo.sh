#!/usr/bin/env bash
#
# Record a demo video of the shell for the README.
#
# Requires a running container (default: http://localhost:8888).
# Start one first if needed:
#   docker compose up
#
# Usage:
#   scripts/record_demo.sh
#   scripts/record_demo.sh --base-url http://localhost:9000
#
# On macOS the output is assets/demo.mp4 (Apple VideoToolbox HEVC, ~seconds).
# On Linux the output is assets/demo.webm (VP9 software encode, slower).
#
# Convert to GIF manually (scale down to 1280px wide for embedding):
#   ffmpeg -i assets/darklab_shell_demo.mp4 \
#     -vf "fps=15,scale=1280:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" \
#     assets/darklab_shell_demo.gif
#
# Trim the video before converting if needed:
#   ffmpeg -i assets/darklab_shell_demo.mp4 -ss 00:00:02 -to 00:01:30 -c copy assets/darklab_shell_demo-trimmed.mp4

set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BASE_URL="${DEMO_BASE_URL:-http://localhost:8888}"
FRAMES_DIR="${DEMO_FRAMES_DIR:-/tmp/darklab_shell-demo-frames}"
PLAYWRIGHT_OUTPUT_DIR="${DEMO_PLAYWRIGHT_OUTPUT_DIR:-/tmp/darklab_shell-demo-output}"

# Parse --base-url flag
while [[ $# -gt 0 ]]; do
  case "$1" in
    --base-url)
      BASE_URL="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

# Health check
echo "Checking container at ${BASE_URL} ..."
if ! curl -sf "${BASE_URL}/health" > /dev/null 2>&1; then
  echo "Error: cannot reach ${BASE_URL} — is the container running?"
  echo "  docker compose up"
  exit 1
fi
echo "Container is up."

cd "$ROOT_DIR"

# Clear previous frames and Playwright output
rm -rf "$FRAMES_DIR" "$PLAYWRIGHT_OUTPUT_DIR"

DEMO_BASE_URL="$BASE_URL" \
DEMO_FRAMES_DIR="$FRAMES_DIR" \
DEMO_PLAYWRIGHT_OUTPUT_DIR="$PLAYWRIGHT_OUTPUT_DIR" \
RUN_DEMO=1 npx playwright test \
  --config config/playwright.demo.config.js

# ── Stitch frames into video ──────────────────────────────────────────────────
# The spec writes PNG frames to DEMO_FRAMES_DIR via page.screenshot(), which
# returns images at deviceScaleFactor resolution
# (3200×1800 for a 1600×900 viewport at deviceScaleFactor: 2).
FRAME_COUNT=$(find "$FRAMES_DIR" -name 'frame_*.png' 2>/dev/null | wc -l | tr -d ' ')

if [ "$FRAME_COUNT" -eq 0 ]; then
  echo ""
  echo "Error: no frames found in ${FRAMES_DIR} — did the test pass?"
  exit 1
fi

echo ""
echo "Stitching ${FRAME_COUNT} frames into video..."
mkdir -p "$ROOT_DIR/docs"

if [[ "$(uname -s)" == "Darwin" ]]; then
  # Apple Silicon: use VideoToolbox hardware HEVC encoder — encodes in seconds
  # instead of minutes. libvpx-vp9 software encoding does not effectively
  # parallelize on Apple Silicon and would take 30+ minutes at this resolution.
  OUT="$ROOT_DIR/assets/darklab_shell_demo.mp4"
  ffmpeg -y -framerate 15 \
    -i "$FRAMES_DIR/frame_%06d.png" \
    -c:v hevc_videotoolbox -q:v 60 \
    -tag:v hvc1 \
    "$OUT"
else
  OUT="$ROOT_DIR/assets/darklab_shell_demo.webm"
  ffmpeg -y -framerate 15 \
    -i "$FRAMES_DIR/frame_%06d.png" \
    -c:v libvpx-vp9 -b:v 0 -crf 28 \
    -cpu-used 4 -row-mt 1 -threads 0 \
    "$OUT"
fi

OUTNAME=$(basename "$OUT")
echo "Done. Final video: assets/${OUTNAME}"

echo ""
echo "Video saved to assets/${OUTNAME}"
echo ""
echo "Convert to GIF (scale down to 1280px wide for embedding, preserves aspect ratio):"
echo "  ffmpeg -i assets/${OUTNAME} \\"
echo "    -vf \"fps=15,scale=1280:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse\" \\"
echo "    assets/darklab_shell_demo.gif"
echo ""
echo "Trim before converting if needed:"
echo "  ffmpeg -i assets/${OUTNAME} -ss 00:00:02 -to 00:01:30 -c copy assets/darklab_shell_demo-trimmed.${OUTNAME##*.}"
