#!/bin/sh
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

# Prepare the swappable managed-cache directory inside the persistent Compose
# volume. Older releases mounted the live template tree at the volume root, so
# move that tree once before the web process starts.

cache_dir="${NUCLEI_TEMPLATES_DIR:-/tmp/nuclei-templates/current}"
config_dir="${NUCLEI_CONFIG_DIR:-/tmp/nuclei-templates/config/nuclei}"
volume_root="${NUCLEI_TEMPLATE_VOLUME_ROOT:-/tmp/nuclei-templates}"
python_bin="${DARKLAB_PYTHON_BIN:-/usr/local/bin/python}"

unsafe_directory() {
    path="$1"
    [ -L "$path" ] || { [ -e "$path" ] && [ ! -d "$path" ]; }
}

rollback_legacy_migration() {
    rollback_status=0
    for entry in "$migration_dir"/* "$migration_dir"/.[!.]* "$migration_dir"/..?*; do
        [ -e "$entry" ] || [ -L "$entry" ] || continue
        mv "$entry" "$volume_root/" || rollback_status=1
    done
    rmdir "$migration_dir" || rollback_status=1
    return "$rollback_status"
}

if unsafe_directory "$volume_root"; then
    echo "NUCLEI_TEMPLATE_CACHE_PREPARE_FAILED stage=volume-root" >&2
    exit 1
fi
mkdir -p "$volume_root" || {
    echo "NUCLEI_TEMPLATE_CACHE_PREPARE_FAILED stage=volume-root-mkdir" >&2
    exit 1
}
if [ "$config_dir" = "$volume_root/config/nuclei" ] \
    && unsafe_directory "$volume_root/config"; then
    echo "NUCLEI_TEMPLATE_CACHE_PREPARE_FAILED stage=config-root" >&2
    exit 1
fi

if [ "$cache_dir" = "$volume_root/current" ] \
    && [ ! -e "$cache_dir" ] \
    && [ ! -L "$cache_dir" ] \
    && [ -f "$volume_root/.checksum" ] \
    && [ ! -L "$volume_root/.checksum" ]; then
    migration_dir="$volume_root/.darklab-nuclei-migration"
    if [ -e "$migration_dir" ] || [ -L "$migration_dir" ]; then
        echo "NUCLEI_TEMPLATE_CACHE_PREPARE_FAILED stage=legacy-migration-state" >&2
        exit 1
    fi
    mkdir "$migration_dir" || {
        echo "NUCLEI_TEMPLATE_CACHE_PREPARE_FAILED stage=legacy-migration-mkdir" >&2
        exit 1
    }
    for entry in "$volume_root"/* "$volume_root"/.[!.]* "$volume_root"/..?*; do
        [ -e "$entry" ] || [ -L "$entry" ] || continue
        [ "$entry" = "$migration_dir" ] && continue
        [ "$entry" = "$volume_root/config" ] && continue
        mv "$entry" "$migration_dir/" || {
            echo "NUCLEI_TEMPLATE_CACHE_PREPARE_FAILED stage=legacy-migration-move" >&2
            rollback_legacy_migration || \
                echo "NUCLEI_TEMPLATE_CACHE_PREPARE_FAILED stage=legacy-migration-rollback" >&2
            exit 1
        }
    done
    if ! NUCLEI_TEMPLATE_MIGRATION_DIR="$migration_dir" \
        NUCLEI_TEMPLATE_MIGRATION_SOURCE="$volume_root" \
        NUCLEI_TEMPLATE_MIGRATION_DESTINATION="$cache_dir" \
        "$python_bin" -c '
import os
from pathlib import Path
from services.nuclei.template_refresh_files import rebase_staged_template_manifest
rebase_staged_template_manifest(
    Path(os.environ["NUCLEI_TEMPLATE_MIGRATION_DIR"]),
    Path(os.environ["NUCLEI_TEMPLATE_MIGRATION_DESTINATION"]),
    recorded_root=Path(os.environ["NUCLEI_TEMPLATE_MIGRATION_SOURCE"]),
)
'; then
        echo "NUCLEI_TEMPLATE_CACHE_PREPARE_FAILED stage=legacy-migration-manifest" >&2
        rollback_legacy_migration || \
            echo "NUCLEI_TEMPLATE_CACHE_PREPARE_FAILED stage=legacy-migration-rollback" >&2
        exit 1
    fi
    mv "$migration_dir" "$cache_dir" || {
        echo "NUCLEI_TEMPLATE_CACHE_PREPARE_FAILED stage=legacy-migration-commit" >&2
        exit 1
    }
    echo "NUCLEI_TEMPLATE_CACHE_MIGRATED"
fi

for path in "$cache_dir" "$config_dir"; do
    if unsafe_directory "$path"; then
        echo "NUCLEI_TEMPLATE_CACHE_PREPARE_FAILED stage=unsafe-directory" >&2
        exit 1
    fi
    mkdir -p "$path" || {
        echo "NUCLEI_TEMPLATE_CACHE_PREPARE_FAILED stage=mkdir" >&2
        exit 1
    }
    chown scanner:appuser "$path" || {
        echo "NUCLEI_TEMPLATE_CACHE_PREPARE_FAILED stage=chown" >&2
        exit 1
    }
    chmod 0750 "$path" || {
        echo "NUCLEI_TEMPLATE_CACHE_PREPARE_FAILED stage=chmod" >&2
        exit 1
    }
done

for metadata in "$cache_dir/.checksum" "$config_dir/.templates-config.json"; do
    if [ ! -f "$metadata" ] || [ -L "$metadata" ]; then
        continue
    fi
    chown scanner:appuser "$metadata" || {
        echo "NUCLEI_TEMPLATE_CACHE_PREPARE_FAILED stage=metadata-chown" >&2
        exit 1
    }
    chmod 0640 "$metadata" || {
        echo "NUCLEI_TEMPLATE_CACHE_PREPARE_FAILED stage=metadata-chmod" >&2
        exit 1
    }
done

# The scanner creates sibling stage and backup directories during refresh.
chown scanner:appuser "$volume_root" || {
    echo "NUCLEI_TEMPLATE_CACHE_PREPARE_FAILED stage=volume-root-chown" >&2
    exit 1
}
chmod 0750 "$volume_root" || {
    echo "NUCLEI_TEMPLATE_CACHE_PREPARE_FAILED stage=volume-root-chmod" >&2
    exit 1
}
