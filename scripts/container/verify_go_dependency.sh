#!/bin/sh
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

set -eu

if [ "$#" -ne 3 ]; then
    echo "usage: verify_go_dependency.sh BINARY MODULE VERSION" >&2
    exit 2
fi

binary=$1
module=$2
version=$3
build_info=$(go version -m "$binary")

# A dep line can name the requested version while a following replacement
# actually supplies different code. Accept only the exact, unreplaced module.
if ! printf '%s\n' "$build_info" | awk -v module="$module" -v version="$version" '
    $1 == "dep" && $2 == module {
        found++
        matches = ($3 == version)
        selected = 1
        next
    }
    selected && $1 == "=>" { replaced = 1 }
    $1 == "dep" || $1 == "mod" || $1 == "build" { selected = 0 }
    END { exit !(found == 1 && matches && !replaced) }
'; then
    printf 'Go binary dependency mismatch: binary=%s module=%s expected=%s (missing, different, or replaced)\n' \
        "$binary" "$module" "$version" >&2
    exit 1
fi

printf 'Verified Go binary dependency: binary=%s module=%s version=%s\n' \
    "$binary" "$module" "$version"
