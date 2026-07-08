import { getTabs as importedGetTabs } from '../../core/state.js';
import { activateTab as importedActivateTab } from '../../tabs.js';
import {
  activateRelativeTab as importedActivateRelativeTab,
  clearActiveShortcutTab as importedClearActiveShortcutTab,
  closeActiveShortcutTab as importedCloseActiveShortcutTab,
  closeOptions as importedCloseOptions,
  closeThemeSelector as importedCloseThemeSelector,
  copyActiveShortcutTab as importedCopyActiveShortcutTab,
  createShortcutTab as importedCreateShortcutTab,
  isStatusMonitorShortcutOpen as importedIsStatusMonitorShortcutOpen,
  openOptions as importedOpenOptions,
  openThemeSelector as importedOpenThemeSelector,
  permalinkActiveShortcutTab as importedPermalinkActiveShortcutTab,
  shouldIgnoreGlobalShortcutTarget as importedShouldIgnoreGlobalShortcutTarget,
} from '../../app.js';
import {
  closeCommandRegistry as importedCloseCommandRegistry,
  isCommandRegistryOverlayOpen as importedIsCommandRegistryOverlayOpen,
  openCommandRegistry as importedOpenCommandRegistry,
} from '../command-registry/command_registry_bridge.js';
import {
  cycleHistoryRunOverlayTab as importedCycleHistoryRunOverlayTab,
  isHistoryRunOverlayOpen as importedIsHistoryRunOverlayOpen,
} from '../history/history_run_modal_state_bridge.js';
import {
  closeAtlas as importedCloseAtlas,
  cycleAtlasTab as importedCycleAtlasTab,
  isAtlasOverlayOpen as importedIsAtlasOverlayOpen,
  openAtlas as importedOpenAtlas,
} from '../atlas/atlas_bridge.js';
import {
  closeProjectWorkspace as importedCloseProjectWorkspace,
  cycleProjectWorkspaceTab as importedCycleProjectWorkspaceTab,
  isProjectWorkspaceOpen as importedIsProjectWorkspaceOpen,
  openProjectWorkspace as importedOpenProjectWorkspace,
} from '../projects/project_context_bridge.js';
import { cycleOptionsTab as importedCycleOptionsTab } from '../preferences/preferences.js';
import {
  closeFaq as importedCloseFaq,
  closeWorkflows as importedCloseWorkflows,
  openFaq as importedOpenFaq,
  openWorkflows as importedOpenWorkflows,
  toggleHistoryPanelSurface as importedToggleHistoryPanelSurface,
  toggleRailCollapsed as importedToggleRailCollapsed,
} from '../../controller_action_bridge.js';
import {
  hideHistoryPanel,
  hideWorkspaceOverlay,
  isFaqOverlayOpen,
  isHistoryPanelOpen,
  isOptionsOverlayOpen,
  isThemeOverlayOpen,
  isWorkflowsOverlayOpen,
  isWorkspaceOverlayOpen,
} from '../../ui/ui_helpers.js';
import {
  closeWorkspace as importedCloseWorkspace,
  openWorkspace as importedOpenWorkspace,
} from '../../workspace_bridge.js';

const SHORTCUT_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

function shortcutGlobalFunction(name) {
  const windowFn = typeof window !== 'undefined' ? window[name] : null;
  if (typeof windowFn === 'function') return windowFn;
  const rootFn = SHORTCUT_GLOBAL && SHORTCUT_GLOBAL[name];
  if (typeof rootFn === 'function') return rootFn;
  const globalFn = typeof globalThis !== 'undefined' ? globalThis[name] : null;
  return typeof globalFn === 'function' ? globalFn : null;
}

