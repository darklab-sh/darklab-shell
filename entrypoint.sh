#!/bin/sh
# Fix /data ownership after Docker volume mount (which resets it to root)
# and re-own any existing files (e.g. history.db created by a previous root run)
# then drop to appuser to run Gunicorn
chown -R appuser:appuser /data 2>/dev/null || true
chmod 700 /data 2>/dev/null || true

# Ensure /tmp is world-writable so the scanner user can write tool cache/config
# (nuclei templates, wapiti sessions, etc.) to the tmpfs mount
chmod 1777 /tmp 2>/dev/null || true

exec gosu appuser gunicorn --bind 0.0.0.0:8888 --workers 4 --threads 4 --timeout 3600 --control-socket /tmp/.gunicorn app:app
