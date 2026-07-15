// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { mobileRunBtn as importedMobileRunBtn } from '../../core/dom.js';
import { getActiveTab as importedGetActiveTab, setComposerState as importedSetComposerState } from '../../core/state.js';
import { _refreshFollowingOutputsAfterLayout as importedRefreshFollowingOutputsAfterLayout } from '../../output.js';
import { submitVisibleComposerCommand as importedSubmitVisibleComposerCommand } from '../../runner_bridge.js';
import { schedulePersistTabSessionState as importedSchedulePersistTabSessionState } from '../tabs/tab_session_state.js';
import {
  blurVisibleComposerInputIfMobile as importedBlurVisibleComposerInputIfMobile,
  getComposerValue as importedGetComposerValue,
  handleComposerInputChange as importedHandleComposerInputChange,
  setMobileKeyboardOpenState as importedSetMobileKeyboardOpenState,
  setMobileViewportClosedHeight as importedSetMobileViewportClosedHeight,
  syncMobileComposerKeyboardState as importedSyncMobileComposerKeyboardState,
} from '../../ui/ui_helpers.js';
import { handleComposerWordArrowShortcut } from './composer_editing.js';
import {
  hasComposerPromptHandler as importedHasComposerPromptHandler,
  syncShellPrompt as importedSyncShellPrompt,
} from './composer_prompt_bridge.js';
import {
  getMobileKeyboardOffset,
  syncMobileViewportState,
  useMobileTerminalViewportMode,
} from '../mobile/mobile_shell_layout.js';

const MOBILE_KEYBOARD_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

function _mobileKeyboardGlobalFunction(name) {
  const fn = MOBILE_KEYBOARD_GLOBAL?.[name];
  return typeof fn === 'function' ? fn : null;
}

function _mobileKeyboardRunButton() {
  return (typeof importedMobileRunBtn !== 'undefined' && importedMobileRunBtn)
    || (typeof document !== 'undefined' ? document.getElementById('mobile-run-btn') : null);
}

function _mobileKeyboardRefreshFollowingOutputs() {
  const refreshOutputs = (typeof importedRefreshFollowingOutputsAfterLayout !== 'undefined' && importedRefreshFollowingOutputsAfterLayout)
    || _mobileKeyboardGlobalFunction('_refreshFollowingOutputsAfterLayout');
  if (typeof refreshOutputs === 'function') refreshOutputs();
}

function _mobileKeyboardSyncShellPrompt() {
  const syncPrompt = (
    typeof importedHasComposerPromptHandler === 'function'
    && importedHasComposerPromptHandler('syncShellPrompt')
  ) ? importedSyncShellPrompt : _mobileKeyboardGlobalFunction('syncShellPrompt');
  if (typeof syncPrompt === 'function') syncPrompt();
}

function _mobileKeyboardSetComposerState(state) {
  const setState = (typeof importedSetComposerState !== 'undefined' && importedSetComposerState)
    || _mobileKeyboardGlobalFunction('setComposerState');
  if (typeof setState === 'function') setState(state);
}

function _mobileKeyboardBlurVisibleComposer() {
  const blurComposer = (typeof importedBlurVisibleComposerInputIfMobile !== 'undefined' && importedBlurVisibleComposerInputIfMobile)
    || _mobileKeyboardGlobalFunction('blurVisibleComposerInputIfMobile');
  if (typeof blurComposer === 'function') blurComposer();
}

function _mobileKeyboardHandleComposerInputChange(input) {
  const handleInput = (typeof importedHandleComposerInputChange !== 'undefined' && importedHandleComposerInputChange)
    || _mobileKeyboardGlobalFunction('handleComposerInputChange');
  if (typeof handleInput === 'function') handleInput(input);
}

function _mobileKeyboardGetActiveTab() {
  if (typeof importedGetActiveTab !== 'undefined' && typeof importedGetActiveTab === 'function') {
    return importedGetActiveTab();
  }
  const getActiveTab = _mobileKeyboardGlobalFunction('getActiveTab');
  return getActiveTab ? getActiveTab() : null;
}

function _mobileKeyboardGetComposerValue(input) {
  const getValue = (typeof importedGetComposerValue !== 'undefined' && importedGetComposerValue)
    || _mobileKeyboardGlobalFunction('getComposerValue');
  return typeof getValue === 'function' ? getValue() : (input && input.value || '');
}

function _mobileKeyboardSchedulePersistTabSessionState() {
  const schedulePersist = (typeof importedSchedulePersistTabSessionState !== 'undefined' && importedSchedulePersistTabSessionState)
    || _mobileKeyboardGlobalFunction('schedulePersistTabSessionState');
  if (typeof schedulePersist === 'function') schedulePersist();
}