const SHORTCUT_STABLE_FUNCTION_NAMES = [
  'activateTab',
  'shouldIgnoreGlobalShortcutTarget',
  'createShortcutTab',
  'closeActiveShortcutTab',
  'activateRelativeTab',
  'permalinkActiveShortcutTab',
  'copyActiveShortcutTab',
  'clearActiveShortcutTab',
  'closeThemeSelector',
  'openThemeSelector',
  'closeWorkspace',
  'openWorkspace',
  'isSchedulesOverlayOpen',
  'openSchedulesModal',
  'closeSchedulesModal',
  'isWatchersOverlayOpen',
  'openWatchersModal',
  'closeWatchersModal',
  'isStatusMonitorShortcutOpen',
  'isStatusMonitorOpen',
  'openStatusMonitor',
  'closeStatusMonitor',
  'isAtlasOverlayOpen',
  'cycleAtlasTab',
  'openAtlas',
  'closeAtlas',
  'isCommandRegistryOverlayOpen',
  'openCommandRegistry',
  'closeCommandRegistry',
  'isProjectWorkspaceOpen',
  'cycleProjectWorkspaceTab',
  'openProjectWorkspace',
  'closeProjectWorkspace',
  'toggleHistoryPanelSurface',
  'closeWorkflows',
  'openWorkflows',
  'closeOptions',
  'openOptions',
  'toggleRailCollapsed',
  'closeFaq',
  'openFaq',
  'isHistoryRunOverlayOpen',
  'cycleHistoryRunOverlayTab',
];
const SHORTCUT_IMPORTED_FUNCTIONS = {
  activateRelativeTab: importedActivateRelativeTab,
  clearActiveShortcutTab: importedClearActiveShortcutTab,
  closeActiveShortcutTab: importedCloseActiveShortcutTab,
  closeAtlas: importedCloseAtlas,
  closeOptions: importedCloseOptions,
  closeThemeSelector: importedCloseThemeSelector,
  closeCommandRegistry: importedCloseCommandRegistry,
  closeWorkspace: importedCloseWorkspace,
  copyActiveShortcutTab: importedCopyActiveShortcutTab,
  createShortcutTab: importedCreateShortcutTab,
  isCommandRegistryOverlayOpen: importedIsCommandRegistryOverlayOpen,
  isAtlasOverlayOpen: importedIsAtlasOverlayOpen,
  isHistoryRunOverlayOpen: importedIsHistoryRunOverlayOpen,
  isProjectWorkspaceOpen: importedIsProjectWorkspaceOpen,
  isStatusMonitorShortcutOpen: importedIsStatusMonitorShortcutOpen,
  openCommandRegistry: importedOpenCommandRegistry,
  openAtlas: importedOpenAtlas,
  openOptions: importedOpenOptions,
  openProjectWorkspace: importedOpenProjectWorkspace,
  openThemeSelector: importedOpenThemeSelector,
  openWorkspace: importedOpenWorkspace,
  openFaq: importedOpenFaq,
  openWorkflows: importedOpenWorkflows,
  permalinkActiveShortcutTab: importedPermalinkActiveShortcutTab,
  shouldIgnoreGlobalShortcutTarget: importedShouldIgnoreGlobalShortcutTarget,
  closeFaq: importedCloseFaq,
  closeProjectWorkspace: importedCloseProjectWorkspace,
  closeWorkflows: importedCloseWorkflows,
  cycleAtlasTab: importedCycleAtlasTab,
  cycleHistoryRunOverlayTab: importedCycleHistoryRunOverlayTab,
  cycleOptionsTab: importedCycleOptionsTab,
  cycleProjectWorkspaceTab: importedCycleProjectWorkspaceTab,
  toggleHistoryPanelSurface: importedToggleHistoryPanelSurface,
  toggleRailCollapsed: importedToggleRailCollapsed,
};
const shortcutStableFunctions = new Map(
  SHORTCUT_STABLE_FUNCTION_NAMES.map(name => [
    name,
    typeof SHORTCUT_IMPORTED_FUNCTIONS[name] === 'function'
      ? SHORTCUT_IMPORTED_FUNCTIONS[name]
      : shortcutGlobalFunction(name),
  ]),
);

function shortcutFunction(name) {
  let fn = shortcutGlobalFunction(name);
  if (fn) shortcutStableFunctions.set(name, fn);
  else fn = shortcutStableFunctions.get(name) || null;
  return fn;
}

function shortcutSurfaceFunction(name) {
  const imported = typeof SHORTCUT_IMPORTED_FUNCTIONS[name] === 'function'
    ? SHORTCUT_IMPORTED_FUNCTIONS[name]
    : null;
  const globalFn = shortcutGlobalFunction(name);
  if (typeof imported === 'function' && imported !== globalFn) {
    return (...args) => {
      const importedResult = imported(...args);
      if (importedResult || typeof globalFn !== 'function') return importedResult;
      return globalFn(...args);
    };
  }
  return globalFn || shortcutStableFunctions.get(name) || null;
}

function shortcutGetTabs() {
  if (typeof importedGetTabs === 'function') return importedGetTabs();
  const read = shortcutFunction('getTabs') || shortcutGlobalFunction('getTabs');
  return read ? read() : [];
}

function getShortcutActivateTab() {
  return shortcutFunction('activateTab')
    || (typeof importedActivateTab !== 'undefined' && importedActivateTab);
}

function shortcutCall(name, ...args) {
  const fn = shortcutFunction(name);
  return fn ? fn(...args) : undefined;
}

function shortcutIsOpen(name) {
  const fn = shortcutFunction(name);
  return !!(fn && fn());
}

function markShortcutHandled(e) {
  if (e && typeof e === 'object') e.__darklabShortcutHandled = true;
}

function shortcutAlreadyHandled(e) {
  return !!(e && e.__darklabShortcutHandled);
}

function eventMatchesCode(e, code) {
  return !!(e && e.code === code);
}

