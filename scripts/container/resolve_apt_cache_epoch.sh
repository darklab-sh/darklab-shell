#!/usr/bin/env sh
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

set -eu

if [ "$#" -ne 1 ]; then
    echo "usage: resolve_apt_cache_epoch.sh YYYY-MM-DD[THH:MM:SSZ]" >&2
    exit 2
fi

value=$1
case "$value" in
    ????-??-??) epoch=$value ;;
    ????-??-??T*) epoch=${value%%T*} ;;
    *)
        echo "APT cache epoch must start with YYYY-MM-DD" >&2
        exit 2
        ;;
esac

case "$epoch" in
    [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) ;;
    *)
        echo "APT cache epoch must use YYYY-MM-DD" >&2
        exit 2
        ;;
esac

printf '%s\n' "$epoch"
