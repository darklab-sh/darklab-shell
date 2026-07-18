// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Neutral overlay-action boundary for modules that need to close app-owned surfaces.

let closeMajorOverlaysHandler = null;

function setOverlayActionHandlers(handlers = {}) {
  if (typeof handlers.closeMajorOverlays === 'function') {
    closeMajorOverlaysHandler = handlers.closeMajorOverlays;
  }
}

function hasOverlayActionHandler(name) {
  return name === 'closeMajorOverlays' && typeof closeMajorOverlaysHandler === 'function';
}

function closeMajorOverlays(...args) {
  return typeof closeMajorOverlaysHandler === 'function'
    ? closeMajorOverlaysHandler(...args)
    : undefined;
}

export {
  closeMajorOverlays,
  hasOverlayActionHandler,
  setOverlayActionHandlers,
};
