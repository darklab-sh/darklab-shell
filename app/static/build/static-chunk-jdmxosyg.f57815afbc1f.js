// app/static/js/features/history/history_run_modal_state_bridge.js
var getHistoryRunModalStateHandler = null;
var openHistoryRunDetailsHandler = null;
var closeHistoryRunOverlayHandler = null;
var isHistoryRunOverlayOpenHandler = null;
var cycleHistoryRunOverlayTabHandler = null;
function hasOwnHandler(handlers, name) {
  return Object.prototype.hasOwnProperty.call(handlers, name);
}
function setHistoryRunModalStateHandlers(handlers = {}) {
  if (hasOwnHandler(handlers, "getHistoryRunModalState") && handlers.getHistoryRunModalState === null) {
    getHistoryRunModalStateHandler = null;
  } else if (typeof handlers.getHistoryRunModalState === "function") {
    getHistoryRunModalStateHandler = handlers.getHistoryRunModalState;
  }
  if (hasOwnHandler(handlers, "openHistoryRunDetails") && handlers.openHistoryRunDetails === null) {
    openHistoryRunDetailsHandler = null;
  } else if (typeof handlers.openHistoryRunDetails === "function") {
    openHistoryRunDetailsHandler = handlers.openHistoryRunDetails;
  }
  if (hasOwnHandler(handlers, "closeHistoryRunOverlay") && handlers.closeHistoryRunOverlay === null) {
    closeHistoryRunOverlayHandler = null;
  } else if (typeof handlers.closeHistoryRunOverlay === "function") {
    closeHistoryRunOverlayHandler = handlers.closeHistoryRunOverlay;
  }
  if (hasOwnHandler(handlers, "isHistoryRunOverlayOpen") && handlers.isHistoryRunOverlayOpen === null) {
    isHistoryRunOverlayOpenHandler = null;
  } else if (typeof handlers.isHistoryRunOverlayOpen === "function") {
    isHistoryRunOverlayOpenHandler = handlers.isHistoryRunOverlayOpen;
  }
  if (hasOwnHandler(handlers, "cycleHistoryRunOverlayTab") && handlers.cycleHistoryRunOverlayTab === null) {
    cycleHistoryRunOverlayTabHandler = null;
  } else if (typeof handlers.cycleHistoryRunOverlayTab === "function") {
    cycleHistoryRunOverlayTabHandler = handlers.cycleHistoryRunOverlayTab;
  }
}
function hasHistoryRunModalStateHandler(name) {
  const handlers = {
    closeHistoryRunOverlay: closeHistoryRunOverlayHandler,
    cycleHistoryRunOverlayTab: cycleHistoryRunOverlayTabHandler,
    getHistoryRunModalState: getHistoryRunModalStateHandler,
    isHistoryRunOverlayOpen: isHistoryRunOverlayOpenHandler,
    openHistoryRunDetails: openHistoryRunDetailsHandler
  };
  return typeof handlers[name] === "function";
}
function getHistoryRunModalState() {
  return typeof getHistoryRunModalStateHandler === "function" ? getHistoryRunModalStateHandler() : null;
}
function openHistoryRunDetails(...args) {
  return typeof openHistoryRunDetailsHandler === "function" ? openHistoryRunDetailsHandler(...args) : void 0;
}
openHistoryRunDetails.hasHandler = () => hasHistoryRunModalStateHandler("openHistoryRunDetails");
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
  hasHistoryRunModalStateHandler,
  getHistoryRunModalState,
  openHistoryRunDetails,
  closeHistoryRunOverlay,
  isHistoryRunOverlayOpen,
  cycleHistoryRunOverlayTab
};
