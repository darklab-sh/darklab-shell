// Neutral Command Registry boundary for eager consumers.

const COMMAND_REGISTRY_BRIDGE_GLOBAL = typeof window !== 'undefined' ? window : globalThis;
const commandRegistryBridgeState = COMMAND_REGISTRY_BRIDGE_GLOBAL.__darklabCommandRegistryBridge || {
  openCommandRegistryHandler: null,
  closeCommandRegistryHandler: null,
  commandRegistryBridgeData: null,
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
  if (typeof handlers.isCommandRegistryOverlayOpen === 'function') {
    commandRegistryBridgeState.isCommandRegistryOverlayOpenHandler = handlers.isCommandRegistryOverlayOpen;
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

function getCommandRegistryData() {
  return commandRegistryBridgeState.commandRegistryBridgeData;
}

function isCommandRegistryOverlayOpen(...args) {
  return typeof commandRegistryBridgeState.isCommandRegistryOverlayOpenHandler === 'function'
    ? !!commandRegistryBridgeState.isCommandRegistryOverlayOpenHandler(...args)
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

export {
  closeCommandRegistry,
  getCommandRegistryData,
  isCommandRegistryOverlayOpen,
  openCommandRegistry,
  renderCommandRegistry,
  setCommandRegistryData,
  setCommandRegistryHandlers,
};
