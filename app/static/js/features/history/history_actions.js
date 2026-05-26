// darklab_shell history action helpers.
// Loaded before history.js so the drawer and Run Details modal can share the
// same starred-cache and overflow-menu helpers.

let _starredCache = null; // null = not yet loaded from server

function _getStarred() {
  return _starredCache !== null ? _starredCache : new Set();
}

function _saveStarred(set) {
  _starredCache = new Set(set);
}

function _toggleStar(cmd) {
  const s = _getStarred();
  const adding = !s.has(cmd);
  if (adding) s.add(cmd); else s.delete(cmd);
  _starredCache = s;
  // fire-and-forget server sync; UI is already updated optimistically
  apiFetch('/session/starred', {
    method: adding ? 'POST' : 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command: cmd }),
  }).catch(() => {});
}

async function loadStarredFromServer() {
  try {
    const resp = await apiFetch('/session/starred');
    if (!resp.ok) return;
    const data = await resp.json();
    _starredCache = new Set(data.commands || []);
  } catch (_) {}
}

async function reloadSessionHistory() {
  await loadStarredFromServer();
  try {
    const limit = Math.max(1, Number(APP_CONFIG.recent_commands_limit) || 50);
    const resp = await apiFetch(`/history/commands?limit=${encodeURIComponent(String(limit))}`);
    if (resp.ok) {
      const data = await resp.json();
      hydrateCmdHistory(data.runs || []);
    }
  } catch (_) {}
  if (typeof isHistoryPanelOpen === 'function' && isHistoryPanelOpen()) refreshHistoryPanel();
}

function _closeHistoryActionMenus(except = null) {
  document.querySelectorAll('.history-action-menu-wrap.open').forEach((wrap) => {
    if (except && wrap === except) return;
    wrap.classList.remove('open');
    wrap.querySelector('[data-action="history-menu"]')?.setAttribute('aria-expanded', 'false');
    _resetHistoryActionMenuPosition(wrap);
  });
}

function _closeHistoryRunActionMenus(except = null) {
  document.querySelectorAll('.history-run-action-menu-wrap.open').forEach((wrap) => {
    if (except && wrap === except) return;
    wrap.classList.remove('open');
    wrap.querySelector('.history-run-action-menu-trigger')?.setAttribute('aria-expanded', 'false');
  });
  document.querySelectorAll('.history-run-export-menu-wrap.open').forEach((wrap) => {
    if (except && wrap === except) return;
    wrap.classList.remove('open');
    wrap.querySelector('.history-run-export-menu-trigger')?.setAttribute('aria-expanded', 'false');
  });
}

function _resetHistoryActionMenuPosition(wrap) {
  const menu = wrap?.querySelector?.('.history-action-menu');
  if (!menu) return;
  menu.style.position = '';
  menu.style.left = '';
  menu.style.top = '';
  menu.style.right = '';
  menu.style.bottom = '';
}

function _positionHistoryActionMenu(wrap) {
  const trigger = wrap?.querySelector?.('[data-action="history-menu"]');
  const menu = wrap?.querySelector?.('.history-action-menu');
  if (!trigger || !menu || typeof trigger.getBoundingClientRect !== 'function') return;
  const triggerRect = trigger.getBoundingClientRect();
  const menuWidth = Math.max(180, menu.offsetWidth || 180);
  const menuHeight = Math.max(1, menu.offsetHeight || 1);
  const viewportWidth = typeof window !== 'undefined'
    ? window.innerWidth
    : document.documentElement.clientWidth;
  const viewportHeight = typeof window !== 'undefined'
    ? window.innerHeight
    : document.documentElement.clientHeight;
  const gutter = 8;
  const preferredLeft = triggerRect.left;
  const left = Math.min(
    Math.max(gutter, preferredLeft),
    Math.max(gutter, viewportWidth - menuWidth - gutter),
  );
  const belowTop = triggerRect.bottom + 4;
  const aboveTop = triggerRect.top - menuHeight - 4;
  const top = belowTop + menuHeight <= viewportHeight - gutter
    ? belowTop
    : Math.max(gutter, aboveTop);
  menu.style.position = 'fixed';
  menu.style.left = `${left}px`;
  menu.style.top = `${top}px`;
  menu.style.right = 'auto';
  menu.style.bottom = 'auto';
}
