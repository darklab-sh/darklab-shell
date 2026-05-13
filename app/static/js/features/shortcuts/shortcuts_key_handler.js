// Global shortcuts-overlay keyboard handler.
//
// Opens the shortcuts overlay with "?" when the current text field is empty,
// while letting literal question marks type normally inside non-empty inputs.
document.addEventListener('keydown', e => {
  if (e.key !== '?') return;
  if (e.ctrlKey || e.metaKey || e.altKey) return;
  if (typeof _welcomeActive !== 'undefined' && _welcomeActive) return;
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
        (ae === cmdInput || ae === mobileCmdInput)
        && typeof syncFocusedComposerState === 'function'
      ) {
        syncFocusedComposerState(ae);
      }
      const raw = isEditable ? (ae.textContent || '') : (ae.value || '');
      if (raw.length > 0) return;
    }
  }
  e.preventDefault();
  e.stopImmediatePropagation();
  if (typeof isShortcutsOverlayOpen === 'function' && isShortcutsOverlayOpen()) {
    closeShortcuts();
  } else {
    openShortcuts();
  }
}, true);
