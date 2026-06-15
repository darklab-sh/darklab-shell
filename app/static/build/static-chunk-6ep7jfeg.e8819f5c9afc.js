// app/static/js/features/atlas/atlas_mobile_bridge.js
var resetTransientStateHandler = null;
function setAtlasMobileHandlers(handlers = {}) {
  if (typeof handlers.resetTransientState === "function") {
    resetTransientStateHandler = handlers.resetTransientState;
  }
}
function resetAtlasMobileTransientState(...args) {
  return typeof resetTransientStateHandler === "function" ? resetTransientStateHandler(...args) : void 0;
}

export {
  setAtlasMobileHandlers,
  resetAtlasMobileTransientState
};
