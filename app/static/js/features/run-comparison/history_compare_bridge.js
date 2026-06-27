// Neutral compare-action boundary shared by launcher and project run rows.

let fetchAndRenderHistoryComparisonHandler = null;
let openHistoryCompareLauncherHandler = null;

function hasOwnHandler(handlers, name) {
  return Object.prototype.hasOwnProperty.call(handlers, name);
}

function setHistoryCompareHandlers(handlers = {}) {
  if (hasOwnHandler(handlers, 'fetchAndRenderHistoryComparison')
    && handlers.fetchAndRenderHistoryComparison === null) {
    fetchAndRenderHistoryComparisonHandler = null;
  } else if (typeof handlers.fetchAndRenderHistoryComparison === 'function') {
    fetchAndRenderHistoryComparisonHandler = handlers.fetchAndRenderHistoryComparison;
  }
  if (hasOwnHandler(handlers, 'openHistoryCompareLauncher')
    && handlers.openHistoryCompareLauncher === null) {
    openHistoryCompareLauncherHandler = null;
  } else if (typeof handlers.openHistoryCompareLauncher === 'function') {
    openHistoryCompareLauncherHandler = handlers.openHistoryCompareLauncher;
  }
}

function hasHistoryCompareHandler(name) {
  const handlers = {
    fetchAndRenderHistoryComparison: fetchAndRenderHistoryComparisonHandler,
    openHistoryCompareLauncher: openHistoryCompareLauncherHandler,
  };
  return typeof handlers[name] === 'function';
}

function fetchAndRenderHistoryComparison(...args) {
  return typeof fetchAndRenderHistoryComparisonHandler === 'function'
    ? fetchAndRenderHistoryComparisonHandler(...args)
    : undefined;
}
fetchAndRenderHistoryComparison.hasHandler = () => hasHistoryCompareHandler('fetchAndRenderHistoryComparison');

function openHistoryCompareLauncher(...args) {
  return typeof openHistoryCompareLauncherHandler === 'function'
    ? openHistoryCompareLauncherHandler(...args)
    : undefined;
}
openHistoryCompareLauncher.hasHandler = () => hasHistoryCompareHandler('openHistoryCompareLauncher');

export {
  fetchAndRenderHistoryComparison,
  hasHistoryCompareHandler,
  openHistoryCompareLauncher,
  setHistoryCompareHandlers,
};
