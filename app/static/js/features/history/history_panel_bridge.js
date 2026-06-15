// Neutral History drawer boundary for runtime consumers that can't import the
// drawer owner directly without creating broad cycles.

const HISTORY_PANEL_BRIDGE_GLOBAL = typeof window !== 'undefined' ? window : globalThis;
const historyPanelHandlers = HISTORY_PANEL_BRIDGE_GLOBAL.__darklabHistoryPanelHandlers || {
  openHistoryWithFilters: null,
  refreshHistoryPanel: null,
  renderHistory: null,
  resetHistoryMobileFilters: null,
  resetHistorySelectionOnClose: null,
};
HISTORY_PANEL_BRIDGE_GLOBAL.__darklabHistoryPanelHandlers = historyPanelHandlers;

function setHistoryPanelHandlers(handlers = {}) {
  Object.keys(historyPanelHandlers).forEach((name) => {
    if (typeof handlers[name] === 'function' && typeof historyPanelHandlers[name] !== 'function') {
      historyPanelHandlers[name] = handlers[name];
    }
  });
}

function hasHistoryPanelHandler(name) {
  return typeof historyPanelHandlers[name] === 'function';
}

function openHistoryWithFilters(...args) {
  return typeof historyPanelHandlers.openHistoryWithFilters === 'function'
    ? historyPanelHandlers.openHistoryWithFilters(...args)
    : undefined;
}

function refreshHistoryPanel(...args) {
  return typeof historyPanelHandlers.refreshHistoryPanel === 'function'
    ? historyPanelHandlers.refreshHistoryPanel(...args)
    : undefined;
}

function renderHistory(...args) {
  return typeof historyPanelHandlers.renderHistory === 'function'
    ? historyPanelHandlers.renderHistory(...args)
    : undefined;
}

function resetHistoryMobileFilters(...args) {
  return typeof historyPanelHandlers.resetHistoryMobileFilters === 'function'
    ? historyPanelHandlers.resetHistoryMobileFilters(...args)
    : undefined;
}

function resetHistorySelectionOnClose(...args) {
  return typeof historyPanelHandlers.resetHistorySelectionOnClose === 'function'
    ? historyPanelHandlers.resetHistorySelectionOnClose(...args)
    : undefined;
}

export {
  hasHistoryPanelHandler,
  openHistoryWithFilters,
  refreshHistoryPanel,
  renderHistory,
  resetHistoryMobileFilters,
  resetHistorySelectionOnClose,
  setHistoryPanelHandlers,
};
