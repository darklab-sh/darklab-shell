// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

/**
 * Extract named pure functions from a browser JS source file for unit testing.
 *
 * Strategy: wrap the file contents in `new Function(...)` so that
 * DOM-referencing functions are defined but never called.  Only the
 * explicitly requested names are returned.  Functions that close over
 * `localStorage` receive a self-contained MemoryStorage instance so that
 * tests stay isolated from any jsdom quirks and don't need a real browser.
 *
 * Usage:
 *   import { fromScript } from './helpers/extract.js'
 *   const { escapeHtml } = fromScript('app/static/js/core/utils.js', 'escapeHtml')
 *
 *   // For functions that use localStorage, access the store via _storage:
 *   const { _getStarred, _saveStarred, _storage } =
 *     fromScript('app/static/js/features/history/history_actions.js', '_getStarred', '_saveStarred')
 *   _storage.setItem('starred', JSON.stringify(['cmd1']))
 */

import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../../../../')
export function stripEsmExports(src) {
  const sourceText = String(src || '')
  return sourceText
    .replace(/^\s*import\s*\{([\s\S]*?)\}\s*from\s*['"]([^'"]+)['"];\s*/gm, (_match, specifiers, modulePath) => {
      return specifiers
        .split(',')
        .map((specifier) => specifier.trim())
        .filter(Boolean)
        .map((specifier) => {
          const [importedName, localName = importedName] = specifier.split(/\s+as\s+/).map((part) => part.trim())
          const localDeclarationPattern = new RegExp(`(?:function|const|let|var)\\s+${importedName}\\b`)
          const sameNameHelperFallback = localName === importedName && (
            modulePath.includes('/ui/')
            || modulePath.includes('./ui/')
            || modulePath.includes('/core/state')
            || modulePath.includes('./core/state')
          );
          const sameScopeImportFallback = modulePath.includes('/workflows/workflows_bridge')
            || modulePath.includes('./workflows_bridge')
            || modulePath.includes('/history/history_panel_bridge')
            || modulePath.includes('./history_panel_bridge')
            || modulePath.includes('/preferences/secrets_bridge')
            || modulePath.includes('./secrets_bridge')
            || modulePath.includes('/command-registry/command_registry_bridge')
            || modulePath.includes('./command_registry_bridge')
            || modulePath.includes('/output_bridge')
            || modulePath.includes('./output_bridge')
            || modulePath.includes('/runner_bridge')
            || modulePath.includes('./runner_bridge');
          const commandRegistryBridgeImport = modulePath.includes('command_registry_bridge');
          if (localName === importedName) {
            const sameNameNeedsGlobalFallback = (
              modulePath.includes('/ui/')
              || modulePath.includes('./ui/')
              || modulePath.includes('/core/state')
              || modulePath.includes('./core/state')
            );
            if (!sameNameNeedsGlobalFallback || localDeclarationPattern.test(sourceText)) return ''
          }
          const shouldSkipBareFallback = (
            sameNameHelperFallback
            || (localDeclarationPattern.test(sourceText) && !sameScopeImportFallback)
            || commandRegistryBridgeImport
          );
          const bareFallback = shouldSkipBareFallback
            ? ''
            : `try { if (typeof ${importedName} !== 'undefined') return ${importedName}; } catch (_) {}`
          const explicitImportOverrides = new Set([
            'bindOutsideClickClose',
            'bindPressable',
            'downloadBlobAsAttachment',
            'downloadUrlAsAttachment',
            'applyMobileTextInputDefaults',
            'focusAnyComposerInput',
            'focusComposerInput',
            'focusElement',
            'focusVisibleComposerInput',
            'hideWorkspaceOverlay',
            'invalidateOptionsSecrets',
            'refocusComposerAfterAction',
            'shellPromptWrap',
            'showConfirm',
          ])
          const explicitGlobalOverride = explicitImportOverrides.has(importedName)
            ? `if (typeof __darklabExtractGlobals !== 'undefined' && __darklabExtractGlobals && __darklabExtractGlobals.${importedName} !== undefined) return __darklabExtractGlobals.${importedName}; `
            : ''
          const globalLookup = sameNameHelperFallback
            ? `if (g && g.${importedName} !== undefined) return g.${importedName}; if (w && w.${importedName} !== undefined) return w.${importedName};`
            : `if (g && g.__darklabExtractPreferGlobalThis && g.${importedName} !== undefined) return g.${importedName}; if (w && w.${importedName} !== undefined) return w.${importedName};`;
          const fallbackLookup = commandRegistryBridgeImport && localDeclarationPattern.test(sourceText)
            ? 'return undefined;'
            : `${globalLookup} return g ? g.${importedName} : undefined;`;
          return `var ${localName} = (() => { ${explicitGlobalOverride}${bareFallback} const g = typeof globalThis !== 'undefined' ? globalThis : undefined; const w = typeof window !== 'undefined' ? window : undefined; ${fallbackLookup} })();`
        })
        .filter(Boolean)
        .join('\n')
    })
    .replace(/^\s*import\s+[\s\S]*?;\s*/gm, '')
    .replace(/export\s*\{([\s\S]*?)\};?/g, (_match, exportsBlock) => {
      const assignments = exportsBlock
        .split(',')
        .map((specifier) => specifier.trim())
        .filter(Boolean)
        .map((specifier) => {
          const [localName, exportedName = localName] = specifier
            .split(/\s+as\s+/)
            .map((part) => part.trim())
          if (!localName || !exportedName) return ''
          return `try { if (typeof ${localName} !== 'undefined' && !(typeof __darklabExtractGlobals !== 'undefined' && __darklabExtractGlobals && __darklabExtractGlobals.${exportedName} !== undefined)) __darklabExtractExportTarget.${exportedName} = ${localName}; } catch (_) {}`
        })
        .filter(Boolean)
        .join(' ')
      if (!assignments) return ''
      return `\n;(() => { const __darklabExtractExportTarget = typeof window !== 'undefined' ? window : (typeof globalThis !== 'undefined' ? globalThis : null); if (!__darklabExtractExportTarget) return; ${assignments} })();\n`
    })
    .replace(/^export\s+(?:const|let|var)\s+\{[^;]+;\s*$/gm, '')
    .replace(/^export\s+\{[^;]+;\s*$/gm, '')
    .replace(/\blet\s+(imported[A-Z]\w*)\s*;/g, 'var $1;')
    .replace(
      /^const\s+(DarklabDismissible|DarklabTabStripEdges|applyMobileTextInputDefaults|blurActiveElement|blurVisibleComposerInput|blurVisibleComposerInputIfMobile|closeAppSelects|enhanceAppSelects|focusAnyComposerInput|focusComposerInput|focusElement|focusVisibleComposerInput|getActiveComposerInput|getComposerInputs|getComposerValue|getMobileKeyboardOffsetBaseline|getMobileViewportClosedHeight|getVisibleComposerInput|handleComposerInputChange|hideAcDropdown|hideFaqOverlay|hideHistoryPanel|hideMobileMenu|hideModalOverlay|hideOptionsOverlay|hidePanelOverlay|hideSearchBar|hideShortcutsOverlay|hideTabKillBtn|hideThemeOverlay|hideWorkflowsOverlay|hideWorkspaceOverlay|isAcDropdownOpen|isActiveTabRunning|isFaqOverlayOpen|isHistoryPanelOpen|isMobileMenuOpen|isOptionsOverlayOpen|isPanelOverlayOpen|isSearchBarOpen|isShortcutsOverlayOpen|isThemeOverlayOpen|isWorkflowsOverlayOpen|isWorkspaceOverlayOpen|markInteractionSurfaceReady|portalDropdownMenu|refocusComposerAfterAction|setComposerValue|setVisibilityState|showAcDropdown|showFaqOverlay|showMobileMenu|showModalOverlay|showPanelOverlay|showSearchBar|showShortcutsOverlay|showTabKillBtn|showWorkflowsOverlay|showWorkspaceOverlay|syncAppSelect|syncComposerSelection|syncFocusedComposerState|syncMobileComposerKeyboardState|syncModalOverlayState|syncRunButtonDisabled|togglePanelOverlay|unportalDropdownMenu|bindDisclosure|bindFocusTrap|bindPressable)\s+=/gm,
      '',
    )
    .replace(/\bconst\s+bindPressable\s+=/g, 'var bindPressable =')
    .replace(/\bconst\s+bindOutsideClickClose\s+=/g, 'var bindOutsideClickClose =')
    .replace(
      /^const\s+(closeAtlas|closeCommandCatalogModal|closeProviderStatusModal|closeProjectWorkspace|closeSchedulesModal|closeWatchersModal|closeWorkflowEditor|ensureWorkflowCatalogLoaded|isAtlasOverlayOpen|isCommandCatalogOverlayOpen|isCommandRegistryOverlayOpen|isHistoryCompareOverlayOpen|isHistoryRunOverlayOpen|isProviderStatusModalOpen|isProjectWorkspaceOpen|isSchedulesOverlayOpen|isWatchersOverlayOpen|loadWorkflows|openWorkflowEditor|renderWorkflowItems)\s+=/gm,
      '',
    )
    .replace(
      /^const\s+(closeFindingTriageEditor|compactTriage|isFindingTriageEditorOpen|openFindingTriageEditor|verificationStatusLabel|verificationStatusTone|verificationStates)\s+=/gm,
      '',
    )
    .replace(
      /^const\s+(APP_STATE_API|emitUiEvent|getActiveTab|getActiveTabId|getAutocompleteState|getAppState|getComposerState|getTab|getTabs|getWelcomeState|onUiEvent|resetAppState|resetComposerState|setActiveTabId|setAutocompleteState|setComposerState|setTabs|setWelcomeState)\s+=/gm,
      '',
    )
}

const STATE_SRC = stripEsmExports(readFileSync(resolve(REPO_ROOT, 'app/static/js/core/state.js'), 'utf8'))
const UI_HELPERS_SRC = stripEsmExports(readFileSync(resolve(REPO_ROOT, 'app/static/js/ui/ui_helpers.js'), 'utf8'))
const UI_PRESSABLE_SRC = stripEsmExports(readFileSync(resolve(REPO_ROOT, 'app/static/js/ui/ui_pressable.js'), 'utf8'))
const UI_DISCLOSURE_SRC = stripEsmExports(readFileSync(resolve(REPO_ROOT, 'app/static/js/ui/ui_disclosure.js'), 'utf8'))
const UI_DISMISSIBLE_SRC = stripEsmExports(readFileSync(resolve(REPO_ROOT, 'app/static/js/ui/ui_dismissible.js'), 'utf8'))
const UI_OUTSIDE_CLICK_SRC = stripEsmExports(readFileSync(resolve(REPO_ROOT, 'app/static/js/ui/ui_outside_click.js'), 'utf8'))
const UI_FOCUS_TRAP_SRC = stripEsmExports(readFileSync(resolve(REPO_ROOT, 'app/static/js/ui/ui_focus_trap.js'), 'utf8'))
const UI_CLEANUP_REASONS_SRC = stripEsmExports(readFileSync(resolve(REPO_ROOT, 'app/static/js/ui/cleanup_reasons.js'), 'utf8'))

const APP_STATE_SEED_KEYS = [
  'tabs',
  'activeTabId',
  'acSuggestions',
  'acContextRegistry',
  'acWordlists',
  'acSpecialCommands',
  'acBuiltinCommandRoots',
  'sessionVariables',
  'acFiltered',
  'acIndex',
  'acSuppressInputOnce',
]

const APP_STATE_BINDING_KEYS = [
  'tabs',
  'activeTabId',
  'acSuggestions',
  'acContextRegistry',
  'acWordlists',
  'acSpecialCommands',
  'acBuiltinCommandRoots',
  'sessionVariables',
  'acFiltered',
  'acIndex',
  'acSuppressInputOnce',
  'searchMatches',
  'searchMatchIdx',
  'searchCaseSensitive',
  'searchRegexMode',
  'searchScope',
  'searchDiscoverabilityPrompted',
  'searchSignalCounts',
  'cmdHistory',
  'recentPreviewHistory',
  '_cmdHistoryNavIndex',
  '_cmdHistoryNavDraft',
  '_suspendCmdHistoryNavReset',
  'pendingHistAction',
  '_welcomeActive',
  '_welcomeDone',
  '_welcomeTabId',
  '_welcomeBanner',
  '_welcomeLiveLine',
  '_welcomeHintNode',
  '_welcomeStatusNodes',
  '_welcomePlan',
  '_welcomeNextBlockIndex',
  '_welcomeSettleRequested',
  '_welcomePromptAfterSettle',
  '_welcomeBootPending',
  '_composerValue',
  '_composerSelectionStart',
  '_composerSelectionEnd',
  '_composerActiveInput',
  '_mobileKeyboardOffsetBaseline',
  '_mobileViewportClosedHeight',
  '_mobileKeyboardLastOpenOffset',
  'timerInterval',
  'timerStart',
  'pendingKillTabId',
]

const WINDOW_GLOBAL_SEED_EXCLUDES = new Set([
  'window',
  'document',
  'localStorage',
  'sessionStorage',
  'setTimeout',
  'clearTimeout',
  'setInterval',
  'clearInterval',
  'URL',
])

const WINDOW_GLOBAL_RESET_KEYS = [
  'AnsiUp',
  'appendLines',
  'confirmClearSessionToken',
  'createWorkspaceDirectory',
  'downloadWorkspaceFile',
  'getWorkspaceAutocompleteDirectoryHints',
  'getWorkspaceAutocompleteFileHints',
  'getWorkspaceDirectoryEntries',
  'handleConfigCommand',
  'handleSecretCommand',
  'handleThemeCommand',
  'handleTourCommand',
  'handleWorkflowTerminalCommand',
  'isProjectWorkspaceOpen',
  'moveWorkspacePath',
  'normalizeWorkspaceCommandPath',
  'notifyProjectWorkspaceChanged',
  'openWorkspaceEditorFromCommand',
  'readWorkspaceFile',
  'refreshActiveProjectContext',
  'refreshProjectWorkspace',
  'refreshWorkspaceFileCache',
  'setComposerPromptMode',
  'teamScopeDeniedMessage',
  'workspaceCanWrite',
  'workspaceDisplayPath',
]

const WINDOW_GLOBAL_PROTECTED_FUNCTIONS = new Set([
  'blurVisibleComposerInput',
  'blurVisibleComposerInputIfMobile',
  'focusAnyComposerInput',
  'focusComposerInput',
  'focusElement',
  'focusVisibleComposerInput',
  'getActiveComposerInput',
  'getComposerInputs',
  'getVisibleComposerInput',
  'handleComposerInputChange',
  'refocusComposerAfterAction',
  'setMobileKeyboardOpenState',
  'setMobileViewportClosedHeight',
  'syncComposerSelection',
  'syncFocusedComposerState',
  'syncMobileComposerKeyboardState',
])

function windowGlobalResetSource() {
  return WINDOW_GLOBAL_RESET_KEYS
    .map((name) => `try {
      if (typeof window !== 'undefined') delete window[${JSON.stringify(name)}];
      if (typeof globalThis !== 'undefined') delete globalThis[${JSON.stringify(name)}];
    } catch (_) {}`)
    .join('\n')
}

function appStateSeedSource(globals) {
  return APP_STATE_SEED_KEYS
    .filter((name) => Object.prototype.hasOwnProperty.call(globals, name))
    .map((name) => `if (typeof APP_STATE_API !== 'undefined' && APP_STATE_API && typeof ${name} !== 'undefined') APP_STATE_API.getState().${name} = ${name};`)
    .join('\n')
}

function windowGlobalSeedSource(globals) {
  return Object.keys(globals)
    .filter((name) => !WINDOW_GLOBAL_SEED_EXCLUDES.has(name))
    .map((name) => `try {
      const seededValue = __darklabExtractGlobals[${JSON.stringify(name)}];
      const protectedFunction = ${WINDOW_GLOBAL_PROTECTED_FUNCTIONS.has(name) ? 'true' : 'false'};
      const skipSeededValue = protectedFunction;
      if (!skipSeededValue && seededValue !== undefined && seededValue !== null) {
        if (typeof window !== 'undefined') window[${JSON.stringify(name)}] = seededValue;
        if (typeof globalThis !== 'undefined') globalThis[${JSON.stringify(name)}] = seededValue;
      }
    } catch (_) {}`)
    .join('\n')
}

function dismissibleWindowBridgeSource() {
  return `
try {
  if (typeof DarklabDismissible !== 'undefined' && DarklabDismissible) {
    if (typeof window !== 'undefined') {
      window.bindDismissible = DarklabDismissible.bindDismissible;
      window.closeTopmostDismissible = DarklabDismissible.closeTopmostDismissible;
    }
    if (typeof globalThis !== 'undefined') {
      globalThis.bindDismissible = DarklabDismissible.bindDismissible;
      globalThis.closeTopmostDismissible = DarklabDismissible.closeTopmostDismissible;
    }
  }
} catch (_) {}`
}

function resetDismissibleRegistrySource() {
  return `
try {
  if (typeof window !== 'undefined') delete window.__darklabDismissibleRegistry;
  if (typeof globalThis !== 'undefined') delete globalThis.__darklabDismissibleRegistry;
} catch (_) {}`
}

function stateWindowMirrorSource() {
  return `
try {
  if (typeof window !== 'undefined' && typeof globalThis !== 'undefined' && globalThis.APP_STATE_API) {
    window.APP_STATE_API = globalThis.APP_STATE_API;
    window.APP_STATE = globalThis.APP_STATE;
    window.getAppState = globalThis.getAppState;
    window.resetAppState = globalThis.resetAppState;
    window.getTabs = globalThis.getTabs;
    window.setTabs = globalThis.setTabs;
    window.getActiveTabId = globalThis.getActiveTabId;
    window.setActiveTabId = globalThis.setActiveTabId;
    window.getActiveTab = globalThis.getActiveTab;
    window.getTab = globalThis.getTab;
    window.getAutocompleteState = globalThis.getAutocompleteState;
    window.setAutocompleteState = globalThis.setAutocompleteState;
    window.getComposerState = globalThis.getComposerState;
    window.setComposerState = globalThis.setComposerState;
    window.resetComposerState = globalThis.resetComposerState;
    window.getWelcomeState = globalThis.getWelcomeState;
    window.setWelcomeState = globalThis.setWelcomeState;
    window.emitUiEvent = globalThis.emitUiEvent;
    window.onUiEvent = globalThis.onUiEvent;
  }
} catch (_) {}
`
}

function resetAppStateSource() {
  return `
try {
  if (typeof APP_STATE_API !== 'undefined' && APP_STATE_API && typeof APP_STATE_API.reset === 'function') {
    APP_STATE_API.reset();
  }
} catch (_) {}
`
}

function testStateBindingSource() {
  return `
try {
  const __darklabStateTargets = [typeof globalThis !== 'undefined' ? globalThis : null, typeof window !== 'undefined' ? window : null].filter(Boolean);
  for (const __darklabStateName of ${JSON.stringify(APP_STATE_BINDING_KEYS)}) {
    for (const __darklabStateTarget of __darklabStateTargets) {
      Object.defineProperty(__darklabStateTarget, __darklabStateName, {
        configurable: true,
        enumerable: true,
        get() {
          return APP_STATE_API.getState()[__darklabStateName];
        },
        set(value) {
          APP_STATE_API.getState()[__darklabStateName] = value;
        },
      });
    }
  }
} catch (_) {}
`
}

/** Minimal but complete in-memory Storage implementation. */
export class MemoryStorage {
  constructor() {
    this._data = Object.create(null)
  }
  getItem(k) {
    return Object.prototype.hasOwnProperty.call(this._data, k) ? this._data[k] : null
  }
  setItem(k, v) {
    this._data[k] = String(v)
  }
  removeItem(k) {
    delete this._data[k]
  }
  clear() {
    this._data = Object.create(null)
  }
  get length() {
    return Object.keys(this._data).length
  }
  key(n) {
    return Object.keys(this._data)[n] ?? null
  }
}

/**
 * Load a browser JS file and return the requested named functions together with
 * the MemoryStorage instance they operate on.
 *
 * Returned object: { [name]: fn, ..., _storage: MemoryStorage }
 */
export function fromScript(relPath, ...names) {
  const src =
    STATE_SRC +
    '\n' +
    resetAppStateSource() +
    '\n' +
    testStateBindingSource() +
    '\n' +
    stripEsmExports(readFileSync(resolve(REPO_ROOT, relPath), 'utf8'))
  const returnExpr = `\nreturn { ${names.join(', ')} };`
  const storage = new MemoryStorage()
  // Pass a minimal APP_CONFIG stub so references inside function bodies don't
  // throw a ReferenceError if those functions are ever called in the tests.
  const fns = new Function('localStorage', 'APP_CONFIG', src + returnExpr)(storage, {
    recent_commands_limit: 20,
  })
  return { ...fns, _storage: storage }
}

/**
 * Load a browser JS file into a custom execution context and return the
 * requested named bindings.
 */
export function fromDomScript(relPath, globals, ...names) {
  const src =
    STATE_SRC +
    '\n' +
    resetAppStateSource() +
    '\n' +
    stateWindowMirrorSource() +
    '\n' +
    testStateBindingSource() +
    '\n' +
    windowGlobalResetSource() +
    '\n' +
    windowGlobalSeedSource(globals) +
    '\n' +
    appStateSeedSource(globals) +
    '\n' +
    UI_HELPERS_SRC +
    '\n' +
    windowGlobalSeedSource(globals) +
    '\n' +
    UI_PRESSABLE_SRC +
    '\n' +
    UI_DISCLOSURE_SRC +
    '\n' +
    resetDismissibleRegistrySource() +
    '\n' +
    UI_DISMISSIBLE_SRC +
    '\n' +
    dismissibleWindowBridgeSource() +
    '\n' +
    UI_OUTSIDE_CLICK_SRC +
    '\n' +
    UI_FOCUS_TRAP_SRC +
    '\n' +
    UI_CLEANUP_REASONS_SRC +
    '\n' +
    stripEsmExports(readFileSync(resolve(REPO_ROOT, relPath), 'utf8'))
  const globalNames = ['__darklabExtractGlobals', ...Object.keys(globals)]
  const globalValues = [globals, ...Object.values(globals)]
  const returnExpr = `\nreturn { ${names.join(', ')} };`
  const fns = new Function(...globalNames, src + returnExpr)(...globalValues)
  return fns
}

/**
 * Load one or more browser JS files into a custom execution context and return
 * a custom object literal expression.
 *
 * @param {string} [initCode] - Optional JS snippet injected after state.js and
 *   ui_helpers.js but before the script files. Injected globals are in scope,
 *   so callers can
 *   seed shared state: e.g. `'setTabs(tabs); setActiveTabId(activeTabId);'`.
 */
export function fromDomScripts(relPaths, globals, returnExpr, initCode = '') {
  const src =
    STATE_SRC +
    '\n' +
    resetAppStateSource() +
    '\n' +
    stateWindowMirrorSource() +
    '\n' +
    testStateBindingSource() +
    '\n' +
    windowGlobalResetSource() +
    '\n' +
    windowGlobalSeedSource(globals) +
    '\n' +
    appStateSeedSource(globals) +
    '\n' +
    UI_HELPERS_SRC +
    '\n' +
    windowGlobalSeedSource(globals) +
    '\n' +
    UI_PRESSABLE_SRC +
    '\n' +
    UI_DISCLOSURE_SRC +
    '\n' +
    resetDismissibleRegistrySource() +
    '\n' +
    UI_DISMISSIBLE_SRC +
    '\n' +
    dismissibleWindowBridgeSource() +
    '\n' +
    UI_OUTSIDE_CLICK_SRC +
    '\n' +
    UI_FOCUS_TRAP_SRC +
    '\n' +
    UI_CLEANUP_REASONS_SRC +
    '\n' +
    windowGlobalSeedSource(globals) +
    '\n' +
    dismissibleWindowBridgeSource() +
    '\n' +
    initCode +
    '\n' +
    relPaths.map((relPath) => stripEsmExports(readFileSync(resolve(REPO_ROOT, relPath), 'utf8'))).join('\n')
  const globalNames = ['__darklabExtractGlobals', ...Object.keys(globals)]
  const globalValues = [globals, ...Object.values(globals)]
  return new Function(...globalNames, `${src}\nreturn ${returnExpr};`)(...globalValues)
}
