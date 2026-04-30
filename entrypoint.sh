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
# (nuclei templates, wapiti sessions, etc.) to the tmpfs mount
chmod 1777 /tmp 2>/dev/null || true

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

exec gosu appuser gunicorn --bind "0.0.0.0:${APP_PORT:-8888}" --workers "${WEB_CONCURRENCY:-4}" --threads "${WEB_THREADS:-4}" --timeout 3600 --control-socket /tmp/.gunicorn app:app
