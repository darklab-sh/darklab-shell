// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Shared Quick Lookup launch boundary for the rail, mobile menu, and shortcut.

import { logClientError as importedLogClientError } from '../../runtime_bridge.js';
import { openAtlasQuickLookup as importedOpenAtlasQuickLookup } from './atlas_bridge.js';

const QUICK_LOOKUP_LAUNCH_SOURCES = new Set(['rail', 'mobile-menu', 'shortcut']);

function normalizedLaunchSource(value) {
  const source = String(value || '').trim().toLowerCase();
  return QUICK_LOOKUP_LAUNCH_SOURCES.has(source) ? source : 'unknown';
}

async function openAtlasQuickLookupFromSurface(source, {
  open = importedOpenAtlasQuickLookup,
  logClientError = importedLogClientError,
  onFailure = null,
} = {}) {
  const safeSource = normalizedLaunchSource(source);
  let stage = 'lazy_load';
  try {
    if (typeof open !== 'function') {
      stage = 'controller';
      throw new Error('Quick Lookup controller is unavailable');
    }
    const opened = await open({ source: safeSource, toggle: true });
    // `false` is also the successful toggle-close result. Lazy controller
    // absence throws with an explicit stage so closing never looks like an
    // application failure.
    if (typeof opened === 'undefined') {
      stage = 'controller';
      throw new Error('Quick Lookup controller is unavailable');
    }
    return opened;
  } catch (err) {
    stage = err?.quickLookupStage === 'controller' ? 'controller' : stage;
    if (typeof logClientError === 'function') {
      logClientError('failed to open Quick Lookup', err, {
        event: 'ATLAS_QUICK_LOOKUP_OPEN_FAILED',
        level: 'error',
        source: safeSource,
        stage,
      });
    }
    if (typeof onFailure === 'function') onFailure(err, { source: safeSource, stage });
    return false;
  }
}

export {
  normalizedLaunchSource,
  openAtlasQuickLookupFromSurface,
};
