#!/usr/bin/env sh
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

set -eu

if [ "$#" -ne 1 ] || [ -z "$1" ]; then
    echo "usage: create_portable_build_context.sh OUTPUT_TAR" >&2
    exit 2
fi

script_dir=$(CDPATH= cd "$(dirname "$0")" && pwd)
repo_root=$(CDPATH= cd "$script_dir/../.." && pwd)

git -C "$repo_root" -c tar.umask=0022 archive --format=tar HEAD > "$1"
