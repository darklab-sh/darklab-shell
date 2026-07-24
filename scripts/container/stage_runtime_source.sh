#!/bin/sh
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

set -eu

source_dir="${1:-}"
runtime_dir="${2:-}"
runtime_owner="${3:-appuser:appuser}"

stage_failed() {
    stage="$1"
    echo "DEVELOPMENT_SOURCE_STAGE_FAILED stage=$stage source=$source_dir destination=$runtime_dir" >&2
    exit 1
}

if [ -z "$source_dir" ] || [ ! -d "$source_dir" ] || [ -L "$source_dir" ]; then
    stage_failed "validate-source"
fi
if [ -z "$runtime_dir" ] || [ ! -d "$runtime_dir" ] || [ -L "$runtime_dir" ]; then
    stage_failed "validate-runtime"
fi
if [ "$source_dir" = "$runtime_dir" ]; then
    stage_failed "separate-paths"
fi

find "$runtime_dir" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} + \
    || stage_failed "clear"
cp -R "${source_dir%/}/." "$runtime_dir/" \
    || stage_failed "copy"

if [ ! -f "$runtime_dir/wsgi.py" ] || [ ! -f "$runtime_dir/config.py" ]; then
    stage_failed "validate-copy"
fi

chown -R "$runtime_owner" "$runtime_dir" \
    || stage_failed "chown"

# Preserve source read/execute privacy while removing every write bit. A host
# file with mode 0600 therefore becomes an appuser-owned 0400 runtime file,
# while ordinary 0644 source remains readable to the same users as the image.
chmod -R u+rX,a-w "$runtime_dir" \
    || stage_failed "chmod"
