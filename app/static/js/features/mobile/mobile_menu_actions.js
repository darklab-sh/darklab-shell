// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Mobile hamburger-menu action dispatch.
//
// controller.js owns the click wiring; this module owns the action body so the
// bootstrap file does not keep growing every time a mobile menu item is added.
import { historyPanel } from '../../core/dom.js';
import { getActiveTabId as importedGetActiveTabId } from '../../core/state.js';
import {
  applyLineNumberPreference,
  applyTimestampPreference,
} from '../preferences/preferences.js';
import {
  openOptions as importedOpenOptions,
  openThemeSelector as importedOpenThemeSelector,
} from '../../app.js';
import { openAtlas as importedOpenAtlas } from '../atlas/atlas_bridge.js';
import { openTeamScopeSelector } from '../team_scope.js';
import { openWorkflows as importedOpenWorkflows } from '../../controller_action_bridge.js';
import { openProjectWorkspace as importedOpenProjectWorkspace } from '../projects/project_context_bridge.js';
import { openWorkspace as importedOpenWorkspace } from '../../workspace_bridge.js';
import { openStatusMonitor as importedOpenStatusMonitor } from '../../runtime_bridge.js';
import { openCommandRegistry as importedOpenCommandRegistry } from '../command-registry/command_registry_bridge.js';
import { openFaq as importedOpenFaq } from '../../controller_action_bridge.js';
import { clearTab } from '../../tabs.js';
import { closeMajorOverlays as importedCloseMajorOverlays } from '../../ui/overlay_actions_bridge.js';
import {
  refreshHistoryPanel as importedRefreshHistoryPanel,
  resetHistoryMobileFilters as importedResetHistoryMobileFilters,
} from '../history/history_panel_bridge.js';
import {
  blurVisibleComposerInputIfMobile as importedBlurVisibleComposerInputIfMobile,
  hideSearchBar,
  isSearchBarOpen,
  refocusComposerAfterAction as importedRefocusComposerAfterAction,
  togglePanelOverlay,
} from '../../ui/ui_helpers.js';
import { getLineNumberMode as importedGetLineNumberMode } from '../../output.js';

const MOBILE_MENU_ACTIONS_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

function _mobileMenuGlobalFunction(name) {
  const fn = MOBILE_MENU_ACTIONS_GLOBAL && MOBILE_MENU_ACTIONS_GLOBAL[name];
  return typeof fn === 'function' ? fn : null;
}

function _mobileMenuCall(name, ...args) {
  const fn = _mobileMenuGlobalFunction(name);
  if (typeof fn === 'function') return fn(...args);
  return undefined;
}

function _mobileMenuImportedCall(importedFn, name, ...args) {
  const fn = typeof importedFn === 'function' ? importedFn : _mobileMenuGlobalFunction(name);
  if (typeof fn === 'function') return fn(...args);
  return undefined;
}

function _mobileMenuActiveTabId() {
  if (typeof importedGetActiveTabId === 'function') return importedGetActiveTabId();
  return MOBILE_MENU_ACTIONS_GLOBAL.activeTabId || null;
}

function _mobileMenuBlurComposer() {
  const blurComposer = (typeof importedBlurVisibleComposerInputIfMobile === 'function'
      ? importedBlurVisibleComposerInputIfMobile
      : null)
    || _mobileMenuGlobalFunction('blurVisibleComposerInputIfMobile');
  if (blurComposer) blurComposer();
}

function _mobileMenuRefocusComposer(options = { defer: true }) {
  const refocusComposer = (typeof importedRefocusComposerAfterAction === 'function'
      ? importedRefocusComposerAfterAction
      : null)
    || _mobileMenuGlobalFunction('refocusComposerAfterAction');
  if (refocusComposer) refocusComposer(options);
}

function _mobileMenuLineNumberMode() {
  if (typeof importedGetLineNumberMode === 'function') return importedGetLineNumberMode();
  return MOBILE_MENU_ACTIONS_GLOBAL.lnMode || 'off';
}

function dispatchMobileMenuAction(action, btn = null) {
  if (action === 'search') {
    const visible = isSearchBarOpen();
    if (visible) {
      hideSearchBar();
      _mobileMenuCall('clearSearch');
    } else {
      _mobileMenuCall('openSearchFromSignal');
    }
  }
  if (action === 'history') {
    _mobileMenuImportedCall(importedCloseMajorOverlays, '_closeMajorOverlays');
    const isOpen = togglePanelOverlay(historyPanel);
    if (isOpen) {
      _mobileMenuImportedCall(importedResetHistoryMobileFilters, 'resetHistoryMobileFilters');
      _mobileMenuBlurComposer();
      _mobileMenuImportedCall(importedRefreshHistoryPanel, 'refreshHistoryPanel');
    }
  }
  if (action === 'ts-toggle') {
    // mobile_chrome.js wires this row as a disclosure; keeping the sheet open
    // is the point of the action.
    return;
  }
  if (action === 'ts-set') {
    applyTimestampPreference(btn?.dataset.tsMode || 'off');
    _mobileMenuRefocusComposer({ defer: true });
  }
  if (action === 'ln') {
    applyLineNumberPreference(_mobileMenuLineNumberMode() === 'on' ? 'off' : 'on');
    _mobileMenuRefocusComposer({ defer: true });
  }
  if (action === 'clear') {
    const activeId = _mobileMenuActiveTabId();
    if (activeId) {
      _mobileMenuCall('cancelWelcome', activeId);
      if (typeof clearTab === 'function') clearTab(activeId, { preserveRunState: true });
    }
    _mobileMenuRefocusComposer({ defer: true });
  }
  if (action === 'options') _mobileMenuImportedCall(importedOpenOptions, 'openOptions');
  if (action === 'scope' && typeof openTeamScopeSelector === 'function') openTeamScopeSelector();
  if (action === 'projects') void _mobileMenuImportedCall(importedOpenProjectWorkspace, 'openProjectWorkspace');
  if (action === 'atlas') void _mobileMenuImportedCall(importedOpenAtlas, 'openAtlas', { source: 'mobile-menu' });
  if (action === 'status-monitor') void _mobileMenuImportedCall(importedOpenStatusMonitor, 'openStatusMonitor', { source: 'mobile-menu' });
  if (action === 'command-registry') _mobileMenuImportedCall(importedOpenCommandRegistry, 'openCommandRegistry');
  if (action === 'theme') _mobileMenuImportedCall(importedOpenThemeSelector, 'openThemeSelector');
  if (action === 'workflows') _mobileMenuImportedCall(importedOpenWorkflows, 'openWorkflows');
  if (action === 'schedules') void _mobileMenuCall('openSchedulesModal');
  if (action === 'watchers') void _mobileMenuCall('openWatchersModal');
  if (action === 'findings-board') void _mobileMenuCall('openFindingsBoard', { source: 'mobile-menu' });
  if (action === 'workspace') void _mobileMenuImportedCall(importedOpenWorkspace, 'openWorkspace');
  if (action === 'faq') _mobileMenuImportedCall(importedOpenFaq, 'openFaq');
  if (action === 'diag') MOBILE_MENU_ACTIONS_GLOBAL.location.href = '/diag';
}

if (typeof window !== 'undefined') {
}

export { dispatchMobileMenuAction };
