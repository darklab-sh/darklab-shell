// Shared focus-trap helper for modal surfaces.
//
// Dialogs (confirm modals, options, theme picker, FAQ, workflows, save menu)
// should hold keyboard focus inside the card until they close — otherwise
// Tab falls through to the document behind the backdrop and cycles into
// rail / tab / HUD buttons the user cannot see or interact with.
//
// bindFocusTrap(container) installs one keydown listener on `container`;
// on Tab (or Shift+Tab), it computes the container's currently focusable
// descendants and wraps focus at the start/end of the list. Focus movement
// inside the container (Tab between two buttons in the middle) is left to
// the browser so native Tab behavior still applies; the helper only acts
// at the boundary to keep focus contained.
//
// Shape follows bindPressable / bindDismissible: one function, element +
// optional opts, idempotent via data-focus-trap-bound, returns a disposable.
(function (global) {
  'use strict';

  // Matches focusable elements that are actually reachable via keyboard.
  // Excludes [tabindex="-1"] (programmatic-only) and [disabled] on inputs /
  // buttons. The :not([hidden]) guard is a coarse visibility filter; the
  // fine-grained visibility check runs in _focusables() below.
  const FOCUSABLE_SELECTOR = [
    'button:not([disabled])',
    'a[href]',
    'input:not([disabled])',
    'select:not([disabled])',
    'textarea:not([disabled])',
    '[tabindex]:not([tabindex="-1"])',
  ].join(', ');

  function _isVisible(el) {
    if (!el) return false;
    if (el.hidden) return false;
    if (typeof el.closest === 'function' && el.closest('[hidden]')) return false;
    // display:none check — the options modal toggles session-token buttons
    // between visible and `style="display:none"` based on token state. If
    // the trap includes a display:none button as its last focusable, Tab
    // from the *actual* last visible button won't match `active === last`
    // and focus leaks out of the card. Works in both jsdom (style.display
    // is reflected in getComputedStyle) and real browsers.
    if (typeof window !== 'undefined' && typeof window.getComputedStyle === 'function') {
      const style = window.getComputedStyle(el);
      if (style && style.display === 'none') return false;
    }
    return true;
  }

  function _focusables(container) {
    if (!container || typeof container.querySelectorAll !== 'function') return [];
    const nodes = Array.from(container.querySelectorAll(FOCUSABLE_SELECTOR));
    return nodes.filter(_isVisible);
  }

  function bindFocusTrap(container) {
    if (!container) return null;
    if (container.dataset && container.dataset.focusTrapBound === '1') return null;
    if (container.dataset) container.dataset.focusTrapBound = '1';

    const keydownHandler = (e) => {
      if (e.key !== 'Tab') return;
      const list = _focusables(container);
      if (list.length === 0) return;
      const first = list[0];
      const last = list[list.length - 1];
      const active = document.activeElement;
      if (e.shiftKey) {
        if (active === first || !container.contains(active)) {
          e.preventDefault();
          if (typeof last.focus === 'function') last.focus();
        }
      } else {
        if (active === last || !container.contains(active)) {
          e.preventDefault();
          if (typeof first.focus === 'function') first.focus();
        }
      }
    };

    container.addEventListener('keydown', keydownHandler);

    return {
      dispose: () => {
        container.removeEventListener('keydown', keydownHandler);
        if (container.dataset) delete container.dataset.focusTrapBound;
      },
    };
  }

  global.bindFocusTrap = bindFocusTrap;
})(typeof window !== 'undefined' ? window : globalThis);
