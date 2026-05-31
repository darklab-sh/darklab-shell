#!/bin/sh
# Fix /data ownership after Docker volume mount (which resets it to root)
# and re-own any existing files (e.g. history.db created by a previous root run)
# then drop to appuser to run Gunicorn
chown -R appuser:appuser /data 2>/dev/null || true
chmod 700 /data 2>/dev/null || true

# Normalize the optional per-session workspace mount before dropping to
# appuser. Bind mounts are commonly root-owned on first boot, so app-mediated
# workspace files need their shared appuser/scanner group restored here.
WORKSPACE_ROOT="${WORKSPACE_ROOT:-/tmp/darklab_shell-workspaces}"
mkdir -p "$WORKSPACE_ROOT" 2>/dev/null || true
chown appuser:appuser "$WORKSPACE_ROOT" 2>/dev/null || true
chmod 730 "$WORKSPACE_ROOT" 2>/dev/null || true
find "$WORKSPACE_ROOT" -mindepth 1 -maxdepth 1 -type d -name 'sess_*' -exec chown appuser:appuser {} \; -exec chmod 3730 {} \; 2>/dev/null || true
# shellcheck disable=SC2156  # session dirs are passed as sh -c positional parameters via {} +
find "$WORKSPACE_ROOT" -mindepth 1 -maxdepth 1 -type d -name 'sess_*' -exec sh -c '
    for session_dir do
        find "$session_dir" -mindepth 1 -exec chown scanner:appuser {} \;
        find "$session_dir" -mindepth 1 -type d -exec chmod 3770 {} \;
        find "$session_dir" -mindepth 1 -type f -exec chmod 640 {} \;
    done
' sh {} + 2>/dev/null || true

# Ensure /tmp is world-writable so the scanner user can write tool cache/config
# (nuclei templates, ProjectDiscovery config, etc.) to the tmpfs mount
chmod 1777 /tmp 2>/dev/null || true

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

# Block the scanner user from making outbound TCP connections to the app port.
# This prevents commands run via the web shell from curling internal endpoints
# like /diag, /config, or /history directly. The rule runs as root before the
# gosu drop, so iptables is available. The || true keeps startup safe if the
# kernel module is absent in unusual environments.
iptables -A OUTPUT -m owner --uid-owner scanner -p tcp --dport "${APP_PORT:-8888}" -j REJECT --reject-with tcp-reset 2>/dev/null || true

# Optional operator-defined scanner egress block. This is the network-layer
# backstop for targets that arrive through DNS, CNAMEs, tool-managed resolver
# input, or raw workspace files where command parsing cannot prove intent.
if [ -n "${RESTRICTED_COMMAND_INPUT_CIDRS:-}" ]; then
    printf '%s\n' "$RESTRICTED_COMMAND_INPUT_CIDRS" | tr ',' '\n' | while IFS= read -r restricted_cidr; do
        restricted_cidr="$(printf '%s' "$restricted_cidr" | xargs)"
        [ -n "$restricted_cidr" ] || continue
        case "$restricted_cidr" in
            *:*)
                if command -v ip6tables >/dev/null 2>&1; then
                    ip6tables -C OUTPUT -m owner --uid-owner scanner -d "$restricted_cidr" -j REJECT 2>/dev/null \
                        || ip6tables -A OUTPUT -m owner --uid-owner scanner -d "$restricted_cidr" -j REJECT 2>/dev/null \
                        || echo "SCANNER_EGRESS_BLOCK_RULE_FAILED cidr=$restricted_cidr" >&2
                fi
                ;;
            *)
                iptables -C OUTPUT -m owner --uid-owner scanner -d "$restricted_cidr" -j REJECT 2>/dev/null \
                    || iptables -A OUTPUT -m owner --uid-owner scanner -d "$restricted_cidr" -j REJECT 2>/dev/null \
                    || echo "SCANNER_EGRESS_BLOCK_RULE_FAILED cidr=$restricted_cidr" >&2
                ;;
        esac
    done
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
    app:app