const MAC_OPTION_KEY_ALIASES = {
  f: ['ƒ'],
};

function eventMatchesLetter(e, letter) {
  if (eventMatchesCode(e, `Key${letter.toUpperCase()}`)) return true;
  const key = e && typeof e.key === 'string' ? e.key.toLowerCase() : '';
  const normalizedLetter = String(letter || '').toLowerCase();
  return key === normalizedLetter || (MAC_OPTION_KEY_ALIASES[normalizedLetter] || []).includes(key);
}

function eventMatchesDigit(e, digit) {
  if (eventMatchesCode(e, `Digit${digit}`)) return true;
  return !!(e && e.key === String(digit));
}

function _handleSurfaceTabShortcut(e) {
  if (!e || e.key !== 'Tab' || !e.altKey || e.ctrlKey || e.metaKey) return false;
  const offset = e.shiftKey ? -1 : 1;
  const surfaces = [
    {
      isOpen: shortcutSurfaceFunction('isHistoryRunOverlayOpen'),
      cycle: shortcutSurfaceFunction('cycleHistoryRunOverlayTab'),
    },
    {
      isOpen: shortcutSurfaceFunction('isAtlasOverlayOpen'),
      cycle: shortcutSurfaceFunction('cycleAtlasTab'),
    },
    {
      isOpen: shortcutSurfaceFunction('isProjectWorkspaceOpen'),
      cycle: shortcutSurfaceFunction('cycleProjectWorkspaceTab'),
    },
    {
      isOpen: typeof isOptionsOverlayOpen === 'function' ? isOptionsOverlayOpen : null,
      cycle: shortcutSurfaceFunction('cycleOptionsTab'),
    },
  ];
  const surface = surfaces.find(item => item.isOpen && item.isOpen() && item.cycle);
  if (!surface || !surface.cycle(offset)) return false;
  markShortcutHandled(e);
  e.preventDefault();
  return true;
}

