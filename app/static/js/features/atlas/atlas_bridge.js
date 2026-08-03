// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Neutral Atlas overlay boundary for lazy placeholders and direct consumers.

const atlasHandlers = {
  DarklabAtlasOverlay: null,
  openAtlas: null,
  openAtlasQuickLookup: null,
  closeAtlas: null,
  isAtlasOverlayOpen: null,
  refreshAtlasOverlay: null,
  cycleAtlasTab: null,
};
const atlasDetailHandlers = {
  DarklabAtlasDetail: null,
  renderDetail: null,
  renderFindingDetail: null,
};
let atlasDetailLoader = null;

function setAtlasHandlers(handlers = {}) {
  Object.keys(atlasHandlers).forEach((name) => {
    if (handlers[name]) atlasHandlers[name] = handlers[name];
  });
}

function setAtlasDetailHandlers(handlers = {}) {
  if (handlers.DarklabAtlasDetail) atlasDetailHandlers.DarklabAtlasDetail = handlers.DarklabAtlasDetail;
  const detail = handlers.DarklabAtlasDetail || handlers;
  ['renderDetail', 'renderFindingDetail'].forEach((name) => {
    if (typeof detail[name] === 'function') atlasDetailHandlers[name] = detail[name];
  });
}

function setAtlasDetailLoader(loader) {
  if (typeof loader === 'function') atlasDetailLoader = loader;
}

function getAtlasOverlayController() {
  return atlasHandlers.DarklabAtlasOverlay || null;
}

function getAtlasDetailController() {
  return atlasDetailHandlers.DarklabAtlasDetail || atlasDetailHandlers;
}

function loadAtlasDetail(...args) {
  if (typeof atlasDetailLoader === 'function') return atlasDetailLoader(...args);
  return Promise.resolve(getAtlasDetailController());
}

function openAtlas(...args) {
  return typeof atlasHandlers.openAtlas === 'function'
    ? atlasHandlers.openAtlas(...args)
    : undefined;
}

function openAtlasQuickLookup(...args) {
  return typeof atlasHandlers.openAtlasQuickLookup === 'function'
    ? atlasHandlers.openAtlasQuickLookup(...args)
    : undefined;
}

function closeAtlas(...args) {
  return typeof atlasHandlers.closeAtlas === 'function'
    ? atlasHandlers.closeAtlas(...args)
    : false;
}

function isAtlasOverlayOpen(...args) {
  return typeof atlasHandlers.isAtlasOverlayOpen === 'function'
    ? !!atlasHandlers.isAtlasOverlayOpen(...args)
    : false;
}

function refreshAtlasOverlay(...args) {
  return typeof atlasHandlers.refreshAtlasOverlay === 'function'
    ? atlasHandlers.refreshAtlasOverlay(...args)
    : false;
}

function cycleAtlasTab(...args) {
  return typeof atlasHandlers.cycleAtlasTab === 'function'
    ? atlasHandlers.cycleAtlasTab(...args)
    : false;
}

export {
  closeAtlas,
  cycleAtlasTab,
  getAtlasDetailController,
  getAtlasOverlayController,
  isAtlasOverlayOpen,
  loadAtlasDetail,
  openAtlas,
  openAtlasQuickLookup,
  refreshAtlasOverlay,
  setAtlasDetailHandlers,
  setAtlasDetailLoader,
  setAtlasHandlers,
};
