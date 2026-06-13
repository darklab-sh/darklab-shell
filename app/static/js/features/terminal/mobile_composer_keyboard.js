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
  if (!useKeyboardOpen && innerHeight > 0 && typeof setMobileViewportClosedHeight === 'function') {
    setMobileViewportClosedHeight(innerHeight);
  }
  const h = useKeyboardOpen
    ? (visualHeight || innerHeight)
    : Math.max(innerHeight, visualHeight);
  if (!(h > 0)) return;
  document.documentElement.style.setProperty('--mobile-viewport-height', `${h}px`);
}

function queueMobileOutputTailRefresh({ keyboardOpen = null, delays = [0, 80, 180, 320] } = {}) {
  if (typeof _refreshFollowingOutputsAfterLayout !== 'function') return;
  delays.forEach(delay => {
    setTimeout(() => {
      if (!useMobileTerminalViewportMode()) return;
      if (!document.body) return;
      if (
        typeof keyboardOpen === 'boolean'
        && document.body.classList.contains('mobile-keyboard-open') !== keyboardOpen
      ) return;
      _refreshFollowingOutputsAfterLayout();
    }, delay);
  });
}

function syncMobileComposerKeyboard({ open = null } = {}) {
  if (typeof window === 'undefined') return;
  const offset = getMobileKeyboardOffset();
  const keyboardOpen = typeof syncMobileComposerKeyboardState === 'function'
    ? syncMobileComposerKeyboardState(offset, { open })
    : !!open;
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
    if (typeof setMobileKeyboardOpenState === 'function') setMobileKeyboardOpenState(false, { delay });
  };
  const resetClosedMobileKeyboardLayout = () => {
    if (typeof syncMobileComposerKeyboardState === 'function') {
      syncMobileComposerKeyboardState(0, { open: false });
    }
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
    if (typeof setComposerState === 'function') {
      setComposerState({
        value: mobileInput.value || '',
        selectionStart: typeof mobileInput.selectionStart === 'number' ? mobileInput.selectionStart : (mobileInput.value || '').length,
        selectionEnd: typeof mobileInput.selectionEnd === 'number' ? mobileInput.selectionEnd : (mobileInput.value || '').length,
        activeInput: 'mobile',
      });
    }
    if (typeof setMobileKeyboardOpenState === 'function') setMobileKeyboardOpenState(true);
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
        if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
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
  if (!mobileInput || !mobileRunBtn) return;
  // Submit handler — read the visible composer input and submit through the
  // shared command engine.
  function _mobileSubmit() {
    submitVisibleComposerCommand({ dismissKeyboard: true, focusAfterSubmit: false });
  }

  mobileRunBtn.addEventListener('click', _mobileSubmit);

  // Sync mobile input through the shared composer handler so autocomplete and
  // shared composer state stay on the same path.
  mobileInput.addEventListener('input', () => {
    handleComposerInputChange(mobileInput);
    const activeTab = typeof getActiveTab === 'function' ? getActiveTab() : null;
    if (activeTab && activeTab.st !== 'running') {
      activeTab.draftInput = typeof getComposerValue === 'function' ? getComposerValue() : (mobileInput.value || '');
      if (typeof schedulePersistTabSessionState === 'function') schedulePersistTabSessionState();
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
      if (typeof setComposerState === 'function') {
        setComposerState({
          value: mobileInput.value || '',
          selectionStart: typeof mobileInput.selectionStart === 'number' ? mobileInput.selectionStart : (mobileInput.value || '').length,
          selectionEnd: typeof mobileInput.selectionEnd === 'number' ? mobileInput.selectionEnd : (mobileInput.value || '').length,
          activeInput: 'mobile',
        });
      }
      syncShellPrompt();
    }, 0);
  });
}

if (typeof window !== 'undefined') {
  Object.assign(window, {
    syncMobileViewportHeight,
    queueMobileOutputTailRefresh,
    syncMobileComposerKeyboard,
    queueMobileComposerKeyboardSync,
    bindMobileComposerKeyboardListeners,
    bindMobileComposerSubmitAndInputListeners,
  });
}
