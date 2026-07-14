// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Neutral History restore boundary for lazy consumers.

const HISTORY_RESTORE_BRIDGE_GLOBAL = typeof window !== 'undefined' ? window : globalThis;
const historyRestoreHandlers = HISTORY_RESTORE_BRIDGE_GLOBAL.__darklabHistoryRestoreHandlers || {
  restoreHistoryRun: null,
  restoreHistoryRunIntoTab: null,
};
HISTORY_RESTORE_BRIDGE_GLOBAL.__darklabHistoryRestoreHandlers = historyRestoreHandlers;

function setHistoryRestoreHandlers(handlers = {}) {
  if (typeof handlers.restoreHistoryRun === 'function' && typeof historyRestoreHandlers.restoreHistoryRun !== 'function') {
    historyRestoreHandlers.restoreHistoryRun = handlers.restoreHistoryRun;
  }
  if (typeof handlers.restoreHistoryRunIntoTab === 'function' && typeof historyRestoreHandlers.restoreHistoryRunIntoTab !== 'function') {
    historyRestoreHandlers.restoreHistoryRunIntoTab = handlers.restoreHistoryRunIntoTab;
  }
}

function restoreHistoryRun(...args) {
  return typeof historyRestoreHandlers.restoreHistoryRun === 'function'
    ? historyRestoreHandlers.restoreHistoryRun(...args)
    : undefined;
}

function restoreHistoryRunIntoTab(...args) {
  return typeof historyRestoreHandlers.restoreHistoryRunIntoTab === 'function'
    ? historyRestoreHandlers.restoreHistoryRunIntoTab(...args)
    : undefined;
}

export {
  restoreHistoryRun,
  restoreHistoryRunIntoTab,
  setHistoryRestoreHandlers,
};