function _mobileKeyboardSetOpen(open, options = {}) {
  const setOpen = (typeof importedSetMobileKeyboardOpenState !== 'undefined' && importedSetMobileKeyboardOpenState)
    || _mobileKeyboardGlobalFunction('setMobileKeyboardOpenState');
  if (setOpen) setOpen(open, options);
}

function _mobileKeyboardSetViewportClosedHeight(height) {
  const setClosedHeight = (typeof importedSetMobileViewportClosedHeight !== 'undefined' && importedSetMobileViewportClosedHeight)
    || _mobileKeyboardGlobalFunction('setMobileViewportClosedHeight');
  if (setClosedHeight) setClosedHeight(height);
}

function _mobileKeyboardSyncComposerState(offset, options = {}) {
  const syncState = (typeof importedSyncMobileComposerKeyboardState !== 'undefined' && importedSyncMobileComposerKeyboardState)
    || _mobileKeyboardGlobalFunction('syncMobileComposerKeyboardState');
  return syncState ? syncState(offset, options) : !!options.open;
}

function _mobileKeyboardSubmitVisibleComposerCommand(options = {}) {
  const submit = (typeof importedSubmitVisibleComposerCommand === 'function' && importedSubmitVisibleComposerCommand)
    || _mobileKeyboardGlobalFunction('submitVisibleComposerCommand');
  if (submit) submit(options);
}

function syncMobileViewportHeight({ keyboardOpen = null } = {}) {
  if (typeof document === 'undefined' || typeof window === 'undefined') return;
  const visualHeight = window.visualViewport ? Math.round(window.visualViewport.height) : 0;
  const innerHeight = Math.round(window.innerHeight || 0);
  const useKeyboardOpen = typeof keyboardOpen === 'boolean'
    ? keyboardOpen
    : !!(typeof document !== 'undefined'
      && document.body
      && document.body.classList
      && document.body.classList.contains('mobile-keyboard-open'));
  if (!useKeyboardOpen && innerHeight > 0) {
    _mobileKeyboardSetViewportClosedHeight(innerHeight);
  }
  const h = useKeyboardOpen
    ? (visualHeight || innerHeight)
    : Math.max(innerHeight, visualHeight);
  if (!(h > 0)) return;
  document.documentElement.style.setProperty('--mobile-viewport-height', `${h}px`);
}

function queueMobileOutputTailRefresh({ keyboardOpen = null, delays = [0, 80, 180, 320] } = {}) {
  delays.forEach(delay => {
    setTimeout(() => {
      if (!useMobileTerminalViewportMode()) return;
      if (!document.body) return;
      if (
        typeof keyboardOpen === 'boolean'
        && document.body.classList.contains('mobile-keyboard-open') !== keyboardOpen
      ) return;
      _mobileKeyboardRefreshFollowingOutputs();
    }, delay);
  });
}

export {
  bindMobileComposerKeyboardListeners,
  bindMobileComposerSubmitAndInputListeners,
  queueMobileComposerKeyboardSync,
  queueMobileOutputTailRefresh,
  syncMobileComposerKeyboard,
  syncMobileViewportHeight,
};

function syncMobileComposerKeyboard({ open = null } = {}) {
  if (typeof window === 'undefined') return;
  const offset = getMobileKeyboardOffset();
  const keyboardOpen = _mobileKeyboardSyncComposerState(offset, { open });
  syncMobileViewportHeight({ keyboardOpen });
  queueMobileOutputTailRefresh({ keyboardOpen, delays: keyboardOpen ? [0] : [0, 80, 180, 320] });
}

let _mobileComposerKeyboardSyncTimer = null;
function queueMobileComposerKeyboardSync(delay = 120) {
  if (typeof window === 'undefined') return;
  if (_mobileComposerKeyboardSyncTimer) clearTimeout(_mobileComposerKeyboardSyncTimer);
  _mobileComposerKeyboardSyncTimer = setTimeout(() => {
    _mobileComposerKeyboardSyncTimer = null;
    syncMobileComposerKeyboard();
  }, delay);
}

