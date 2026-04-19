// Single source of truth for mobile bottom-sheet drag/tap/keyboard close
// behavior. Every mobile sheet (menu, recents, history panel, workflows, FAQ,
// options, kill, hist-del, share-redaction) is wired through bindMobileSheet
// so the handle behavior cannot drift between sheets.
//
// Behavior contract for every bound sheet:
// - Visual handle: a `:scope > .sheet-grab` element. If the sheet template
//   doesn't ship one, an aria-hidden one is injected at the top.
// - Tap: a finger-down + finger-up under `tapMaxMovement` pixels closes.
// - Drag: pulling the sheet down translates it with the finger; releasing
//   past `threshold` pixels animates it out and closes; releasing before the
//   threshold snaps it back to the resting position.
// - Keyboard: Enter or Space on a focused handle closes (matches the
//   role="button" semantics on the recents-sheet handle).
// - Mobile-only: pointer handlers no-op when useMobileTerminalViewportMode()
//   reports the shell is in desktop mode, so the same modals can stay drag-
//   immune on desktop.
(function (global) {
  'use strict';

  function _isMobileMode() {
    return typeof global.useMobileTerminalViewportMode === 'function'
      && global.useMobileTerminalViewportMode();
  }

  function _ensureGrab(sheet) {
    if (!sheet) return null;
    let grab = sheet.querySelector(':scope > .sheet-grab');
    if (grab) return grab;
    grab = document.createElement('div');
    grab.className = 'sheet-grab';
    grab.setAttribute('aria-hidden', 'true');
    sheet.insertBefore(grab, sheet.firstChild || null);
    return grab;
  }

  function bindMobileSheet(sheet, opts) {
    if (!sheet || !opts || typeof opts.onClose !== 'function') return;
    if (sheet.dataset.mobileSheetBound === '1') return;
    sheet.dataset.mobileSheetBound = '1';

    const onClose = opts.onClose;
    const threshold = typeof opts.threshold === 'number' ? opts.threshold : 60;
    const tapMaxMovement = typeof opts.tapMaxMovement === 'number' ? opts.tapMaxMovement : 10;

    const grab = _ensureGrab(sheet);
    if (!grab) return;

    let drag = null;

    function clearStyles() {
      sheet.style.removeProperty('transform');
      sheet.style.removeProperty('transition');
      sheet.style.removeProperty('will-change');
      sheet.style.removeProperty('opacity');
    }

    function settle(close) {
      if (close) {
        sheet.style.transition = 'transform 180ms ease, opacity 180ms ease';
        sheet.style.transform = `translateY(${sheet.getBoundingClientRect().height}px)`;
        sheet.style.opacity = '0.98';
        setTimeout(() => {
          clearStyles();
          onClose();
        }, 180);
      } else {
        sheet.style.transition = 'transform 160ms ease';
        sheet.style.transform = 'translateY(0)';
        setTimeout(clearStyles, 180);
      }
    }

    function endDrag(pointerId, cancelled) {
      if (!drag || drag.pointerId !== pointerId) return;
      const dy = drag.dy;
      const moved = drag.maxDy;
      drag = null;
      try { sheet.releasePointerCapture(pointerId); } catch (_) { /* non-critical */ }
      try { grab.releasePointerCapture(pointerId); } catch (_) { /* non-critical */ }
      if (cancelled) {
        settle(false);
        return;
      }
      // Tap: finger never moved meaningfully. Close without an outbound drag
      // animation since there's no momentum to honor.
      if (moved < tapMaxMovement) {
        clearStyles();
        onClose();
        return;
      }
      settle(dy >= threshold);
    }

    grab.addEventListener('pointerdown', e => {
      if (!_isMobileMode()) return;
      if (typeof e.button === 'number' && e.button !== 0) return;
      drag = { pointerId: e.pointerId, startY: e.clientY, dy: 0, maxDy: 0 };
      sheet.style.willChange = 'transform';
      sheet.style.transition = 'none';
      // Capture on the grab so subsequent move/up events still fire here even
      // if the finger drifts outside the small handle target.
      try { grab.setPointerCapture(e.pointerId); } catch (_) { /* non-critical */ }
    });

    grab.addEventListener('pointermove', e => {
      if (!drag || drag.pointerId !== e.pointerId) return;
      const dy = Math.max(0, e.clientY - drag.startY);
      drag.dy = dy;
      if (dy > drag.maxDy) drag.maxDy = dy;
      if (dy <= 0) return;
      e.preventDefault();
      sheet.style.transform = `translateY(${dy}px)`;
    });

    grab.addEventListener('pointerup', e => endDrag(e.pointerId, false));
    grab.addEventListener('pointercancel', e => endDrag(e.pointerId, true));

    grab.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onClose();
      }
    });
  }

  global.bindMobileSheet = bindMobileSheet;
})(typeof window !== 'undefined' ? window : globalThis);
