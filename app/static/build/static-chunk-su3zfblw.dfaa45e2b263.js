// app/static/js/features/history/history_run_modal_state_bridge.js
var HISTORY_RUN_MODAL_STATE_BRIDGE_GLOBAL = typeof window !== "undefined" ? window : globalThis;
var warnedMissingHistoryRunModalStateHandlers = /* @__PURE__ */ new Set();
var getHistoryRunModalStateHandler = null;
var openHistoryRunDetailsHandler = null;
var closeHistoryRunOverlayHandler = null;
var isHistoryRunOverlayOpenHandler = null;
var cycleHistoryRunOverlayTabHandler = null;
function hasOwnHandler(handlers, name) {
  return Object.prototype.hasOwnProperty.call(handlers, name);
}
function _historyRunModalStateBridgeWarningsEnabled() {
  const config = HISTORY_RUN_MODAL_STATE_BRIDGE_GLOBAL?.APP_CONFIG && typeof HISTORY_RUN_MODAL_STATE_BRIDGE_GLOBAL.APP_CONFIG === "object" && !Array.isArray(HISTORY_RUN_MODAL_STATE_BRIDGE_GLOBAL.APP_CONFIG) ? HISTORY_RUN_MODAL_STATE_BRIDGE_GLOBAL.APP_CONFIG : {};
  return config.frontend_bridge_warnings === true || config.debug === true || config.dev_mode === true || config.environment === "development" || config.env === "development";
}
function _logHistoryRunModalStateBridgeDiagnostic(level, event, details = {}) {
  if (!_historyRunModalStateBridgeWarningsEnabled()) return;
  const consoleApi = HISTORY_RUN_MODAL_STATE_BRIDGE_GLOBAL?.console || globalThis?.console;
  const method = level === "error" ? "error" : level === "warning" ? "warn" : "debug";
  const log = consoleApi && (consoleApi[method] || consoleApi.log);
  if (typeof log !== "function") return;
  log.call(consoleApi, `[darklab] ${event}`, {
    event,
    level,
    ...details
  });
}
function _warnMissingHistoryRunModalStateHandler(name) {
  if (warnedMissingHistoryRunModalStateHandlers.has(name)) return;
  warnedMissingHistoryRunModalStateHandlers.add(name);
  _logHistoryRunModalStateBridgeDiagnostic("warning", "HISTORY_RUN_MODAL_STATE_HANDLER_MISSING", {
    handler: name
  });
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
  if (typeof getHistoryRunModalStateHandler === "function") return getHistoryRunModalStateHandler();
  _warnMissingHistoryRunModalStateHandler("getHistoryRunModalState");
  return null;
}
function openHistoryRunDetails(...args) {
  if (typeof openHistoryRunDetailsHandler === "function") return openHistoryRunDetailsHandler(...args);
  _warnMissingHistoryRunModalStateHandler("openHistoryRunDetails");
  return void 0;
}
openHistoryRunDetails.hasHandler = () => hasHistoryRunModalStateHandler("openHistoryRunDetails");
function closeHistoryRunOverlay(...args) {
  if (typeof closeHistoryRunOverlayHandler === "function") return closeHistoryRunOverlayHandler(...args);
  _warnMissingHistoryRunModalStateHandler("closeHistoryRunOverlay");
  return false;
}
function isHistoryRunOverlayOpen(...args) {
  if (typeof isHistoryRunOverlayOpenHandler === "function") return !!isHistoryRunOverlayOpenHandler(...args);
  _warnMissingHistoryRunModalStateHandler("isHistoryRunOverlayOpen");
  return false;
}
function cycleHistoryRunOverlayTab(...args) {
  if (typeof cycleHistoryRunOverlayTabHandler === "function") return cycleHistoryRunOverlayTabHandler(...args);
  _warnMissingHistoryRunModalStateHandler("cycleHistoryRunOverlayTab");
  return false;
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
