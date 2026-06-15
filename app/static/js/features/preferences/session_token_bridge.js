// Neutral Options session-token boundary for cross-tab session refreshes.

let updateOptionsSessionTokenStatusHandler = null;

function setSessionTokenHandlers(handlers = {}) {
  if (typeof handlers.updateOptionsSessionTokenStatus === 'function') {
    updateOptionsSessionTokenStatusHandler = handlers.updateOptionsSessionTokenStatus;
  }
}

function updateOptionsSessionTokenStatus(...args) {
  return typeof updateOptionsSessionTokenStatusHandler === 'function'
    ? updateOptionsSessionTokenStatusHandler(...args)
    : undefined;
}

export {
  setSessionTokenHandlers,
  updateOptionsSessionTokenStatus,
};
