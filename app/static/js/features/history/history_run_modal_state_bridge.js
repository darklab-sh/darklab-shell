// Neutral Run Details modal-state boundary for History project helpers.

let getHistoryRunModalStateHandler = null;
let openHistoryRunDetailsHandler = null;
let closeHistoryRunOverlayHandler = null;
let isHistoryRunOverlayOpenHandler = null;
let cycleHistoryRunOverlayTabHandler = null;

function setHistoryRunModalStateHandlers(handlers = {}) {
  if (typeof handlers.getHistoryRunModalState === 'function') {
    getHistoryRunModalStateHandler = handlers.getHistoryRunModalState;
  }
  if (typeof handlers.openHistoryRunDetails === 'function') {
    openHistoryRunDetailsHandler = handlers.openHistoryRunDetails;
  }
  if (typeof handlers.closeHistoryRunOverlay === 'function') {
    closeHistoryRunOverlayHandler = handlers.closeHistoryRunOverlay;
  }
  if (typeof handlers.isHistoryRunOverlayOpen === 'function') {
    isHistoryRunOverlayOpenHandler = handlers.isHistoryRunOverlayOpen;
  }
  if (typeof handlers.cycleHistoryRunOverlayTab === 'function') {
    cycleHistoryRunOverlayTabHandler = handlers.cycleHistoryRunOverlayTab;
  }
}

function getHistoryRunModalState() {
  return typeof getHistoryRunModalStateHandler === 'function'
    ? getHistoryRunModalStateHandler()
    : null;
}

function openHistoryRunDetails(...args) {
  return typeof openHistoryRunDetailsHandler === 'function'
    ? openHistoryRunDetailsHandler(...args)
    : undefined;
}

function closeHistoryRunOverlay(...args) {
  return typeof closeHistoryRunOverlayHandler === 'function'
    ? closeHistoryRunOverlayHandler(...args)
    : false;
}

function isHistoryRunOverlayOpen(...args) {
  return typeof isHistoryRunOverlayOpenHandler === 'function'
    ? !!isHistoryRunOverlayOpenHandler(...args)
    : false;
}

function cycleHistoryRunOverlayTab(...args) {
  return typeof cycleHistoryRunOverlayTabHandler === 'function'
    ? cycleHistoryRunOverlayTabHandler(...args)
    : false;
}

export {
  closeHistoryRunOverlay,
  cycleHistoryRunOverlayTab,
  getHistoryRunModalState,
  isHistoryRunOverlayOpen,
  openHistoryRunDetails,
  setHistoryRunModalStateHandlers,
};
