// Tracks active runs the user intentionally detached before reload restore runs.
// Loaded before pty.js and runner.js because both clear detached restore markers.
const DETACHED_ACTIVE_RUNS_STORAGE_PREFIX = 'detached_active_runs';

function _detachedActiveRunsStorageKey() {
  const sessionId = typeof SESSION_ID !== 'undefined' ? String(SESSION_ID || 'session') : 'session';
  return `${DETACHED_ACTIVE_RUNS_STORAGE_PREFIX}:${sessionId}`;
}

function _readDetachedActiveRunIds() {
  if (typeof localStorage === 'undefined') return {};
  try {
    const parsed = JSON.parse(localStorage.getItem(_detachedActiveRunsStorageKey()) || '{}');
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
  } catch (_) {
    return {};
  }
}

function _writeDetachedActiveRunIds(detached) {
  if (typeof localStorage === 'undefined') return;
  const entries = Object.entries(detached || {})
    .filter(([runId]) => String(runId || '').trim());
  try {
    if (!entries.length) {
      localStorage.removeItem(_detachedActiveRunsStorageKey());
      return;
    }
    localStorage.setItem(_detachedActiveRunsStorageKey(), JSON.stringify(Object.fromEntries(entries)));
  } catch (_) {}
}

function markActiveRunDetachedForRestore(runId) {
  const normalized = String(runId || '').trim();
  if (!normalized) return;
  const detached = _readDetachedActiveRunIds();
  detached[normalized] = Date.now();
  _writeDetachedActiveRunIds(detached);
}

function clearActiveRunDetachedForRestore(runId) {
  const normalized = String(runId || '').trim();
  if (!normalized) return;
  const detached = _readDetachedActiveRunIds();
  if (!Object.prototype.hasOwnProperty.call(detached, normalized)) return;
  delete detached[normalized];
  _writeDetachedActiveRunIds(detached);
}

function _isActiveRunDetachedForRestore(runId) {
  const normalized = String(runId || '').trim();
  if (!normalized) return false;
  return Object.prototype.hasOwnProperty.call(_readDetachedActiveRunIds(), normalized);
}

function _pruneDetachedActiveRunRestoreIds(activeRunIds) {
  const activeIds = activeRunIds instanceof Set ? activeRunIds : new Set();
  const detached = _readDetachedActiveRunIds();
  let changed = false;
  Object.keys(detached).forEach((runId) => {
    if (!activeIds.has(runId)) {
      delete detached[runId];
      changed = true;
    }
  });
  if (changed) _writeDetachedActiveRunIds(detached);
}

if (typeof window !== 'undefined') {
  Object.assign(window, {
    markActiveRunDetachedForRestore,
    clearActiveRunDetachedForRestore,
    _isActiveRunDetachedForRestore,
    _pruneDetachedActiveRunRestoreIds,
  });
}
