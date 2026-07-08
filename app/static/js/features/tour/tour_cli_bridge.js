import { loadTourCliCommand as importedLoadTourCliCommand } from '../../core/lazy_assets.js';

const TOUR_CLI_BRIDGE_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

let loadedHandleTourCommand = null;

async function handleTourCommand(cmd, tabId = null) {
  if (typeof loadedHandleTourCommand === 'function' && loadedHandleTourCommand !== handleTourCommand) {
    return loadedHandleTourCommand(cmd, tabId);
  }

  const globalHandler = TOUR_CLI_BRIDGE_GLOBAL && TOUR_CLI_BRIDGE_GLOBAL.handleTourCommand;
  if (typeof globalHandler === 'function' && globalHandler !== handleTourCommand) {
    return globalHandler(cmd, tabId);
  }

  const load = (typeof importedLoadTourCliCommand === 'function' && importedLoadTourCliCommand)
    || (TOUR_CLI_BRIDGE_GLOBAL && TOUR_CLI_BRIDGE_GLOBAL.loadTourCliCommand);
  if (typeof load !== 'function') return false;

  loadedHandleTourCommand = await load();
  if (typeof loadedHandleTourCommand !== 'function' || loadedHandleTourCommand === handleTourCommand) {
    return false;
  }
  return loadedHandleTourCommand(cmd, tabId);
}

export { handleTourCommand };
