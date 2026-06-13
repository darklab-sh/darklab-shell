// Global shortcuts-overlay keyboard handler.
//
// Opens the shortcuts overlay with "?" when the current text field is empty,
// while letting literal question marks type normally inside non-empty inputs.
document.addEventListener('keydown', e => {
  if (e.key !== '?') return;
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  const global = typeof window !== 'undefined' ? window : {};
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
        (ae === global.cmdInput || ae === global.mobileCmdInput)
        && typeof global.syncFocusedComposerState === 'function'
      ) {
        global.syncFocusedComposerState(ae);
      }
      const raw = isEditable ? (ae.textContent || '') : (ae.value || '');
      if (raw.length > 0) return;
    }
  }
  e.preventDefault();
  e.stopImmediatePropagation();
  if (
    global._welcomeActive
    && typeof global.activeTabId !== 'undefined'
    && typeof global.welcomeOwnsTab === 'function'
    && global.welcomeOwnsTab(global.activeTabId)
    && typeof global.requestWelcomeSettle === 'function'
  ) {
    global.requestWelcomeSettle(global.activeTabId);
  }
  if (typeof global.isShortcutsOverlayOpen === 'function' && global.isShortcutsOverlayOpen()) {
    if (typeof global.closeShortcuts === 'function') global.closeShortcuts();
  } else {
    if (typeof global.openShortcuts === 'function') global.openShortcuts();
  }
}, true);
