// ── Run comparison overlay shell ─────────────────────────────────────────
// Loaded before history.js. The History drawer still owns launcher/result rendering,
// while this module owns the compare modal's open/close/focus lifecycle.
import {
  closeAppSelects as importedCloseAppSelects,
  refocusComposerAfterAction as importedRefocusComposerAfterAction,
  syncModalOverlayState as importedSyncModalOverlayState,
} from '../../ui/ui_helpers.js';
import { bindDismissible as importedBindDismissible } from '../../ui/ui_dismissible.js';

const HISTORY_COMPARE_OVERLAY_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

function _historyCompareOverlayBindDismissible(overlay) {
  const bind = (typeof importedBindDismissible !== 'undefined' && importedBindDismissible)
    || (typeof HISTORY_COMPARE_OVERLAY_GLOBAL.bindDismissible === 'function'
      ? HISTORY_COMPARE_OVERLAY_GLOBAL.bindDismissible
      : null);
  if (typeof bind !== 'function') return;
  bind(overlay, {
    level: 'modal',
    isOpen: () => overlay.classList.contains('open'),
    onClose: closeHistoryCompareOverlay,
    closeButtons: overlay.querySelectorAll('.history-compare-close, .sheet-grab'),
  });
}

function _historyCompareOverlayCloseAppSelects() {
  const close = (typeof importedCloseAppSelects !== 'undefined' && importedCloseAppSelects)
    || (typeof HISTORY_COMPARE_OVERLAY_GLOBAL.closeAppSelects === 'function'
      ? HISTORY_COMPARE_OVERLAY_GLOBAL.closeAppSelects
      : null);
  if (typeof close === 'function') close();
}

function _historyCompareOverlaySyncModalState() {
  const sync = (typeof importedSyncModalOverlayState !== 'undefined' && importedSyncModalOverlayState)
    || HISTORY_COMPARE_OVERLAY_GLOBAL.syncModalOverlayState
    || null;
  if (typeof sync === 'function') sync();
}

function _historyCompareOverlayRefocusComposer() {
  const refocus = (
    typeof importedRefocusComposerAfterAction !== 'undefined'
    && importedRefocusComposerAfterAction
  )
    || (typeof HISTORY_COMPARE_OVERLAY_GLOBAL.refocusComposerAfterAction === 'function'
      ? HISTORY_COMPARE_OVERLAY_GLOBAL.refocusComposerAfterAction
      : null);
  if (typeof refocus === 'function') refocus({ preventScroll: true });
}

function _ensureHistoryCompareOverlay() {
  let overlay = document.getElementById('history-compare-overlay');
  if (overlay) return overlay;

  overlay = document.createElement('div');
  overlay.id = 'history-compare-overlay';
  overlay.className = 'modal-overlay mobile-sheet-overlay u-hidden history-compare-overlay';
  overlay.innerHTML = `
    <section id="history-compare-modal" class="history-compare-modal mobile-sheet-surface" role="dialog" aria-modal="true" aria-labelledby="history-compare-title" tabindex="-1">
      <div class="sheet-grab gesture-handle" role="button" tabindex="0" aria-label="Close run comparison"></div>
      <div class="history-compare-header surface-header">
        <div class="history-compare-heading">
          <div id="history-compare-title" class="history-compare-title">COMPARE RUNS</div>
          <div id="history-compare-subtitle" class="history-compare-subtitle"></div>
        </div>
        <button type="button" class="close-btn history-compare-close" aria-label="Close run comparison">✕</button>
      </div>
      <div id="history-compare-body" class="history-compare-body surface-body nice-scroll"></div>
    </section>
  `;
  document.body.appendChild(overlay);
  overlay.addEventListener('click', e => {
    if (e.target === overlay) closeHistoryCompareOverlay();
  });
  overlay.querySelectorAll('.history-compare-close, .sheet-grab').forEach(el => {
    el.addEventListener('click', () => closeHistoryCompareOverlay());
    el.addEventListener('keydown', e => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        closeHistoryCompareOverlay();
      }
    });
  });
  _historyCompareOverlayBindDismissible(overlay);
  return overlay;
}

function closeHistoryCompareOverlay() {
  const overlay = document.getElementById('history-compare-overlay');
  if (!overlay) return;
  // Close (and unportal) any open dropdowns before hiding the overlay,
  // otherwise a portaled menu would remain visible in document.body.
  HISTORY_COMPARE_OVERLAY_GLOBAL._closeHistoryCompareActionMenus?.();
  _historyCompareOverlayCloseAppSelects();
  overlay.classList.remove('open');
  overlay.classList.add('u-hidden');
  overlay.setAttribute('aria-hidden', 'true');
  _historyCompareOverlaySyncModalState();
  _historyCompareOverlayRefocusComposer();
}

function _focusHistoryCompareOverlay() {
  const overlay = document.getElementById('history-compare-overlay');
  if (!overlay || !overlay.classList.contains('open')) return;
  const modal = overlay.querySelector('#history-compare-modal');
  if (!modal || typeof modal.focus !== 'function') return;
  if (modal.contains(document.activeElement)) return;
  try {
    modal.focus({ preventScroll: true });
  } catch (_) {
    modal.focus();
  }
}

function _queueHistoryCompareInitialFocus() {
  const schedule = typeof requestAnimationFrame === 'function'
    ? requestAnimationFrame
    : (callback) => setTimeout(callback, 0);
  schedule(_focusHistoryCompareOverlay);
}

function _openHistoryCompareOverlay() {
  const overlay = _ensureHistoryCompareOverlay();
  overlay.classList.remove('u-hidden');
  overlay.classList.add('open');
  overlay.setAttribute('aria-hidden', 'false');
  _historyCompareOverlaySyncModalState();
  _queueHistoryCompareInitialFocus();
}

function isHistoryCompareOverlayOpen() {
  const overlay = document.getElementById('history-compare-overlay');
  return !!(overlay && overlay.classList.contains('open'));
}


export {
  _ensureHistoryCompareOverlay,
  _focusHistoryCompareOverlay,
  _openHistoryCompareOverlay,
  _queueHistoryCompareInitialFocus,
  closeHistoryCompareOverlay,
  isHistoryCompareOverlayOpen,
};
