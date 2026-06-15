// app/static/js/features/run-comparison/history_compare_bridge.js
var fetchAndRenderHistoryComparisonHandler = null;
var openHistoryCompareLauncherHandler = null;
function setHistoryCompareHandlers(handlers = {}) {
  if (typeof handlers.fetchAndRenderHistoryComparison === "function") {
    fetchAndRenderHistoryComparisonHandler = handlers.fetchAndRenderHistoryComparison;
  }
  if (typeof handlers.openHistoryCompareLauncher === "function") {
    openHistoryCompareLauncherHandler = handlers.openHistoryCompareLauncher;
  }
}
function fetchAndRenderHistoryComparison(...args) {
  return typeof fetchAndRenderHistoryComparisonHandler === "function" ? fetchAndRenderHistoryComparisonHandler(...args) : void 0;
}
function openHistoryCompareLauncher(...args) {
  return typeof openHistoryCompareLauncherHandler === "function" ? openHistoryCompareLauncherHandler(...args) : void 0;
}

export {
  setHistoryCompareHandlers,
  fetchAndRenderHistoryComparison,
  openHistoryCompareLauncher
};
