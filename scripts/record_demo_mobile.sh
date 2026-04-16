#!/usr/bin/env bash
#
# Record a mobile demo video of the shell for the README.
#
# Requires a running container (default: http://localhost:8888).
# Start one first if needed:
#   docker compose up
#
# Usage:
#   scripts/record_demo_mobile.sh
#   scripts/record_demo_mobile.sh --base-url http://localhost:9000
#
# The recorded video is saved to assets/demo-mobile.webm at 1179×2556 (3×
# device pixel density) — genuinely crisp on Retina displays. Playwright's
# built-in video recorder ignores deviceScaleFactor; instead the spec runs a
# background page.screenshot() loop which does respect it, and this script
# stitches the frames into a video with ffmpeg.
#
# On macOS the output is assets/darklab_shell_mobile_demo.mp4 (Apple VideoToolbox HEVC, ~seconds).
# On Linux the output is assets/darklab_shell_mobile_demo.webm (VP9 software encode, slower).
#
# Convert to GIF manually (scale down to 393px wide for embedding):
#   ffmpeg -i assets/darklab_shell_mobile_demo.mp4 \
#     -vf "fps=15,scale=393:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse" \
#     assets/darklab_shell_mobile_demo.gif
#
# Trim the video before converting if needed:
#   ffmpeg -i assets/darklab_shell_mobile_demo.mp4 -ss 00:00:02 -to 00:01:30 -c copy assets/darklab_shell_mobile_demo-trimmed.mp4

set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BASE_URL="${DEMO_BASE_URL:-http://localhost:8888}"

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

# Clear previous frames and output
rm -rf test-results/demo-mobile-frames/ test-results/demo-mobile-output/

DEMO_BASE_URL="$BASE_URL" RUN_DEMO=1 npx playwright test \
  --config config/playwright.demo.mobile.config.js

# ── Stitch frames into video ──────────────────────────────────────────────────
# The spec writes PNG frames to test-results/demo-mobile-frames/ via
# page.screenshot(), which returns images at deviceScaleFactor resolution
# (1179×2556 for a 393×852 viewport at deviceScaleFactor: 3).
FRAMES_DIR="$ROOT_DIR/test-results/demo-mobile-frames"
FRAME_COUNT=$(find "$FRAMES_DIR" -name 'frame_*.png' 2>/dev/null | wc -l | tr -d ' ')

if [ "$FRAME_COUNT" -eq 0 ]; then
  echo ""
  echo "Error: no frames found in test-results/demo-mobile-frames/ — did the test pass?"
  exit 1
fi

echo ""
echo "Stitching ${FRAME_COUNT} frames into video..."
mkdir -p "$ROOT_DIR/docs"

if [[ "$(uname -s)" == "Darwin" ]]; then
  # Apple Silicon: use VideoToolbox hardware HEVC encoder — encodes in seconds
  # instead of minutes. libvpx-vp9 software encoding does not effectively
  # parallelize on Apple Silicon and would take 30+ minutes at this resolution.
  OUT="$ROOT_DIR/assets/darklab_shell_mobile_demo.mp4"
  ffmpeg -y -framerate 15 \
    -i "$FRAMES_DIR/frame_%06d.png" \
    -c:v hevc_videotoolbox -q:v 60 \
    -tag:v hvc1 \
    "$OUT"
else
  OUT="$ROOT_DIR/assets/darklab_shell_mobile_demo.webm"
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
echo "Convert to GIF (scale down to 393px wide for embedding):"
echo "  ffmpeg -i assets/${OUTNAME} \\"
echo "    -vf \"fps=15,scale=393:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse\" \\"
echo "    assets/darklab_shell_mobile_demo.gif"
echo ""
echo "Trim before converting if needed:"
echo "  ffmpeg -i assets/${OUTNAME} -ss 00:00:02 -to 00:01:30 -c copy assets/darklab_shell_mobile_demo-trimmed.${OUTNAME##*.}"
