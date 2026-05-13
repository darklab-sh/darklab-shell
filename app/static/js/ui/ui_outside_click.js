// Single source of truth for ambient outside-click dismissal.
//
// Companion to bindDismissible: where bindDismissible owns
// backdrop-click for surfaces with a visible scrim, bindOutsideClickClose
// owns ambient-click dismissal for dropdown-style menus and side panels
// where clicks can land anywhere in the document (or anywhere in a
// scoped subtree) without a dimming overlay to intercept them.
//
// The key contract this helper encodes is the trigger-exemption rule:
// a disclosure's trigger button has its own click handler that toggles
// the panel. The outside-click listener must NOT close the panel when
// the click lands on the trigger, otherwise you get a close-then-reopen
// loop (or the panel never opens at all, depending on listener order).
//
// Before this helper, every call site hand-rolled the same pattern:
//   - triggerBtn.addEventListener('click', e => { e.stopPropagation(); ... });
//   - document.addEventListener('click', () => closeThePanel());
// and the stopPropagation() was the workaround for the missing trigger
// exemption. Register the trigger with bindOutsideClickClose and the
// helper skips clicks landing on it (or inside it), so the trigger's
// own handler no longer needs to stopPropagation.
//
// Unlike bindDismissible, this helper does NOT own Escape — callers that
// need Escape-to-close should layer a bindDismissible on the same surface
// (when it has modal/panel/sheet semantics), or rely on the owning
// modal/sheet's Escape cascade for nested dropdowns.
(function (global) {
  'use strict';

  function _toArray(input) {
    if (!input) return [];
    if (Array.isArray(input)) return input.filter(Boolean);
    return [input];
  }

  function bindOutsideClickClose(panel, opts) {
    if (!opts) return null;
    if (typeof opts.isOpen !== 'function') return null;
    if (typeof opts.onClose !== 'function') return null;
    // panel may be null when the caller has no single containing element
    // (e.g. the recents-sheet case where several sibling dropdowns share a
    // parent scope and exemption is expressed purely via a CSS selector).
    // In that case, panel.contains() is skipped and trigger + exemptSelectors
    // are the sole exemption channels.

    const isOpenFn = opts.isOpen;
    const onCloseFn = opts.onClose;
    const triggers = _toArray(opts.triggers);
    const exemptSelectors = _toArray(opts.exemptSelectors);
    const scope = opts.scope || (typeof document !== 'undefined' ? document : null);
    if (!scope || typeof scope.addEventListener !== 'function') return null;

    const handler = (e) => {
      if (!isOpenFn()) return;
      const target = e.target;
      if (!target) return;
      if (panel && panel.contains && panel.contains(target)) return;
      for (let i = 0; i < triggers.length; i += 1) {
        const t = triggers[i];
        if (!t) continue;
        if (t === target) return;
        if (t.contains && t.contains(target)) return;
      }
      if (exemptSelectors.length && typeof target.closest === 'function') {
        for (let i = 0; i < exemptSelectors.length; i += 1) {
          if (target.closest(exemptSelectors[i])) return;
        }
      }
      onCloseFn();
    };

    scope.addEventListener('click', handler);

    return {
      dispose: () => {
        scope.removeEventListener('click', handler);
      },
    };
  }

  global.bindOutsideClickClose = bindOutsideClickClose;
})(typeof window !== 'undefined' ? window : globalThis);