function handleTabShortcut(e, options = {}) {
  if (shortcutAlreadyHandled(e)) return true;
  if (!e.altKey || e.ctrlKey || e.metaKey) return false;
  if (_handleSurfaceTabShortcut(e)) return true;
  if (options && options.surfaceOnly) return false;
  if (shortcutCall('shouldIgnoreGlobalShortcutTarget', e.target)) return false;
  // Letter chords (T, W) require no Shift — Alt+Shift+T is the theme-selector
  // chrome shortcut and must fall through to handleChromeShortcut.
  if (!e.shiftKey && eventMatchesLetter(e, 't')) {
    shortcutCall('createShortcutTab');
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (!e.shiftKey && eventMatchesLetter(e, 'w')) {
    shortcutCall('closeActiveShortcutTab');
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (e.shiftKey && e.key === 'ArrowRight') {
    shortcutCall('activateRelativeTab', 1);
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (e.shiftKey && e.key === 'ArrowLeft') {
    shortcutCall('activateRelativeTab', -1);
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (e.key === 'Tab') {
    shortcutCall('activateRelativeTab', e.shiftKey ? -1 : 1);
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  const matchedDigit = [1, 2, 3, 4, 5, 6, 7, 8, 9].find(digit => eventMatchesDigit(e, digit));
  if (matchedDigit) {
    const tabIndex = matchedDigit - 1;
    const currentTabs = shortcutGetTabs();
    const activate = getShortcutActivateTab();
    if (currentTabs[tabIndex] && typeof activate === 'function') {
      activate(currentTabs[tabIndex].id);
    }
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  return false;
}

function handleActionShortcut(e) {
  if (shortcutAlreadyHandled(e)) return true;
  if (shortcutCall('shouldIgnoreGlobalShortcutTarget', e.target)) return false;
  if (e.altKey && !e.ctrlKey && !e.metaKey && e.shiftKey && eventMatchesLetter(e, 'p')) {
    shortcutCall('permalinkActiveShortcutTab');
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (e.altKey && !e.ctrlKey && !e.metaKey && e.shiftKey && eventMatchesLetter(e, 'c')) {
    shortcutCall('copyActiveShortcutTab');
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (e.ctrlKey && !e.altKey && !e.metaKey && (e.key === 'l' || e.key === 'L')) {
    shortcutCall('clearActiveShortcutTab');
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (e.ctrlKey && !e.altKey && !e.metaKey && (e.key === 'd' || e.key === 'D')) {
    shortcutCall('closeActiveShortcutTab');
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  return false;
}

// Desktop chrome shortcuts (rail, search, history, options, theme, workflows,
// Files, projects, command registry, and Status Monitor).
// The composer is allowed to pass through so prompt-focused users can still
// trigger chrome toggles — each branch calls preventDefault so Option-glyphs
// (`«`, `˙`, `µ`, `©`, `≤`, `ˇ`, `ß`) never leak into the prompt on macOS.
// Other editable targets (modal inputs, search field, options textarea)
// remain gated so typing isn't hijacked.
//
// Search is bound to Alt+S (not Alt+F) because the composer owns Alt+F as
// readline word-forward; binding search to Alt+F would either hijack that
// or require a context-dependent chord that's a net UX loss. Alt+S has no
// readline conflict and works identically from everywhere.
//
// Each chord toggles its surface directly so the shortcut behavior stays in
// sync with the current rail/menu surfaces.
function handleChromeShortcut(e) {
  if (shortcutAlreadyHandled(e)) return true;
  if (!e.altKey || e.ctrlKey || e.metaKey) return false;
  if (_handleSurfaceTabShortcut(e)) return true;
  if (shortcutCall('shouldIgnoreGlobalShortcutTarget', e.target)) return false;
  // Alt+Shift+T → theme; guard first so it doesn't match Alt+Shift letter = T as tab-new.
  if (e.shiftKey && eventMatchesLetter(e, 't')) {
    if (typeof isThemeOverlayOpen === 'function' && isThemeOverlayOpen()) shortcutCall('closeThemeSelector');
    else shortcutCall('openThemeSelector');
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (e.shiftKey && eventMatchesLetter(e, 'f')) {
    if (shortcutIsOpen('isWorkspaceOverlayOpen') || (typeof isWorkspaceOverlayOpen === 'function' && isWorkspaceOverlayOpen())) {
      if (shortcutFunction('closeWorkspace')) shortcutCall('closeWorkspace');
      else if (typeof hideWorkspaceOverlay === 'function') hideWorkspaceOverlay();
    } else {
      shortcutCall('openWorkspace');
    }
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (e.shiftKey && eventMatchesLetter(e, 's')) {
    if (shortcutIsOpen('isSchedulesOverlayOpen')) void shortcutCall('closeSchedulesModal');
    else void shortcutCall('openSchedulesModal');
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (e.shiftKey && eventMatchesLetter(e, 'w')) {
    if (shortcutIsOpen('isWatchersOverlayOpen')) void shortcutCall('closeWatchersModal');
    else void shortcutCall('openWatchersModal');
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  // All remaining chrome chords are shift-free.
  if (e.shiftKey) return false;
  if (eventMatchesLetter(e, 'm')) {
    if (shortcutIsOpen('isStatusMonitorOpen') || shortcutCall('isStatusMonitorShortcutOpen')) shortcutCall('closeStatusMonitor');
    else void shortcutCall('openStatusMonitor', { source: 'shortcut' });
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (eventMatchesLetter(e, 'a')) {
    if (shortcutIsOpen('isAtlasOverlayOpen')) {
      shortcutCall('closeAtlas');
    } else {
      void shortcutCall('openAtlas', { source: 'shortcut' });
    }
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (eventMatchesLetter(e, 'c')) {
    if (shortcutIsOpen('isCommandRegistryOverlayOpen')) shortcutCall('closeCommandRegistry');
    else shortcutCall('openCommandRegistry');
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (eventMatchesLetter(e, 'p')) {
    if (shortcutIsOpen('isProjectWorkspaceOpen')) shortcutCall('closeProjectWorkspace');
    else void shortcutCall('openProjectWorkspace');
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (eventMatchesLetter(e, 'h')) {
    if (typeof isHistoryPanelOpen === 'function' && isHistoryPanelOpen()) {
      hideHistoryPanel();
    } else {
      shortcutCall('toggleHistoryPanelSurface', true);
    }
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (eventMatchesLetter(e, 'g')) {
    if (typeof isWorkflowsOverlayOpen === 'function' && isWorkflowsOverlayOpen()) shortcutCall('closeWorkflows');
    else shortcutCall('openWorkflows');
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (eventMatchesLetter(e, 's')) {
    document.getElementById('search-toggle-btn')?.click();
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (eventMatchesCode(e, 'Comma') || e.key === ',') {
    if (typeof isOptionsOverlayOpen === 'function' && isOptionsOverlayOpen()) shortcutCall('closeOptions');
    else shortcutCall('openOptions');
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (eventMatchesCode(e, 'Backslash') || e.key === '\\') {
    shortcutCall('toggleRailCollapsed');
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  if (eventMatchesCode(e, 'Slash') || e.key === '/' || e.key === '÷') {
    if (typeof isFaqOverlayOpen === 'function' && isFaqOverlayOpen()) shortcutCall('closeFaq');
    else shortcutCall('openFaq');
    markShortcutHandled(e);
    e.preventDefault();
    return true;
  }
  return false;
}

export {
  eventMatchesCode,
  eventMatchesDigit,
  eventMatchesLetter,
  handleActionShortcut,
  handleChromeShortcut,
  handleTabShortcut,
};
