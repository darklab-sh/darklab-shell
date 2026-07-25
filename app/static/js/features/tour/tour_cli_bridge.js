// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { loadTourCliCommand as importedLoadTourCliCommand } from '../../core/lazy_assets.js';

const TOUR_CLI_BRIDGE_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

let loadedHandleTourCommand = null;

async function handleTourCommand(cmd, tabId = null, execution = null) {
  if (typeof loadedHandleTourCommand === 'function' && loadedHandleTourCommand !== handleTourCommand) {
    return loadedHandleTourCommand(cmd, tabId, execution);
  }

  const globalHandler = TOUR_CLI_BRIDGE_GLOBAL && TOUR_CLI_BRIDGE_GLOBAL.handleTourCommand;
  if (typeof globalHandler === 'function' && globalHandler !== handleTourCommand) {
    return globalHandler(cmd, tabId, execution);
  }

  const load = (typeof importedLoadTourCliCommand === 'function' && importedLoadTourCliCommand)
    || (TOUR_CLI_BRIDGE_GLOBAL && TOUR_CLI_BRIDGE_GLOBAL.loadTourCliCommand);
  if (typeof load !== 'function') return false;

  loadedHandleTourCommand = await load();
  if (typeof loadedHandleTourCommand !== 'function' || loadedHandleTourCommand === handleTourCommand) {
    return false;
  }
  return loadedHandleTourCommand(cmd, tabId, execution);
}

export { handleTourCommand };
