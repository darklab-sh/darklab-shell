// Single source of truth for expandable/collapsible UI surfaces.
//
// Before this helper, each disclosure in the shell hand-rolled its own
// open/closed state, aria-expanded wiring, and panel visibility toggle.
// The five sites (FAQ items, desktop rail section headers, mobile
// timestamps sub-menu, mobile recents advanced-filter toggle, save-menu
// dropdowns) each got aria-expanded slightly wrong in a different way,
// and two of them omitted aria-expanded entirely.
//
// bindDisclosure(trigger, opts) composes on top of bindPressable so a
// disclosure trigger is always a fully-wired pressable (click +
// Enter/Space + optional press-style clearing + optional focus-theft
// prevention), and on top of that it owns:
//   - aria-expanded on the trigger (initial + on every toggle)
//   - optional panel class toggling (openClass set when open,
//     hiddenClass set when closed)
//   - an onToggle hook that receives the post-transition open state
//     (fired on user-initiated toggles and on imperative open()/close()/
//     toggle() calls — not on the initial sync, so callers don't pay
//     side-effect cost just from binding)
//
// Intentionally out of scope (Phase 4): outside-click dismiss, Escape-
// to-close, scrim-backed modals, sheet coordination. Those are separate
// behaviors with their own dismissal ordering and are handled by the
// dismissible-surface helpers.
(function (global) {
  'use strict';

  function _applyPanelState(panel, open, openClass, hiddenClass) {
    if (!panel || !panel.classList) return;
    if (openClass) panel.classList.toggle(openClass, open);
    if (hiddenClass) panel.classList.toggle(hiddenClass, !open);
  }

  function bindDisclosure(trigger, opts) {
    if (!trigger || !opts) return null;
    if (trigger.dataset && trigger.dataset.disclosureBound === '1') return null;
    if (typeof global.bindPressable !== 'function') return null;

    const panel = opts.panel || null;
    const openClass = Object.prototype.hasOwnProperty.call(opts, 'openClass')
      ? opts.openClass
      : 'open';
    const hiddenClass = opts.hiddenClass || null;
    const onToggle = typeof opts.onToggle === 'function' ? opts.onToggle : null;

    let isOpen = !!opts.initialOpen;

    function sync(emit) {
      if (typeof trigger.setAttribute === 'function') {
        trigger.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
      }
      _applyPanelState(panel, isOpen, openClass, hiddenClass);
      if (emit && onToggle) onToggle(isOpen, { trigger, panel });
    }

    sync(false);

    global.bindPressable(trigger, {
      refocusComposer: opts.refocusComposer === true,
      clearPressStyle: !!opts.clearPressStyle,
      preventFocusTheft: !!opts.preventFocusTheft,
      preventScroll: opts.preventScroll,
      defer: opts.defer,
      onActivate: (e) => {
        if (opts.stopPropagation && e && typeof e.stopPropagation === 'function') {
          e.stopPropagation();
        }
        isOpen = !isOpen;
        sync(true);
      },
    });

    if (trigger.dataset) trigger.dataset.disclosureBound = '1';

    return {
      isOpen: () => isOpen,
      open: () => { if (!isOpen) { isOpen = true; sync(true); } },
      close: () => { if (isOpen) { isOpen = false; sync(true); } },
      toggle: () => { isOpen = !isOpen; sync(true); },
    };
  }

  global.bindDisclosure = bindDisclosure;
})(typeof window !== 'undefined' ? window : globalThis);
