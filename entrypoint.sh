#!/bin/sh
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

# Development mounts the checkout outside /app because native Linux preserves
# host ownership and modes on bind mounts. Stage a fresh container-owned,
# read-only snapshot before any config import or unprivileged process starts.
if [ -n "${APP_SOURCE_DIR:-}" ]; then
    /usr/local/libexec/darklab-stage-runtime-source \
        "$APP_SOURCE_DIR" /app appuser:appuser \
        || exit 1
    unset APP_SOURCE_DIR
fi

# Fix /data ownership after Docker volume mount (which resets it to root)
# and re-own any existing files (e.g. history.db created by a previous root run)
# then drop to appuser to run Gunicorn
chown -R appuser:appuser /data 2>/dev/null || true
chmod 700 /data 2>/dev/null || true

# Production installs keep the host overlay private (0700 directory, 0600
# files). Root can read that bind mount, but the app workers cannot. Stage the
# overlay tree into a private appuser-owned runtime directory before dropping
# privileges so workers can read the complete startup snapshot.
stage_local_config_overlays() {
    source_dir="${APP_LOCAL_CONF_DIR:-}"
    [ -n "$source_dir" ] || return

    [ -e "$source_dir" ] || return
    if [ ! -d "$source_dir" ] || [ -L "$source_dir" ]; then
        echo "LOCAL_CONFIG_OVERLAY_INVALID path=$source_dir" >&2
        exit 1
    fi
    invalid_entry=$(find "$source_dir" \( -type l -o \! -type d -a \! -type f \) -print -quit)
    if [ -n "$invalid_entry" ]; then
        echo "LOCAL_CONFIG_OVERLAY_INVALID path=$invalid_entry" >&2
        exit 1
    fi

    runtime_dir="/tmp/darklab-runtime-conf"
    rm -rf "$runtime_dir"
    mkdir "$runtime_dir" || {
        echo "LOCAL_CONFIG_OVERLAY_STAGE_FAILED stage=mkdir path=$runtime_dir" >&2
        exit 1
    }
    cp -R "${source_dir%/}/." "$runtime_dir/" || {
        echo "LOCAL_CONFIG_OVERLAY_STAGE_FAILED stage=copy path=$source_dir" >&2
        exit 1
    }
    chown -R appuser:appuser "$runtime_dir" || {
        echo "LOCAL_CONFIG_OVERLAY_STAGE_FAILED stage=chown path=$runtime_dir" >&2
        exit 1
    }
    if ! find "$runtime_dir" -type d -exec chmod 700 {} \; \
        || ! find "$runtime_dir" -type f -exec chmod 600 {} \;; then
        echo "LOCAL_CONFIG_OVERLAY_STAGE_FAILED stage=chmod path=$runtime_dir" >&2
        exit 1
    fi
    APP_LOCAL_CONF_DIR="$runtime_dir"
    export APP_LOCAL_CONF_DIR
}

stage_local_config_overlays

