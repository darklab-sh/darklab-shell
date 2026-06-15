// Neutral compare-action boundary shared by launcher and project run rows.

let fetchAndRenderHistoryComparisonHandler = null;
let openHistoryCompareLauncherHandler = null;

function setHistoryCompareHandlers(handlers = {}) {
  if (typeof handlers.fetchAndRenderHistoryComparison === 'function') {
    fetchAndRenderHistoryComparisonHandler = handlers.fetchAndRenderHistoryComparison;
  }
  if (typeof handlers.openHistoryCompareLauncher === 'function') {
    openHistoryCompareLauncherHandler = handlers.openHistoryCompareLauncher;
  }
}

function fetchAndRenderHistoryComparison(...args) {
  return typeof fetchAndRenderHistoryComparisonHandler === 'function'
    ? fetchAndRenderHistoryComparisonHandler(...args)
    : undefined;
}

function openHistoryCompareLauncher(...args) {
  return typeof openHistoryCompareLauncherHandler === 'function'
    ? openHistoryCompareLauncherHandler(...args)
    : undefined;
}

export {
  fetchAndRenderHistoryComparison,
  openHistoryCompareLauncher,
  setHistoryCompareHandlers,
};
