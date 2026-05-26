// Single source of truth for dismissible overlay/modal/sheet surfaces.
//
// Before this helper, every surface that dims or obscures the shell
// (FAQ, Workflows, Theme, Options, Shortcuts, history panel, kill
// confirmation, history-delete confirmation, share-redaction modal,
// mobile menu-sheet, mobile recents-sheet) hand-rolled three things:
//   - backdrop click to dismiss
//   - explicit close-button click to dismiss
//   - an entry in the global Escape cascade in controller.js
//
// The Escape cascade had to be hand-maintained so modals always beat
// panels and panels always beat nothing, and the order was enforced by
// a long if-chain that was easy to break when a new surface landed.
//
// bindDismissible(el, opts) owns all three concerns for one surface,
// and closeTopmostDismissible() is the shared dispatcher invoked by the
// global Escape listener so the level ordering is declarative rather
// than re-implemented per call site.
//
// Level priority (highest first): 'modal' > 'sheet' > 'panel'. When
// multiple dismissibles are open, closeTopmostDismissible() closes the
// topmost one at the highest populated level only. Within a level, the
// most recently registered (topmost) one wins — stacks the same way a
// z-indexed overlay pile does today.
//
// Composes bindPressable for close buttons so "dismiss me" controls go
// through the same activation path (click + Enter/Space + blur) as every
// other pressable in the shell.
(function (global) {
  'use strict';

  const LEVEL_PRIORITY = { modal: 3, sheet: 2, panel: 1 };
  const _registry = [];

  function _normalizeCloseButtons(input) {
    if (!input) return [];
    if (Array.isArray(input)) return input.filter(Boolean);
    return [input];
  }

  function bindDismissible(el, opts) {
    if (!el || !opts) return null;
    if (el.dataset && el.dataset.dismissibleBound === '1') return null;
    if (!(opts.level in LEVEL_PRIORITY)) return null;
    if (typeof opts.onClose !== 'function') return null;

    const level = opts.level;
    const isOpenFn = typeof opts.isOpen === 'function' ? opts.isOpen : () => false;
    const onCloseFn = opts.onClose;
    const backdropEl = opts.backdropEl === undefined ? el : opts.backdropEl;
    const closeOnBackdrop = opts.closeOnBackdrop !== false && backdropEl !== null;
    const closeButtons = _normalizeCloseButtons(opts.closeButtons);

    if (el.dataset) el.dataset.dismissibleBound = '1';

    const teardowns = [];

    if (closeOnBackdrop && backdropEl && typeof backdropEl.addEventListener === 'function') {
      const backdropHandler = (e) => {
        if (e.target !== backdropEl) return;
        if (!isOpenFn()) return;
        onCloseFn();
      };
      backdropEl.addEventListener('click', backdropHandler);
      teardowns.push(() => backdropEl.removeEventListener('click', backdropHandler));
    }

    closeButtons.forEach((btn) => {
      if (!btn || typeof btn.addEventListener !== 'function') return;
      const alreadyPressable = btn.dataset && btn.dataset.pressableBound === '1';
      if (!alreadyPressable && typeof global.bindPressable === 'function') {
        const handle = global.bindPressable(btn, {
          refocusComposer: false,
          onActivate: () => { if (isOpenFn()) onCloseFn(); },
        });
        if (handle && typeof handle.dispose === 'function') {
          teardowns.push(() => handle.dispose());
        }
      } else {
        const clickHandler = () => { if (isOpenFn()) onCloseFn(); };
        btn.addEventListener('click', clickHandler);
        teardowns.push(() => btn.removeEventListener('click', clickHandler));
      }
    });

    const entry = { el, level, isOpen: isOpenFn, close: onCloseFn };
    _registry.push(entry);

    return {
      isOpen: () => isOpenFn(),
      close: () => { if (isOpenFn()) onCloseFn(); },
      dispose: () => {
        const idx = _registry.indexOf(entry);
        if (idx >= 0) _registry.splice(idx, 1);
        if (el.dataset) delete el.dataset.dismissibleBound;
        teardowns.forEach((fn) => { try { fn(); } catch (_) { /* swallow */ } });
        teardowns.length = 0;
      },
    };
  }

  // Close the topmost open dismissible by level priority
  // (modal > sheet > panel), and within a level the most recently
  // registered one wins. Returns true if something was closed, false
  // if nothing was open.
  function closeTopmostDismissible() {
    let best = null;
    let bestPriority = -1;
    let bestIdx = -1;
    for (let i = 0; i < _registry.length; i += 1) {
      const entry = _registry[i];
      if (!entry.isOpen()) continue;
      const pri = LEVEL_PRIORITY[entry.level] || 0;
      if (pri > bestPriority || (pri === bestPriority && i > bestIdx)) {
        best = entry;
        bestPriority = pri;
        bestIdx = i;
      }
    }
    if (!best) return false;
    best.close();
    return true;
  }

  global.bindDismissible = bindDismissible;
  global.closeTopmostDismissible = closeTopmostDismissible;
})(typeof window !== 'undefined' ? window : globalThis);