# Normalize the optional per-session workspace mount before dropping to
# appuser. Bind mounts are commonly root-owned on first boot, so app-mediated
# workspace files need their shared appuser/scanner group restored here.
repair_workspace_root() {
    workspace_root="$1"
    create_root="$2"
    if [ "$create_root" = "1" ]; then
        mkdir -p "$workspace_root" 2>/dev/null || true
    elif [ ! -d "$workspace_root" ]; then
        return
    fi
    chown appuser:appuser "$workspace_root" 2>/dev/null || true
    chmod 730 "$workspace_root" 2>/dev/null || true
    find "$workspace_root" -mindepth 1 -maxdepth 1 -type d -name 'sess_*' -exec chown appuser:appuser {} \; -exec chmod 3730 {} \; 2>/dev/null || true
    # shellcheck disable=SC2156  # session dirs are passed as sh -c positional parameters via {} +
    find "$workspace_root" -mindepth 1 -maxdepth 1 -type d -name 'sess_*' -exec sh -c '
        for session_dir do
            for child in "$session_dir"/*; do
                [ -e "$child" ] || continue
                if [ -d "$child" ] && [ ! -L "$child" ]; then
                    chown scanner:appuser "$child" 2>/tmp/workspace-repair.err \
                        || echo "WORKSPACE_REPAIR_FAILED stage=direct-child-chown path=$child error=$(cat /tmp/workspace-repair.err 2>/dev/null)" >&2
                    chmod 3770 "$child" 2>/tmp/workspace-repair.err \
                        || echo "WORKSPACE_REPAIR_FAILED stage=direct-child-chmod path=$child error=$(cat /tmp/workspace-repair.err 2>/dev/null)" >&2
                elif [ -f "$child" ]; then
                    chown scanner:appuser "$child" 2>/tmp/workspace-repair.err \
                        || echo "WORKSPACE_REPAIR_FAILED stage=direct-child-chown path=$child error=$(cat /tmp/workspace-repair.err 2>/dev/null)" >&2
                    chmod 640 "$child" 2>/tmp/workspace-repair.err \
                        || echo "WORKSPACE_REPAIR_FAILED stage=direct-child-chmod path=$child error=$(cat /tmp/workspace-repair.err 2>/dev/null)" >&2
                fi
            done
            find "$session_dir" -mindepth 1 -print0 \
                | xargs -0r chown scanner:appuser 2>/tmp/workspace-repair.err \
                || echo "WORKSPACE_REPAIR_FAILED stage=recursive-chown path=$session_dir error=$(cat /tmp/workspace-repair.err 2>/dev/null)" >&2
            find "$session_dir" -mindepth 1 -type d -print0 \
                | xargs -0r chmod 3770 2>/tmp/workspace-repair.err \
                || echo "WORKSPACE_REPAIR_FAILED stage=recursive-dir-chmod path=$session_dir error=$(cat /tmp/workspace-repair.err 2>/dev/null)" >&2
            find "$session_dir" -mindepth 1 -type f -print0 \
                | xargs -0r chmod 640 2>/tmp/workspace-repair.err \
                || echo "WORKSPACE_REPAIR_FAILED stage=recursive-file-chmod path=$session_dir error=$(cat /tmp/workspace-repair.err 2>/dev/null)" >&2
        done
    ' sh {} + || true
}

WORKSPACE_ROOT="${WORKSPACE_ROOT:-/tmp/darklab_shell-workspaces}"
repair_workspace_root "$WORKSPACE_ROOT" 1
if [ "$WORKSPACE_ROOT" != "/workspaces" ]; then
    repair_workspace_root /workspaces 0
fi

# Ensure /tmp is world-writable so the scanner user can write tool cache/config
# (nuclei templates, ProjectDiscovery config, etc.) to the tmpfs mount
chmod 1777 /tmp 2>/dev/null || true

# The release image runs one of three supported process roles. Connector
# workers share the web process's staged configuration and durable mounts, but
# they don't need the scanner user's packet capabilities or Gunicorn's helper
# workers. Dispatch them before web-only firewall and process setup.
PROCESS_ROLE_READY_FILE="/tmp/darklab-process-role.ready"
rm -f "$PROCESS_ROLE_READY_FILE"

run_process_role() {
    process_role="${DARKLAB_PROCESS_ROLE:-web}"
    case "$process_role" in
        web)
            return
            ;;
        zap-worker)
            process_module="services.connectors.zap_worker"
            ;;
        oast-worker)
            process_module="services.connectors.oast_worker"
            ;;
        *)
            echo "PROCESS_ROLE_INVALID role=$process_role" >&2
            exit 64
            ;;
    esac

    printf '%s\n' "$process_role" > "$PROCESS_ROLE_READY_FILE" || {
        echo "PROCESS_ROLE_READY_FAILED role=$process_role" >&2
        exit 1
    }
    chown root:root "$PROCESS_ROLE_READY_FILE"
    chmod 0444 "$PROCESS_ROLE_READY_FILE"
    exec gosu appuser python -m "$process_module"
}

run_process_role

RAW_PACKET_FIREWALL_READY_FILE="/tmp/darklab-raw-packet-firewall.ready"
rm -f "$RAW_PACKET_FIREWALL_READY_FILE"

# prometheus_client multiprocess mode stores per-worker metric shards here.
# The directory is on /tmp tmpfs in Compose; clear stale shards before Gunicorn
# starts so an unclean container stop cannot double-count old workers.
PROMETHEUS_MULTIPROC_DIR="${PROMETHEUS_MULTIPROC_DIR:-/tmp/darklab_shell-prom}"
mkdir -p "$PROMETHEUS_MULTIPROC_DIR" 2>/dev/null || true
find "$PROMETHEUS_MULTIPROC_DIR" -type f -name '*.db' -delete 2>/dev/null || true
chown appuser:appuser "$PROMETHEUS_MULTIPROC_DIR" 2>/dev/null || true
chmod 700 "$PROMETHEUS_MULTIPROC_DIR" 2>/dev/null || true
export PROMETHEUS_MULTIPROC_DIR

# Pre-create config/cache dirs owned by scanner so tools don't try to create
# them as root. Covers nuclei, uncover, and other tools that write to ~/.config
mkdir -p /tmp/.config/nuclei /tmp/.config/uncover /tmp/.cache
chown -R scanner:scanner /tmp/.config /tmp/.cache
chmod -R 755 /tmp/.config /tmp/.cache

# Nuclei creates a new templates directory with mode 0700, which prevents the
# appuser web process from reading the managed checksum after scanner installs
# templates. Prepare the shared root first so scanner keeps write ownership and
# appuser can traverse it to verify the exact template snapshot used by plans.
prepare_managed_nuclei_cache() {
    NUCLEI_TEMPLATES_DIR="${NUCLEI_TEMPLATES_DIR:-/tmp/nuclei-templates}"
    export NUCLEI_TEMPLATES_DIR

    if [ -L "$NUCLEI_TEMPLATES_DIR" ] \
        || { [ -e "$NUCLEI_TEMPLATES_DIR" ] && [ ! -d "$NUCLEI_TEMPLATES_DIR" ]; }; then
        echo "NUCLEI_TEMPLATE_CACHE_INVALID path=$NUCLEI_TEMPLATES_DIR" >&2
        exit 1
    fi
    mkdir -p "$NUCLEI_TEMPLATES_DIR" || {
        echo "NUCLEI_TEMPLATE_CACHE_PREPARE_FAILED stage=mkdir path=$NUCLEI_TEMPLATES_DIR" >&2
        exit 1
    }
    chown scanner:appuser "$NUCLEI_TEMPLATES_DIR" || {
        echo "NUCLEI_TEMPLATE_CACHE_PREPARE_FAILED stage=chown path=$NUCLEI_TEMPLATES_DIR" >&2
        exit 1
    }
    chmod 0750 "$NUCLEI_TEMPLATES_DIR" || {
        echo "NUCLEI_TEMPLATE_CACHE_PREPARE_FAILED stage=chmod path=$NUCLEI_TEMPLATES_DIR" >&2
        exit 1
    }
}

prepare_managed_nuclei_cache

# A fresh deployment should be able to preview reviewed Nuclei probes without
# first running a manual terminal command. Bootstrap only an empty managed
# cache; existing snapshots remain unchanged until an operator updates them.
/usr/local/libexec/darklab-bootstrap-nuclei-templates

# Block the scanner user from reaching this container's app port without
# reserving that same port on authorized remote targets. Prefer addrtype so
# loopback and every address assigned to the container stay covered. Older
# kernels fall back to explicit loopback and container addresses.
add_scanner_local_app_port_rule() {
    firewall_cmd="$1"
    address_family="$2"
    loopback_address="$3"
    command -v "$firewall_cmd" >/dev/null 2>&1 || return

    if "$firewall_cmd" -C OUTPUT -m owner --uid-owner scanner -m addrtype --dst-type LOCAL \
        -p tcp --dport "${APP_PORT:-8888}" -j REJECT --reject-with tcp-reset 2>/dev/null; then
        return
    fi
    if "$firewall_cmd" -A OUTPUT -m owner --uid-owner scanner -m addrtype --dst-type LOCAL \
        -p tcp --dport "${APP_PORT:-8888}" -j REJECT --reject-with tcp-reset 2>/dev/null; then
        return
    fi

    rule_added=0
    for local_address in "$loopback_address" $(hostname -i 2>/dev/null); do
        case "$address_family:$local_address" in
            ipv4:*:*) continue ;;
            ipv6:*:*) ;;
            ipv6:*) continue ;;
        esac
        "$firewall_cmd" -C OUTPUT -m owner --uid-owner scanner -d "$local_address" \
            -p tcp --dport "${APP_PORT:-8888}" -j REJECT --reject-with tcp-reset 2>/dev/null \
            || "$firewall_cmd" -A OUTPUT -m owner --uid-owner scanner -d "$local_address" \
                -p tcp --dport "${APP_PORT:-8888}" -j REJECT --reject-with tcp-reset 2>/dev/null \
            || continue
        rule_added=1
    done
    [ "$rule_added" = "1" ] || echo "SCANNER_LOCAL_APP_PORT_RULE_FAILED family=$address_family" >&2
}

add_scanner_local_app_port_rule iptables ipv4 127.0.0.1
add_scanner_local_app_port_rule ip6tables ipv6 ::1

# Resolve the same normalized CIDR list the Flask app will enforce. This keeps
# YAML/local-overlay configuration and environment overrides on one source of
# truth before the root-only firewall setup drops privileges.
if ! effective_restricted_cidrs="$(python -c '
from config import CFG
print("\n".join(str(value) for value in CFG.get("restricted_command_input_cidrs", [])))
')"; then
    echo "SCANNER_EGRESS_CONFIG_RESOLUTION_FAILED" >&2
    exit 1
fi

add_scanner_egress_block_rule() {
    restricted_cidr="$1"
    case "$restricted_cidr" in
        *:*) firewall_cmd="ip6tables" ;;
        *) firewall_cmd="iptables" ;;
    esac
    command -v "$firewall_cmd" >/dev/null 2>&1 || return 1
    "$firewall_cmd" -C OUTPUT -m owner --uid-owner scanner -d "$restricted_cidr" -j REJECT 2>/dev/null \
        || "$firewall_cmd" -A OUTPUT -m owner --uid-owner scanner -d "$restricted_cidr" -j REJECT 2>/dev/null \
        || return 1
    "$firewall_cmd" -C OUTPUT -m owner --uid-owner scanner -d "$restricted_cidr" -j REJECT 2>/dev/null
}

# Fail startup when the configured egress boundary cannot be installed. Raw
# Nmap also verifies the root-owned marker below before it can become active.
if [ -n "$effective_restricted_cidrs" ]; then
    firewall_failed=0
    previous_ifs="$IFS"
    IFS='
'
    for restricted_cidr in $effective_restricted_cidrs; do
        [ -n "$restricted_cidr" ] || continue
        if ! add_scanner_egress_block_rule "$restricted_cidr"; then
            echo "SCANNER_EGRESS_BLOCK_RULE_FAILED cidr=$restricted_cidr" >&2
            firewall_failed=1
        fi
    done
    IFS="$previous_ifs"
    if [ "$firewall_failed" != "0" ]; then
        exit 1
    fi
    printf '%s\n' "$effective_restricted_cidrs" > "$RAW_PACKET_FIREWALL_READY_FILE"
    chown root:root "$RAW_PACKET_FIREWALL_READY_FILE"
    chmod 0444 "$RAW_PACKET_FIREWALL_READY_FILE"
fi

WEB_CONCURRENCY="${WEB_CONCURRENCY:-4}"
WEB_THREADS="${WEB_THREADS:-4}"
export WEB_CONCURRENCY WEB_THREADS

if [ "${NOTIFICATION_WORKER_ENABLED:-1}" = "1" ]; then
    gosu appuser sh -c "
        while true; do
            python -m services.notifications.worker
            status=\$?
            echo \"notification worker exited with status \${status}; restarting in 5s\" >&2
            sleep 5
        done
    " &
fi

if [ "${SCHEDULER_ENABLED:-1}" = "1" ]; then
    gosu appuser sh -c "
        while true; do
            python -m services.scheduler.worker
            status=\$?
            echo \"scheduler worker exited with status \${status}; restarting in 5s\" >&2
            sleep 5
        done
    " &
fi

if [ "${AI_WORKER_ENABLED:-0}" = "1" ]; then
    gosu appuser sh -c "
        while true; do
            python -m services.ai.worker
            status=\$?
            echo \"AI worker exited with status \${status}; restarting in 5s\" >&2
            sleep 5
        done
    " &
fi

exec gosu appuser gunicorn \
    --config /app/gunicorn_conf.py \
    --bind "0.0.0.0:${APP_PORT:-8888}" \
    --workers "$WEB_CONCURRENCY" \
    --threads "$WEB_THREADS" \
    --timeout 3600 \
    --control-socket /tmp/.gunicorn \
    wsgi:application