function bindMobileComposerKeyboardListeners(mobileInput) {
  if (!mobileInput || typeof window === 'undefined') return;
  const closeMobileKeyboard = (delay = 120) => {
    _mobileKeyboardSetOpen(false, { delay });
  };
  const resetClosedMobileKeyboardLayout = () => {
    _mobileKeyboardSyncComposerState(0, { open: false });
    syncMobileViewportHeight({ keyboardOpen: false });
  };
  const queueMobileViewportRecovery = (delays = [50, 180]) => {
    delays.forEach(delay => {
      setTimeout(() => {
        syncMobileComposerKeyboard();
        syncMobileViewportState();
      }, delay);
    });
  };
  if (window.visualViewport && typeof window.visualViewport.addEventListener === 'function') {
    window.visualViewport.addEventListener('resize', () => {
      syncMobileComposerKeyboard();
      queueMobileComposerKeyboardSync();
    });
  }
  mobileInput.addEventListener('focus', () => {
    _mobileKeyboardSetComposerState({
      value: mobileInput.value || '',
      selectionStart: typeof mobileInput.selectionStart === 'number' ? mobileInput.selectionStart : (mobileInput.value || '').length,
      selectionEnd: typeof mobileInput.selectionEnd === 'number' ? mobileInput.selectionEnd : (mobileInput.value || '').length,
      activeInput: 'mobile',
    });
    _mobileKeyboardSetOpen(true);
    syncMobileComposerKeyboard();
    queueMobileComposerKeyboardSync();
  });
  mobileInput.addEventListener('blur', () => {
    closeMobileKeyboard();
    syncMobileComposerKeyboard();
    queueMobileComposerKeyboardSync();
  });

  // When the user returns to the browser from another app, the OS may have
  // closed the keyboard without firing a visualViewport resize event, leaving
  // the stale mobile-keyboard-open class and --mobile-keyboard-offset on the
  // page.  Re-run a full viewport state sync after a short settle delay.
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) {
        closeMobileKeyboard(0);
        _mobileKeyboardBlurVisibleComposer();
        resetClosedMobileKeyboardLayout();
        return;
      }
      queueMobileViewportRecovery();
    });
  }
  window.addEventListener('focus', () => {
    queueMobileViewportRecovery([80, 220]);
  });
  window.addEventListener('pageshow', () => {
    queueMobileViewportRecovery([0, 120]);
  });
}

function bindMobileComposerSubmitAndInputListeners(mobileInput) {
  const runButton = _mobileKeyboardRunButton();
  if (!mobileInput || !runButton) return;
  // Submit handler — read the visible composer input and submit through the
  // shared command engine.
  function _mobileSubmit() {
    _mobileKeyboardSubmitVisibleComposerCommand({ dismissKeyboard: true, focusAfterSubmit: false });
  }

  runButton.addEventListener('click', _mobileSubmit);

  // Sync mobile input through the shared composer handler so autocomplete and
  // shared composer state stay on the same path.
  mobileInput.addEventListener('input', () => {
    _mobileKeyboardHandleComposerInputChange(mobileInput);
    const activeTab = _mobileKeyboardGetActiveTab();
    if (activeTab && activeTab.st !== 'running') {
      activeTab.draftInput = _mobileKeyboardGetComposerValue(mobileInput);
      _mobileKeyboardSchedulePersistTabSessionState();
    }
  });

  mobileInput.addEventListener('keydown', e => {
    if (typeof handleComposerWordArrowShortcut === 'function' && handleComposerWordArrowShortcut(e)) return;
    if (e.key === 'Enter') {
      e.preventDefault();
      _mobileSubmit();
    }
  });

  // Guard against something resetting the cursor to end synchronously after a
  // tap repositions it. Capture the cursor position at click time (iOS has
  // already placed it by then) and restore it on the next tick if it moved
  // specifically to end — the symptom of a spurious focus() or setSelectionRange
  // call clobbering the tap-to-reposition result.
  mobileInput.addEventListener('click', () => {
    if (!useMobileTerminalViewportMode()) return;
    if (typeof document === 'undefined' || document.activeElement !== mobileInput) return;
    const savedStart = mobileInput.selectionStart;
    const savedEnd   = mobileInput.selectionEnd;
    const valueLen   = (mobileInput.value || '').length;
    if (typeof savedStart !== 'number' || savedStart >= valueLen) return;
    setTimeout(() => {
      if (typeof document === 'undefined' || document.activeElement !== mobileInput) return;
      if (mobileInput.selectionStart >= (mobileInput.value || '').length) {
        mobileInput.setSelectionRange(savedStart, savedEnd);
      }
      _mobileKeyboardSetComposerState({
        value: mobileInput.value || '',
        selectionStart: typeof mobileInput.selectionStart === 'number' ? mobileInput.selectionStart : (mobileInput.value || '').length,
        selectionEnd: typeof mobileInput.selectionEnd === 'number' ? mobileInput.selectionEnd : (mobileInput.value || '').length,
        activeInput: 'mobile',
      });
      _mobileKeyboardSyncShellPrompt();
    }, 0);
  });
}

if (typeof window !== 'undefined') {
}
