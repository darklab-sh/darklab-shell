#!/bin/sh
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

# Populate the managed Nuclei cache once without making app startup depend on
# ProjectDiscovery. The caller prepares the cache directory and remains
# responsible for starting the app even when this helper cannot download it.

cache_dir="${NUCLEI_TEMPLATES_DIR:-/tmp/nuclei-templates}"
manifest="$cache_dir/.checksum"

case "${NUCLEI_TEMPLATE_BOOTSTRAP_ENABLED:-true}" in
    1|true|TRUE|yes|YES|on|ON)
        ;;
    0|false|FALSE|no|NO|off|OFF)
        echo "NUCLEI_TEMPLATE_BOOTSTRAP_SKIPPED reason=disabled"
        exit 0
        ;;
    *)
        echo "NUCLEI_TEMPLATE_BOOTSTRAP_FAILED reason=invalid_enabled_value" >&2
        exit 0
        ;;
esac

if [ -L "$manifest" ]; then
    echo "NUCLEI_TEMPLATE_BOOTSTRAP_FAILED reason=unsafe_manifest" >&2
    exit 0
fi
if [ -s "$manifest" ] && [ -f "$manifest" ]; then
    echo "NUCLEI_TEMPLATE_BOOTSTRAP_SKIPPED reason=cache_present"
    exit 0
fi

echo "NUCLEI_TEMPLATE_BOOTSTRAP_STARTED"
if timeout 180 gosu scanner env \
    HOME=/tmp \
    XDG_CONFIG_HOME=/tmp/.config \
    nuclei -update-templates -ud "$cache_dir"; then
    if [ -s "$manifest" ] && [ -f "$manifest" ] && [ ! -L "$manifest" ]; then
        echo "NUCLEI_TEMPLATE_BOOTSTRAP_SUCCEEDED"
    else
        echo "NUCLEI_TEMPLATE_BOOTSTRAP_FAILED reason=manifest_missing_after_update" >&2
    fi
else
    status=$?
    echo "NUCLEI_TEMPLATE_BOOTSTRAP_FAILED reason=update_failed exit_status=$status" >&2
fi

# Missing templates make Nuclei plans unavailable, but they must not prevent
# the rest of darklab_shell from starting.
exit 0
