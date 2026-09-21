// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Secondary shell content starts after tab restoration or an explicit panel open.
import { apiFetch, logClientError } from '../../session.js';
import { renderAllowedCommandsFaq, renderFaqItems, setAllowedCommandsFaqData } from './faq_helpers.js';
import { isCommandRegistryOverlayOpen, renderCommandRegistry, setCommandRegistryData } from './command_registry_bridge.js';
import { ensureWorkflowCatalogLoaded } from '../workflows/workflows_bridge.js';

const shellCatalogRequests = new Map();

function loadShellCatalog(path, render) {
  if (!shellCatalogRequests.has(path)) {
    const request = apiFetch(path).then(response => {
      if (response.ok === false) throw new Error(`HTTP ${response.status}`);
      return response.json();
    }).then(render).catch(error => {
      shellCatalogRequests.delete(path);
      logClientError(`failed to load ${path}`, error);
    });
    shellCatalogRequests.set(path, request);
  }
  return shellCatalogRequests.get(path);
}

function loadShellCatalogs() {
  return Promise.all([
    loadShellCatalog('/allowed-commands', data => {
      setAllowedCommandsFaqData(data);
      renderAllowedCommandsFaq(data);
    }),
    loadShellCatalog('/commands/catalog', data => {
      setCommandRegistryData(data);
      if (isCommandRegistryOverlayOpen()) renderCommandRegistry();
    }),
    loadShellCatalog('/faq', data => renderFaqItems(data.items || [])),
    loadShellCatalog('/shortcuts', data => renderShortcuts(data || {})),
    Promise.resolve(ensureWorkflowCatalogLoaded()).catch(error => logClientError('failed to load /workflows', error)),
  ]);
}

function renderShortcuts(data) {
  const listEl = document.getElementById('shortcuts-list');
  if (!listEl) return;
  listEl.textContent = '';
  const sections = Array.isArray(data && data.sections) ? data.sections : [];
  for (const section of sections) {
    const items = Array.isArray(section && section.items) ? section.items : [];
    if (!items.length) continue;
    const sectionEl = document.createElement('div');
    sectionEl.className = 'shortcuts-section';
    const headingEl = document.createElement('div');
    headingEl.className = 'shortcut-section-title';
    headingEl.textContent = section.title || '';
    sectionEl.appendChild(headingEl);
    const pairsEl = document.createElement('div');
    pairsEl.className = 'shortcuts-pairs';
    for (const item of items) {
      const keyEl = document.createElement('div');
      keyEl.className = 'shortcut-key';
      keyEl.textContent = item.key || '';
      const descEl = document.createElement('div');
      descEl.className = 'shortcut-desc';
      descEl.textContent = item.description || '';
      pairsEl.appendChild(keyEl);
      pairsEl.appendChild(descEl);
    }
    sectionEl.appendChild(pairsEl);
    listEl.appendChild(sectionEl);
  }
}

export { loadShellCatalogs, renderShortcuts };
