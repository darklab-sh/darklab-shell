// Single source of truth for press-to-activate UI surfaces.
//
// Before this helper existed, every pressable control in the shell (HUD
// action buttons, history/recents row actions, rail section headers, FAQ
// questions, welcome-command loaders, mobile sheet items, save-menu items)
// reinvented its own click / keyboard / press-clear / refocus contract.
// The subtle inconsistencies produced user-visible bugs: sticky press
// highlights on mobile, missing Enter/Space activation on role="button"
// divs, composer focus not returning after a chrome click.
//
// bindPressable(el, { onActivate, ... }) is the one place those behaviors
// live. It follows the bindMobileSheet() prior-art shape from
// mobile_sheet.js: one function, element + options bag, asserts its
// preconditions, owns the full behavior contract, idempotent via a
// data-pressable-bound guard.
//
// Behavior contract:
// - click activates onActivate(event)
// - Enter/Space activate onActivate for non-<button> elements (<button>
//   gets keyboard activation from the browser for free and should not be
//   double-fired)
// - After activation: el.blur() if el owns focus (clears native :focus
//   styling), then (if refocusComposer) refocusComposerAfterAction() to
//   send focus back to the visible composer
// - clearPressStyle: opt-in CSS-state escape hatch — the helper toggles
//   data-pressable-clearing="1" on the element for one animation frame,
//   so per-surface CSS can override sticky :hover / :active / .is-pressed
//   residue without each call site re-inventing the toggle
// - preventFocusTheft: binds pointerdown → preventDefault so pressing a
//   chrome button does not pull focus off the composer (matches the
//   pointerdown + preventDefault pattern used today around the mobile
//   edit-bar buttons)
(function (global) {
  'use strict';

  function _isNativeButton(el) {
    return el && typeof el.tagName === 'string' && el.tagName.toUpperCase() === 'BUTTON';
  }

  function _clearPress(el) {
    if (!el || !el.dataset) return;
    el.dataset.pressableClearing = '1';
    const clear = () => {
      if (el.dataset) delete el.dataset.pressableClearing;
    };
    if (typeof requestAnimationFrame === 'function') {
      requestAnimationFrame(() => requestAnimationFrame(clear));
    } else {
      setTimeout(clear, 16);
    }
  }

  function _afterActivate(el, options) {
    if (document.activeElement === el && typeof el.blur === 'function') {
      try { el.blur(); } catch (_) { /* non-critical */ }
    }
    if (options.clearPressStyle) _clearPress(el);
    if (options.refocusComposer !== false && typeof global.refocusComposerAfterAction === 'function') {
      global.refocusComposerAfterAction({
        preventScroll: options.preventScroll !== false,
        defer: !!options.defer,
      });
    }
  }

  function bindPressable(el, opts) {
    if (!el || !opts || typeof opts.onActivate !== 'function') return;
    if (el.dataset && el.dataset.pressableBound === '1') return;
    if (el.dataset) el.dataset.pressableBound = '1';

    const onActivate = opts.onActivate;
    const options = {
      refocusComposer: opts.refocusComposer !== false,
      preventFocusTheft: !!opts.preventFocusTheft,
      preventScroll: opts.preventScroll !== false,
      defer: !!opts.defer,
      clearPressStyle: !!opts.clearPressStyle,
    };

    if (options.preventFocusTheft) {
      el.addEventListener('pointerdown', e => {
        // Only the primary button / primary touch contact should block
        // focus movement — right-click / multi-touch pass through.
        if (typeof e.button === 'number' && e.button !== 0) return;
        e.preventDefault();
      });
    }

    el.addEventListener('click', e => {
      try { onActivate(e); } finally { _afterActivate(el, options); }
    });

    if (!_isNativeButton(el)) {
      el.addEventListener('keydown', e => {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        e.preventDefault();
        try { onActivate(e); } finally { _afterActivate(el, options); }
      });
    }
  }

  global.bindPressable = bindPressable;
})(typeof window !== 'undefined' ? window : globalThis);
