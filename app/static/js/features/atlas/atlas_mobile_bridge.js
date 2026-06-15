// Neutral Atlas mobile boundary for desktop overlay reset hooks.

let resetTransientStateHandler = null;

function setAtlasMobileHandlers(handlers = {}) {
  if (typeof handlers.resetTransientState === 'function') {
    resetTransientStateHandler = handlers.resetTransientState;
  }
}

function resetAtlasMobileTransientState(...args) {
  return typeof resetTransientStateHandler === 'function'
    ? resetTransientStateHandler(...args)
    : undefined;
}

export {
  resetAtlasMobileTransientState,
  setAtlasMobileHandlers,
};
