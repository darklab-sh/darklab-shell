// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Keep the Options sheet and its focused field above the software keyboard.
// The shell's viewport height tracks composer focus, not fields in overlays.
let stopTracking = null;

function stopOptionsKeyboardTracking() {
  stopTracking?.();
  stopTracking = null;
}

function startOptionsKeyboardTracking(overlay) {
  stopOptionsKeyboardTracking();
  if (!overlay) return;
  const body = overlay.querySelector('.options-body');
  const viewport = window.visualViewport;
  let frame = null;

  function sync() {
    frame = null;
    if (!overlay.classList.contains('open')) return;
    const mobile = document.body.classList.contains('mobile-terminal-mode');
    overlay.classList.toggle('options-viewport-tracked', mobile);
    if (!mobile) return;
    const height = viewport?.height || window.innerHeight;
    const keyboardInset = Math.max(0, window.innerHeight - height - (viewport?.offsetTop || 0));
    overlay.style.setProperty('--options-viewport-height', `${height}px`);
    overlay.style.setProperty('--options-viewport-bottom', `${keyboardInset}px`);

    const active = document.activeElement;
    if (!body?.contains(active) || !active.matches('input, textarea, select, [contenteditable="true"]')) return;
    const field = active.getBoundingClientRect();
    if (!field.height) return;
    const bounds = body.getBoundingClientRect();
    // Scroll only the Options body; scrolling ancestors can pan the whole app.
    const top = bounds.top + 12;
    const bottom = bounds.bottom - 12;
    if (field.bottom > bottom) body.scrollTop += field.bottom - bottom;
    else if (field.top < top) body.scrollTop -= top - field.top;
  }

  function schedule() {
    if (frame === null) frame = window.requestAnimationFrame(sync);
  }

  overlay.addEventListener('focusin', schedule);
  viewport?.addEventListener('resize', schedule);
  viewport?.addEventListener('scroll', schedule);
  window.addEventListener('resize', schedule);
  sync();
  stopTracking = () => {
    if (frame !== null) window.cancelAnimationFrame(frame);
    overlay.removeEventListener('focusin', schedule);
    viewport?.removeEventListener('resize', schedule);
    viewport?.removeEventListener('scroll', schedule);
    window.removeEventListener('resize', schedule);
    overlay.classList.remove('options-viewport-tracked');
    overlay.style.removeProperty('--options-viewport-height');
    overlay.style.removeProperty('--options-viewport-bottom');
  };
}

export { startOptionsKeyboardTracking, stopOptionsKeyboardTracking };
