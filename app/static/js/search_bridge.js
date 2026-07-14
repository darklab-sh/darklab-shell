// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Neutral search boundary for tab lifecycle code. search.js imports tabs.js,
// so tabs.js reaches search behavior through this bridge instead of importing
// search.js back and creating a cycle.

const searchHandlers = {
  clearSearch: null,
  refreshSearchDiscoverabilityUi: null,
  scheduleSearchDiscoverabilityRefresh: null,
};

function setSearchHandlers(handlers = {}) {
  Object.keys(searchHandlers).forEach((name) => {
    if (typeof handlers[name] === 'function') searchHandlers[name] = handlers[name];
  });
}

function hasSearchHandler(name) {
  return typeof searchHandlers[name] === 'function';
}

function clearSearch(...args) {
  return typeof searchHandlers.clearSearch === 'function'
    ? searchHandlers.clearSearch(...args)
    : undefined;
}

function refreshSearchDiscoverabilityUi(...args) {
  return typeof searchHandlers.refreshSearchDiscoverabilityUi === 'function'
    ? searchHandlers.refreshSearchDiscoverabilityUi(...args)
    : undefined;
}

function scheduleSearchDiscoverabilityRefresh(...args) {
  return typeof searchHandlers.scheduleSearchDiscoverabilityRefresh === 'function'
    ? searchHandlers.scheduleSearchDiscoverabilityRefresh(...args)
    : undefined;
}

export {
  clearSearch,
  hasSearchHandler,
  refreshSearchDiscoverabilityUi,
  scheduleSearchDiscoverabilityRefresh,
  setSearchHandlers,
};
