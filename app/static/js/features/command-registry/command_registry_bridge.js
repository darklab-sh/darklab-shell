// Neutral Command Registry boundary for eager consumers.

const COMMAND_REGISTRY_BRIDGE_GLOBAL = typeof window !== 'undefined' ? window : globalThis;
const commandRegistryBridgeState = COMMAND_REGISTRY_BRIDGE_GLOBAL.__darklabCommandRegistryBridge || {
  allowedCommandsFaqData: null,
  closeCommandCatalogHandler: null,
  hideCommandCatalogHandler: null,
  openCommandRegistryHandler: null,
  closeCommandRegistryHandler: null,
  commandRegistryBridgeData: null,
  isCommandCatalogOverlayOpenHandler: null,
  isCommandRegistryOverlayOpenHandler: null,
  renderCommandRegistryHandler: null,
};
COMMAND_REGISTRY_BRIDGE_GLOBAL.__darklabCommandRegistryBridge = commandRegistryBridgeState;

function setCommandRegistryHandlers(handlers = {}) {
  if (typeof handlers.openCommandRegistry === 'function') {
    commandRegistryBridgeState.openCommandRegistryHandler = handlers.openCommandRegistry;
  }
  if (typeof handlers.closeCommandRegistry === 'function') {
    commandRegistryBridgeState.closeCommandRegistryHandler = handlers.closeCommandRegistry;
  }
  if (typeof handlers.closeCommandCatalogModal === 'function') {
    commandRegistryBridgeState.closeCommandCatalogHandler = handlers.closeCommandCatalogModal;
  }
  if (typeof handlers.hideCommandCatalogOverlay === 'function') {
    commandRegistryBridgeState.hideCommandCatalogHandler = handlers.hideCommandCatalogOverlay;
  }
  if (typeof handlers.isCommandRegistryOverlayOpen === 'function') {
    commandRegistryBridgeState.isCommandRegistryOverlayOpenHandler = handlers.isCommandRegistryOverlayOpen;
  }
  if (typeof handlers.isCommandCatalogOverlayOpen === 'function') {
    commandRegistryBridgeState.isCommandCatalogOverlayOpenHandler = handlers.isCommandCatalogOverlayOpen;
  }
  if (typeof handlers.renderCommandRegistry === 'function') {
    commandRegistryBridgeState.renderCommandRegistryHandler = handlers.renderCommandRegistry;
  }
}

function openCommandRegistry(...args) {
  return typeof commandRegistryBridgeState.openCommandRegistryHandler === 'function'
    ? commandRegistryBridgeState.openCommandRegistryHandler(...args)
    : undefined;
}

function closeCommandRegistry(...args) {
  return typeof commandRegistryBridgeState.closeCommandRegistryHandler === 'function'
    ? commandRegistryBridgeState.closeCommandRegistryHandler(...args)
    : undefined;
}

function closeCommandCatalogModal(...args) {
  return typeof commandRegistryBridgeState.closeCommandCatalogHandler === 'function'
    ? commandRegistryBridgeState.closeCommandCatalogHandler(...args)
    : undefined;
}

function hideCommandCatalogOverlay(...args) {
  return typeof commandRegistryBridgeState.hideCommandCatalogHandler === 'function'
    ? commandRegistryBridgeState.hideCommandCatalogHandler(...args)
    : undefined;
}

function getCommandRegistryData() {
  return commandRegistryBridgeState.commandRegistryBridgeData;
}

function getAllowedCommandsFaqData() {
  return commandRegistryBridgeState.allowedCommandsFaqData;
}

function isCommandRegistryOverlayOpen(...args) {
  return typeof commandRegistryBridgeState.isCommandRegistryOverlayOpenHandler === 'function'
    ? !!commandRegistryBridgeState.isCommandRegistryOverlayOpenHandler(...args)
    : false;
}

function isCommandCatalogOverlayOpen(...args) {
  return typeof commandRegistryBridgeState.isCommandCatalogOverlayOpenHandler === 'function'
    ? !!commandRegistryBridgeState.isCommandCatalogOverlayOpenHandler(...args)
    : false;
}

function renderCommandRegistry(...args) {
  return typeof commandRegistryBridgeState.renderCommandRegistryHandler === 'function'
    ? commandRegistryBridgeState.renderCommandRegistryHandler(...args)
    : undefined;
}

function setCommandRegistryData(data) {
  commandRegistryBridgeState.commandRegistryBridgeData = data || null;
  return commandRegistryBridgeState.commandRegistryBridgeData;
}

function setAllowedCommandsFaqData(data) {
  commandRegistryBridgeState.allowedCommandsFaqData = data || null;
  return commandRegistryBridgeState.allowedCommandsFaqData;
}

export {
  closeCommandCatalogModal,
  closeCommandRegistry,
  getAllowedCommandsFaqData,
  getCommandRegistryData,
  hideCommandCatalogOverlay,
  isCommandCatalogOverlayOpen,
  isCommandRegistryOverlayOpen,
  openCommandRegistry,
  renderCommandRegistry,
  setAllowedCommandsFaqData,
  setCommandRegistryData,
  setCommandRegistryHandlers,
};
