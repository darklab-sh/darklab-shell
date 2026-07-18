// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// darklab_shell history action helpers.
// Loaded before history.js so the drawer and Run Details modal can share the
// same starred-cache and overflow-menu helpers.
import { getAppConfig as importedGetAppConfig } from '../../core/config.js';
import { isHistoryPanelOpen as importedIsHistoryPanelOpen } from '../../ui/ui_helpers.js';
import { hydrateCmdHistory as importedHydrateCmdHistory } from './history_recall.js';
import {
  apiFetch as importedRuntimeApiFetch,
  hasRuntimeHandler as importedHasRuntimeHandler,
} from '../../runtime_bridge.js';

const HISTORY_ACTIONS_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

let _starredCache = null; // null = not yet loaded from server

function _historyActionsAppConfig() {
  if (typeof importedGetAppConfig === 'function') return importedGetAppConfig();
  return HISTORY_ACTIONS_GLOBAL?.APP_CONFIG || {};
}

function _historyActionsHydrateCmdHistory(runs) {
  const hydrate = (typeof importedHydrateCmdHistory !== 'undefined' && importedHydrateCmdHistory)
    || (typeof HISTORY_ACTIONS_GLOBAL?.hydrateCmdHistory === 'function'
      ? HISTORY_ACTIONS_GLOBAL.hydrateCmdHistory
      : null);
  if (typeof hydrate === 'function') hydrate(runs);
}

function _historyActionsIsPanelOpen() {
  const isOpen = (typeof importedIsHistoryPanelOpen !== 'undefined' && importedIsHistoryPanelOpen)
    || (typeof HISTORY_ACTIONS_GLOBAL?.isHistoryPanelOpen === 'function'
      ? HISTORY_ACTIONS_GLOBAL.isHistoryPanelOpen
      : null);
  return typeof isOpen === 'function' ? isOpen() : false;
}

function _historyActionsApiFetch(...args) {
  const fetcher = (
    typeof importedHasRuntimeHandler === 'function'
    && importedHasRuntimeHandler('apiFetch')
    && typeof importedRuntimeApiFetch === 'function'
      ? importedRuntimeApiFetch
      : null
  ) || (typeof HISTORY_ACTIONS_GLOBAL?.apiFetch === 'function'
    ? HISTORY_ACTIONS_GLOBAL.apiFetch
    : null);
  return fetcher ? fetcher(...args) : Promise.reject(new Error('apiFetch unavailable'));
}

function _historyActionsRefreshHistoryPanel() {
  const refresh = typeof HISTORY_ACTIONS_GLOBAL?.refreshHistoryPanel === 'function'
    ? HISTORY_ACTIONS_GLOBAL.refreshHistoryPanel
    : null;
  if (refresh) refresh();
}

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
  _historyActionsApiFetch('/session/starred', {
    method: adding ? 'POST' : 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ command: cmd }),
  }).catch(() => {});
}

async function loadStarredFromServer() {
  try {
    const resp = await _historyActionsApiFetch('/session/starred');
    if (!resp.ok) return;
    const data = await resp.json();
    _starredCache = new Set(data.commands || []);
  } catch (_) {}
}

async function reloadSessionHistory() {
  await loadStarredFromServer();
  try {
    const config = _historyActionsAppConfig();
    const limit = Math.max(1, Number(config.recent_commands_limit) || 50);
    const resp = await _historyActionsApiFetch(`/history/commands?limit=${encodeURIComponent(String(limit))}`);
    if (resp.ok) {
      const data = await resp.json();
      _historyActionsHydrateCmdHistory(data.runs || []);
    }
  } catch (_) {}
  if (_historyActionsIsPanelOpen()) _historyActionsRefreshHistoryPanel();
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

if (typeof window !== 'undefined') {
}

export {
  _closeHistoryActionMenus,
  _closeHistoryRunActionMenus,
  _getStarred,
  _positionHistoryActionMenu,
  _resetHistoryActionMenuPosition,
  _saveStarred,
  _toggleStar,
  loadStarredFromServer,
  reloadSessionHistory,
};
