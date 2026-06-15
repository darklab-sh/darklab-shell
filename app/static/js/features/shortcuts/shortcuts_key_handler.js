// Global shortcuts-overlay keyboard handler.
//
// Opens the shortcuts overlay with "?" when the current text field is empty,
// while letting literal question marks type normally inside non-empty inputs.
import {
  cmdInput as importedCmdInput,
  mobileCmdInput as importedMobileCmdInput,
} from '../../core/dom.js';
import {
  getActiveTabId as importedGetActiveTabId,
  getWelcomeState as importedGetWelcomeState,
} from '../../core/state.js';
import {
  isShortcutsOverlayOpen as importedIsShortcutsOverlayOpen,
  syncFocusedComposerState as importedSyncFocusedComposerState,
} from '../../ui/ui_helpers.js';
import {
  closeShortcuts as importedCloseShortcuts,
  openShortcuts as importedOpenShortcuts,
} from '../../controller.js';
import {
  requestWelcomeSettle as importedRequestWelcomeSettle,
  welcomeOwnsTab as importedWelcomeOwnsTab,
} from '../../welcome.js';

function _shortcutsGlobal() {
  return typeof window !== 'undefined' ? window : {};
}

function _shortcutsCmdInput() {
  return (typeof importedCmdInput !== 'undefined' && importedCmdInput)
    || _shortcutsGlobal().cmdInput;
}

function _shortcutsMobileCmdInput() {
  return (typeof importedMobileCmdInput !== 'undefined' && importedMobileCmdInput)
    || _shortcutsGlobal().mobileCmdInput;
}

function _shortcutsSyncFocusedComposerState(input) {
  const sync = (typeof importedSyncFocusedComposerState !== 'undefined' && importedSyncFocusedComposerState)
    || null;
  if (typeof sync === 'function') sync(input);
}

function _shortcutsWelcomeState() {
  if (typeof importedGetWelcomeState !== 'undefined' && typeof importedGetWelcomeState === 'function') {
    return importedGetWelcomeState();
  }
  return { active: false };
}

function _shortcutsActiveTabId() {
  if (typeof importedGetActiveTabId !== 'undefined' && typeof importedGetActiveTabId === 'function') {
    return importedGetActiveTabId();
  }
  return null;
}

document.addEventListener('keydown', e => {
  if (e.key !== '?') return;
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const global = _shortcutsGlobal();
  const ae = document.activeElement;
  if (ae) {
    const tag = (ae.tagName || '').toLowerCase();
    const isEditable = ae.isContentEditable;
    const isTextInput =
      tag === 'textarea' ||
      (tag === 'input' && !/^(checkbox|radio|button|submit|reset|range|color|file)$/i.test(ae.type || '')) ||
      isEditable;
    if (tag === 'select') return;
    if (isTextInput) {
      if (
        (ae === _shortcutsCmdInput() || ae === _shortcutsMobileCmdInput())
      ) {
        _shortcutsSyncFocusedComposerState(ae);
      }
      const raw = isEditable ? (ae.textContent || '') : (ae.value || '');
      if (raw.length > 0) return;
    }
  }
  e.preventDefault();
  e.stopImmediatePropagation();
  const welcomeState = _shortcutsWelcomeState();
  const activeId = _shortcutsActiveTabId();
  if (
    welcomeState.active
    && typeof activeId !== 'undefined'
    && typeof importedWelcomeOwnsTab === 'function'
    && importedWelcomeOwnsTab(activeId)
    && typeof importedRequestWelcomeSettle === 'function'
  ) {
    importedRequestWelcomeSettle(activeId);
  }
  if (typeof importedIsShortcutsOverlayOpen === 'function' && importedIsShortcutsOverlayOpen()) {
    if (typeof importedCloseShortcuts === 'function') importedCloseShortcuts();
  } else {
    if (typeof importedOpenShortcuts === 'function') importedOpenShortcuts();
  }
}, true);
