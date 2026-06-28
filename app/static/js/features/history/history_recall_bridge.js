// Neutral command-recall boundary for shared UI helpers.

const HISTORY_RECALL_BRIDGE_GLOBAL = typeof window !== 'undefined' ? window : globalThis;
const historyRecallHandlers = HISTORY_RECALL_BRIDGE_GLOBAL.__darklabHistoryRecallHandlers || {
  resetCmdHistoryNav: null,
};
HISTORY_RECALL_BRIDGE_GLOBAL.__darklabHistoryRecallHandlers = historyRecallHandlers;

function setHistoryRecallHandlers(handlers = {}) {
  if (typeof handlers.resetCmdHistoryNav === 'function') {
    historyRecallHandlers.resetCmdHistoryNav = handlers.resetCmdHistoryNav;
  }
}

function resetCmdHistoryNav(...args) {
  return typeof historyRecallHandlers.resetCmdHistoryNav === 'function'
    ? historyRecallHandlers.resetCmdHistoryNav(...args)
    : undefined;
}

export {
  resetCmdHistoryNav,
  setHistoryRecallHandlers,
};
