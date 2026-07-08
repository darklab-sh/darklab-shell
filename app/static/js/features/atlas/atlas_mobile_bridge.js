// Neutral Atlas mobile boundary for desktop overlay reset hooks.

let resetTransientStateHandler = null;
let atlasMobileLoader = null;

function setAtlasMobileHandlers(handlers = {}) {
  if (typeof handlers.resetTransientState === 'function') {
    resetTransientStateHandler = handlers.resetTransientState;
  }
}

function setAtlasMobileLoader(loader) {
  if (typeof loader === 'function') atlasMobileLoader = loader;
}

function loadAtlasMobile(...args) {
  return typeof atlasMobileLoader === 'function'
    ? atlasMobileLoader(...args)
    : Promise.resolve(null);
}

function resetAtlasMobileTransientState(...args) {
  return typeof resetTransientStateHandler === 'function'
    ? resetTransientStateHandler(...args)
    : undefined;
}

export {
  loadAtlasMobile,
  resetAtlasMobileTransientState,
  setAtlasMobileHandlers,
  setAtlasMobileLoader,
};
