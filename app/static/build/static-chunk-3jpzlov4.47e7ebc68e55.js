// app/static/js/features/history/history_restore_bridge.js
var HISTORY_RESTORE_BRIDGE_GLOBAL = typeof window !== "undefined" ? window : globalThis;
var historyRestoreHandlers = HISTORY_RESTORE_BRIDGE_GLOBAL.__darklabHistoryRestoreHandlers || {
  restoreHistoryRun: null,
  restoreHistoryRunIntoTab: null
};
HISTORY_RESTORE_BRIDGE_GLOBAL.__darklabHistoryRestoreHandlers = historyRestoreHandlers;
function setHistoryRestoreHandlers(handlers = {}) {
  if (typeof handlers.restoreHistoryRun === "function" && typeof historyRestoreHandlers.restoreHistoryRun !== "function") {
    historyRestoreHandlers.restoreHistoryRun = handlers.restoreHistoryRun;
  }
  if (typeof handlers.restoreHistoryRunIntoTab === "function" && typeof historyRestoreHandlers.restoreHistoryRunIntoTab !== "function") {
    historyRestoreHandlers.restoreHistoryRunIntoTab = handlers.restoreHistoryRunIntoTab;
  }
}
function restoreHistoryRun(...args) {
  return typeof historyRestoreHandlers.restoreHistoryRun === "function" ? historyRestoreHandlers.restoreHistoryRun(...args) : void 0;
}

export {
  setHistoryRestoreHandlers,
  restoreHistoryRun
};
