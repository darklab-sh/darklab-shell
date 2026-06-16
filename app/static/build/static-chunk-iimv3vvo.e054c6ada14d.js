// app/static/js/features/history/history_run_modal_state_bridge.js
var getHistoryRunModalStateHandler = null;
var openHistoryRunDetailsHandler = null;
var closeHistoryRunOverlayHandler = null;
var isHistoryRunOverlayOpenHandler = null;
var cycleHistoryRunOverlayTabHandler = null;
function setHistoryRunModalStateHandlers(handlers = {}) {
  if (typeof handlers.getHistoryRunModalState === "function") {
    getHistoryRunModalStateHandler = handlers.getHistoryRunModalState;
  }
  if (typeof handlers.openHistoryRunDetails === "function") {
    openHistoryRunDetailsHandler = handlers.openHistoryRunDetails;
  }
  if (typeof handlers.closeHistoryRunOverlay === "function") {
    closeHistoryRunOverlayHandler = handlers.closeHistoryRunOverlay;
  }
  if (typeof handlers.isHistoryRunOverlayOpen === "function") {
    isHistoryRunOverlayOpenHandler = handlers.isHistoryRunOverlayOpen;
  }
  if (typeof handlers.cycleHistoryRunOverlayTab === "function") {
    cycleHistoryRunOverlayTabHandler = handlers.cycleHistoryRunOverlayTab;
  }
}
function getHistoryRunModalState() {
  return typeof getHistoryRunModalStateHandler === "function" ? getHistoryRunModalStateHandler() : null;
}
function openHistoryRunDetails(...args) {
  return typeof openHistoryRunDetailsHandler === "function" ? openHistoryRunDetailsHandler(...args) : void 0;
}
function closeHistoryRunOverlay(...args) {
  return typeof closeHistoryRunOverlayHandler === "function" ? closeHistoryRunOverlayHandler(...args) : false;
}
function isHistoryRunOverlayOpen(...args) {
  return typeof isHistoryRunOverlayOpenHandler === "function" ? !!isHistoryRunOverlayOpenHandler(...args) : false;
}
function cycleHistoryRunOverlayTab(...args) {
  return typeof cycleHistoryRunOverlayTabHandler === "function" ? cycleHistoryRunOverlayTabHandler(...args) : false;
}

export {
  setHistoryRunModalStateHandlers,
  getHistoryRunModalState,
  openHistoryRunDetails,
  closeHistoryRunOverlay,
  isHistoryRunOverlayOpen,
  cycleHistoryRunOverlayTab
};
