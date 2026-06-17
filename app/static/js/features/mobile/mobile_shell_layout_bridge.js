// Neutral mobile-shell layout boundary for UI helpers and runtime callers.

const mobileShellLayoutHandlers = {
  dismissMobileKeyboardAfterSubmit: null,
  getMobileKeyboardOffset: null,
  isMobileKeyboardOpen: null,
  syncMobileViewportState: null,
  useMobileTerminalViewportMode: null,
};

function setMobileShellLayoutHandlers(handlers = {}) {
  Object.keys(mobileShellLayoutHandlers).forEach((name) => {
    if (typeof handlers[name] === 'function') mobileShellLayoutHandlers[name] = handlers[name];
  });
}

function hasMobileShellLayoutHandler(name) {
  return typeof mobileShellLayoutHandlers[name] === 'function';
}

function dismissMobileKeyboardAfterSubmit(...args) {
  return typeof mobileShellLayoutHandlers.dismissMobileKeyboardAfterSubmit === 'function'
    ? mobileShellLayoutHandlers.dismissMobileKeyboardAfterSubmit(...args)
    : undefined;
}

function getMobileKeyboardOffset(...args) {
  return typeof mobileShellLayoutHandlers.getMobileKeyboardOffset === 'function'
    ? mobileShellLayoutHandlers.getMobileKeyboardOffset(...args)
    : 0;
}

function isMobileKeyboardOpen(...args) {
  return typeof mobileShellLayoutHandlers.isMobileKeyboardOpen === 'function'
    ? !!mobileShellLayoutHandlers.isMobileKeyboardOpen(...args)
    : false;
}

function syncMobileViewportState(...args) {
  return typeof mobileShellLayoutHandlers.syncMobileViewportState === 'function'
    ? mobileShellLayoutHandlers.syncMobileViewportState(...args)
    : undefined;
}

function useMobileTerminalViewportMode(...args) {
  return typeof mobileShellLayoutHandlers.useMobileTerminalViewportMode === 'function'
    ? !!mobileShellLayoutHandlers.useMobileTerminalViewportMode(...args)
    : false;
}

export {
  dismissMobileKeyboardAfterSubmit,
  getMobileKeyboardOffset,
  hasMobileShellLayoutHandler,
  isMobileKeyboardOpen,
  setMobileShellLayoutHandlers,
  syncMobileViewportState,
  useMobileTerminalViewportMode,
};
