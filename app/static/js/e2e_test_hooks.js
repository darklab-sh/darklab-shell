// Playwright-only browser hooks for end-to-end tests.
//
// The app runtime uses explicit ESM imports. These hooks intentionally preserve
// a small page.evaluate surface for browser tests that need to seed output,
// inspect session identity, or exercise tab state without reintroducing app
// module coupling through globals.
import {
  getActiveTabId,
  getAppState,
  getTab,
  getWelcomeState,
} from './core/state.js';
import {
  apiFetch,
  getSessionId,
} from './session.js';
import {
  runCommand,
  submitComposerCommand,
  submitVisibleComposerCommand,
} from './runner.js';
import {
  appendLine,
  appendLines,
} from './output.js';
import {
  clearTab,
  getOutput,
  setTabLabel,
  setTabStatus,
  updateOutputFollowButton,
} from './tabs.js';
import {
  acHide,
  acShow,
} from './autocomplete.js';
import {
  closeOptions,
  openOptions,
  openThemeSelector,
} from './app.js';
import {
  openFaq,
  openShortcuts,
  openWorkflows,
  toggleHistoryPanelSurface,
} from './controller.js';
import {
  openProjectWorkspace,
  refreshActiveProjectContext,
  refreshProjectWorkspace,
} from './features/projects/project_context_bridge.js';
import { refreshHistoryPanel } from './history.js';
import {
  hideHistoryPanel,
  isHistoryPanelOpen,
  showPanelOverlay,
} from './ui/ui_helpers.js';
import { openWorkspace } from './workspace_bridge.js';
import {
  _readRecentValues,
  getAutocompleteMatches,
  limitAutocompleteMatchesForDisplay,
  loadRecentValues,
  loadScheduleAutocompleteHints,
  loadWatcherAutocompleteHints,
} from './features/autocomplete/suggestions.js';
import { loadSessionVariables } from './features/autocomplete/runtime_context.js';
import {
  refreshSearchDiscoverabilityUi,
  scheduleSearchDiscoverabilityRefresh,
} from './search.js';
import { persistTabSessionStateNow } from './features/tabs/tab_session_state.js';
import {
  requestWelcomeSettle,
  welcomeOwnsTab,
} from './welcome.js';

const E2E_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

function _isE2EBrowser() {
  return !!(
    E2E_GLOBAL
    && E2E_GLOBAL.navigator
    && E2E_GLOBAL.navigator.webdriver === true
  );
}

function _defineE2EProperty(name, descriptor) {
  if (!E2E_GLOBAL) return;
  Object.defineProperty(E2E_GLOBAL, name, {
    configurable: true,
    enumerable: false,
    ...descriptor,
  });
}

function _stateValue(name) {
  const state = typeof getAppState === 'function' ? getAppState() : {};
  return state ? state[name] : undefined;
}

function _setStateValue(name, value) {
  const state = typeof getAppState === 'function' ? getAppState() : {};
  if (state) state[name] = value;
}

function _defineStateAlias(name) {
  _defineE2EProperty(name, {
    get() { return _stateValue(name); },
    set(value) { _setStateValue(name, value); },
  });
}

function _welcomeStateValue(name) {
  const state = typeof getWelcomeState === 'function' ? getWelcomeState() : {};
  return state ? state[name] : undefined;
}

function _defineWelcomeStateAlias(globalName, stateName) {
  _defineE2EProperty(globalName, {
    get() { return _welcomeStateValue(stateName); },
  });
}

function installE2ETestHooks() {
  if (!_isE2EBrowser()) return;

  const showHistoryPanel = () => showPanelOverlay(document.getElementById('history-panel'));

  const hooks = {
    apiFetch,
    acHide,
    acShow,
    appendLine,
    appendLines,
    clearTab,
    closeOptions,
    getActiveTabId,
    getAutocompleteMatches,
    getOutput,
    getSessionId,
    getTab,
    hideHistoryPanel,
    isHistoryPanelOpen,
    loadRecentValues,
    limitAutocompleteMatchesForDisplay,
    loadScheduleAutocompleteHints,
    loadSessionVariables,
    loadWatcherAutocompleteHints,
    persistTabSessionStateNow,
    refreshSearchDiscoverabilityUi,
    refreshHistoryPanel,
    requestWelcomeSettle,
    runCommand,
    scheduleSearchDiscoverabilityRefresh,
    setTabLabel,
    setTabStatus,
    showHistoryPanel,
    submitComposerCommand,
    submitVisibleComposerCommand,
    openFaq,
    openOptions,
    openProjectWorkspace,
    refreshActiveProjectContext,
    refreshProjectWorkspace,
    openShortcuts,
    openThemeSelector,
    openWorkflows,
    openWorkspace,
    _readRecentValues,
    toggleHistoryPanelSurface,
    updateOutputFollowButton,
    welcomeOwnsTab,
  };

  E2E_GLOBAL.__darklabE2E = Object.freeze({ ...hooks });

  Object.entries(hooks).forEach(([name, value]) => {
    if (typeof value === 'function') {
      _defineE2EProperty(name, { value, writable: true });
    }
  });

  _defineE2EProperty('SESSION_ID', {
    get() { return typeof getSessionId === 'function' ? getSessionId() : ''; },
  });
  _defineE2EProperty('activeTabId', {
    get() { return typeof getActiveTabId === 'function' ? getActiveTabId() : null; },
  });

  [
    'acSuggestions',
    'acContextRegistry',
    'acWordlists',
    'acSpecialCommands',
    'acBuiltinCommandRoots',
    'cmdHistory',
    'sessionVariables',
  ].forEach(_defineStateAlias);

  _defineWelcomeStateAlias('_welcomeActive', 'active');
  _defineWelcomeStateAlias('_welcomeBootPending', 'bootPending');
  _defineWelcomeStateAlias('_welcomeDone', 'done');
  _defineWelcomeStateAlias('_welcomeTabId', 'tabId');
}

installE2ETestHooks();

export { installE2ETestHooks };
