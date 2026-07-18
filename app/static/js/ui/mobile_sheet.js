// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Single source of truth for mobile bottom-sheet drag/tap/keyboard close
// behavior. Every mobile sheet (menu, recents, history panel, workflows, FAQ,
// options, kill, hist-del, share-redaction) is wired through bindMobileSheet
// so the handle behavior cannot drift between sheets.
//
// Behavior contract for every bound sheet:
// - Visual handle: a `:scope > .sheet-grab.gesture-handle` element. If the
//   sheet template doesn't ship one, an aria-hidden one is injected at the top.
// - Tap: a finger-down + finger-up under `tapMaxMovement` pixels closes.
// - Drag: pulling the sheet down translates it with the finger; releasing
//   past `threshold` pixels animates it out and closes; releasing before the
//   threshold snaps it back to the resting position.
// - Keyboard: Enter or Space on a focused handle closes (matches the
//   role="button" semantics on the recents-sheet handle).
// - Mobile-only: pointer handlers no-op when useMobileTerminalViewportMode()
//   reports the shell is in desktop mode, so the same modals can stay drag-
//   immune on desktop.
import { useMobileTerminalViewportMode as importedUseMobileTerminalViewportMode } from '../features/mobile/mobile_shell_layout.js';

const bindMobileSheet = (function (global) {
  'use strict';

  function _isMobileMode() {
    const readMobileMode = (typeof importedUseMobileTerminalViewportMode !== 'undefined' && importedUseMobileTerminalViewportMode)
      || null;
    if (typeof readMobileMode === 'function' && readMobileMode()) return true;
    return !!(typeof document !== 'undefined'
      && document.body
      && document.body.classList
      && document.body.classList.contains('mobile-terminal-mode'));
  }

  function _ensureGrab(sheet) {
    if (!sheet) return null;
    let grab = sheet.querySelector(':scope > .sheet-grab');
    if (grab) return grab;
    grab = document.createElement('div');
    grab.className = 'sheet-grab gesture-handle';
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

    function fallbackCloseOpenOverlay() {
      const overlay = sheet.closest?.('.mobile-sheet-overlay.open');
      if (!overlay) return;
      overlay.classList.remove('open');
      overlay.classList.add('u-hidden');
      overlay.setAttribute('aria-hidden', 'true');
    }

    function settle(close) {
      if (close) {
        sheet.style.transition = 'transform 180ms ease, opacity 180ms ease';
        sheet.style.transform = `translateY(${sheet.getBoundingClientRect().height}px)`;
        sheet.style.opacity = '0.98';
        setTimeout(() => {
          clearStyles();
          try { onClose(); } finally { fallbackCloseOpenOverlay(); }
        }, 180);
      } else {
        sheet.style.transition = 'transform 160ms ease';
        sheet.style.transform = 'translateY(0)';
        setTimeout(clearStyles, 180);
      }
    }

    function _removeWindowFallbacks() {
      window.removeEventListener('pointerup', _windowEnd, true);
      window.removeEventListener('pointercancel', _windowCancel, true);
    }

    function endDrag(pointerId, cancelled) {
      if (!drag || drag.pointerId !== pointerId) return;
      const dy = drag.dy;
      const moved = drag.maxDy;
      drag = null;
      _removeWindowFallbacks();
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

    function applyPointerPosition(e) {
      if (!drag || drag.pointerId !== e.pointerId) return;
      const dy = Math.max(0, e.clientY - drag.startY);
      drag.dy = dy;
      if (dy > drag.maxDy) drag.maxDy = dy;
      if (dy > 0) sheet.style.transform = `translateY(${dy}px)`;
    }

    function _windowEnd(e) {
      applyPointerPosition(e);
      endDrag(e.pointerId, false);
    }
    function _windowCancel(e) { endDrag(e.pointerId, true); }
    function _isGrabEvent(e) {
      return e && (e.target === grab || (typeof e.composedPath === 'function' && e.composedPath().includes(grab)));
    }

    // Safety net: if the sheet is hidden mid-drag (e.g. user taps the X close
    // button or scrim while a finger is still on the grab), the grab's
    // pointerup may never fire and endDrag never cleans up. Left unchecked,
    // `transform: translateY(...)` persists on the sheet and follows it into
    // the next open — pinning the modal low and making the grab/content
    // unreachable. Clearing any leaked inline styles at the start of each
    // fresh drag recovers the sheet; window-level fallbacks ensure endDrag
    // runs even if the grab is no longer receiving events.
    grab.addEventListener('pointerdown', e => {
      if (!_isMobileMode()) return;
      if (typeof e.button === 'number' && e.button !== 0) return;
      clearStyles();
      drag = { pointerId: e.pointerId, startY: e.clientY, dy: 0, maxDy: 0 };
      sheet.style.willChange = 'transform';
      sheet.style.transition = 'none';
      // Capture on the grab so subsequent move/up events still fire here even
      // if the finger drifts outside the small handle target.
      try { grab.setPointerCapture(e.pointerId); } catch (_) { /* non-critical */ }
      window.addEventListener('pointerup', _windowEnd, true);
      window.addEventListener('pointercancel', _windowCancel, true);
    });

    const onPointerMove = e => {
      if (!drag || drag.pointerId !== e.pointerId) return;
      applyPointerPosition(e);
      if (drag.dy <= 0) return;
      e.preventDefault();
    };
    grab.addEventListener('pointermove', onPointerMove);

    grab.addEventListener('pointerup', e => {
      applyPointerPosition(e);
      endDrag(e.pointerId, false);
    });
    grab.addEventListener('pointercancel', e => endDrag(e.pointerId, true));
    sheet.addEventListener('pointermove', e => {
      if (_isGrabEvent(e)) onPointerMove(e);
    }, true);
    sheet.addEventListener('pointerup', e => {
      if (_isGrabEvent(e)) {
        applyPointerPosition(e);
        endDrag(e.pointerId, false);
      }
    }, true);
    sheet.addEventListener('pointercancel', e => {
      if (_isGrabEvent(e)) endDrag(e.pointerId, true);
    }, true);

    grab.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onClose();
      }
    });

    // Final safety net. If some other code path (close button click, scrim
    // tap, _closeMajorOverlays, etc.) hides the sheet while `drag` is still
    // active and the captured pointerup never reaches window — possible on
    // iOS Safari when the captured element loses its compositor layer — the
    // inline `transform: translateY(...)` would follow the sheet into its
    // next open, pinning the modal low with an unresponsive grab. Watching
    // the sheet's computed visibility lets us scrub inline styles at the
    // exact moment the sheet becomes hidden, independent of pointer state.
    let _lastHidden = !_isVisible(sheet);
    const visibilityObserver = new MutationObserver(() => {
      const hidden = !_isVisible(sheet);
      if (hidden && !_lastHidden) {
        drag = null;
        _removeWindowFallbacks();
        clearStyles();
      }
      _lastHidden = hidden;
    });
    visibilityObserver.observe(sheet, { attributes: true, attributeFilter: ['class', 'style'] });
    if (sheet.parentElement) {
      visibilityObserver.observe(sheet.parentElement, { attributes: true, attributeFilter: ['class', 'style'] });
    }
  }

  function _isVisible(el) {
    if (!el || typeof el.getClientRects !== 'function') return false;
    if (el.offsetParent === null && getComputedStyle(el).position !== 'fixed') {
      const rects = el.getClientRects();
      if (!rects.length) return false;
    }
    return getComputedStyle(el).display !== 'none' && getComputedStyle(el).visibility !== 'hidden';
  }

  return bindMobileSheet;
})(typeof window !== 'undefined' ? window : globalThis);

export { bindMobileSheet };
