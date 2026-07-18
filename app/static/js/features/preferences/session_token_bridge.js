// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

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
