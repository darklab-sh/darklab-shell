// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Shared mobile action-sheet primitive.
//
// One singleton sheet is reused for every caller. It composes the app's
// bottom-sheet, dismissible, mobile-sheet, and pressable primitives while
// keeping caller-specific action logic in the caller.
import { bindDismissible as importedBindDismissible } from './ui_dismissible.js';
import { bindMobileSheet as importedBindMobileSheet } from './mobile_sheet.js';
import { bindPressable as importedBindPressable } from './ui_pressable.js';
import { enhanceAppSelects as importedEnhanceAppSelects } from './ui_helpers.js';

const {
  closeActionSheet,
  openActionSheet,
} = (function initActionSheet() {
  let overlay = null;
  let sheet = null;
  let titleEl = null;
  let itemsEl = null;
  let returnFocusEl = null;
  let onCloseFn = null;

  function _ensure() {
    if (overlay && sheet && titleEl && itemsEl) return overlay;
    overlay = document.createElement('div');
    overlay.id = 'action-sheet-overlay';
    overlay.className = 'modal-overlay mobile-sheet-overlay action-sheet-overlay u-hidden';
    overlay.setAttribute('aria-hidden', 'true');

    sheet = document.createElement('section');
    sheet.id = 'action-sheet';
    sheet.className = 'modal-card mobile-sheet-surface bottom-sheet action-sheet';
    sheet.setAttribute('role', 'dialog');
    sheet.setAttribute('aria-modal', 'true');
    sheet.setAttribute('aria-labelledby', 'action-sheet-title');

    const grab = document.createElement('div');
    grab.className = 'sheet-grab gesture-handle';
    grab.setAttribute('role', 'button');
    grab.tabIndex = 0;
    grab.setAttribute('aria-label', 'Close action sheet');

    const header = document.createElement('div');
    header.className = 'bottom-sheet-header action-sheet-header';
    titleEl = document.createElement('h2');
    titleEl.id = 'action-sheet-title';
    titleEl.className = 'action-sheet-title';
    titleEl.textContent = 'Actions';
    header.appendChild(titleEl);

    itemsEl = document.createElement('div');
    itemsEl.className = 'bottom-sheet-body nice-scroll action-sheet-items';

    sheet.append(grab, header, itemsEl);
    overlay.appendChild(sheet);

    overlay.addEventListener('click', (event) => {
      if (event.target === overlay) closeActionSheet();
    });

    const dismissible = typeof importedBindDismissible === 'function'
      ? importedBindDismissible
      : null;
    if (dismissible) {
      dismissible(overlay, {
        level: 'sheet',
        isOpen: () => !!(overlay && overlay.classList.contains('open')),
        onClose: () => closeActionSheet(),
        backdropEl: overlay,
      });
    }
    const mobileSheet = typeof importedBindMobileSheet === 'function'
      ? importedBindMobileSheet
      : null;
    if (mobileSheet) {
      mobileSheet(sheet, { onClose: () => closeActionSheet() });
    }
    return overlay;
  }

  function _mount(container) {
    const host = container && typeof container.appendChild === 'function' ? container : document.body;
    if (overlay && overlay.parentElement !== host) host.appendChild(overlay);
  }

  function _actionButton(item) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn btn-ghost action-sheet-item';
    if (item.tone === 'danger') btn.classList.add('is-danger', 'btn-danger');
    if (item.disabled) btn.disabled = true;
    if (item.action) btn.dataset.actionSheetAction = String(item.action);
    if (item.title || item.hint) btn.title = item.title || item.hint;
    if (item.icon) {
      const icon = document.createElement('span');
      icon.className = 'action-sheet-item-icon';
      icon.setAttribute('aria-hidden', 'true');
      icon.textContent = String(item.icon);
      btn.appendChild(icon);
    }
    const label = document.createElement('span');
    label.textContent = String(item.label || '');
    btn.appendChild(label);
    btn.addEventListener('click', async () => {
      if (btn.disabled) return;
      btn.disabled = true;
      closeActionSheet({ restoreFocus: false });
      if (typeof item.action === 'function') {
        await item.action(item);
      }
    });
    const pressable = typeof importedBindPressable === 'function'
      ? importedBindPressable
      : null;
    if (pressable) {
      pressable(btn, { refocusComposer: false });
    }
    return btn;
  }

  function _renderItem(item) {
    if (!item) return null;
    if (item.divider) {
      const divider = document.createElement('div');
      divider.className = 'action-sheet-divider';
      divider.setAttribute('role', 'separator');
      return divider;
    }
    if (item.node) {
      const wrap = document.createElement('div');
      wrap.className = 'action-sheet-field';
      wrap.appendChild(item.node);
      return wrap;
    }
    return _actionButton(item);
  }

  function openActionSheet({
    title = 'Actions',
    items = [],
    container = document.body,
    onClose = null,
    returnFocus = null,
  } = {}) {
    const filteredItems = Array.isArray(items) ? items.filter(Boolean) : [];
    if (!filteredItems.length) return null;
    closeActionSheet({ restoreFocus: false });
    _ensure();
    _mount(container);
    onCloseFn = typeof onClose === 'function' ? onClose : null;
    returnFocusEl = returnFocus || document.activeElement || null;
    titleEl.textContent = String(title || 'Actions');
    itemsEl.replaceChildren();
    filteredItems.forEach((item) => {
      const node = _renderItem(item);
      if (node) itemsEl.appendChild(node);
    });
    const enhanceAppSelects = typeof importedEnhanceAppSelects === 'function' ? importedEnhanceAppSelects : null;
    if (typeof enhanceAppSelects === 'function') {
      itemsEl.querySelectorAll('select.form-select').forEach((select) => {
        select.dataset.portalMenu = 'true';
      });
      enhanceAppSelects(itemsEl);
    }
    overlay.classList.remove('u-hidden');
    overlay.classList.add('open');
    overlay.setAttribute('aria-hidden', 'false');
    itemsEl.scrollTop = 0;
    window.setTimeout(() => {
      itemsEl.querySelector('button:not(:disabled), select:not(:disabled), input:not(:disabled), textarea:not(:disabled)')?.focus();
    }, 0);
    return overlay;
  }

  function closeActionSheet({ restoreFocus = true } = {}) {
    if (!overlay) return;
    overlay.classList.add('u-hidden');
    overlay.classList.remove('open');
    overlay.setAttribute('aria-hidden', 'true');
    if (itemsEl) itemsEl.replaceChildren();
    const focusTarget = returnFocusEl;
    const onClose = onCloseFn;
    returnFocusEl = null;
    onCloseFn = null;
    if (typeof onClose === 'function') onClose();
    if (
      restoreFocus
      && focusTarget
      && focusTarget.isConnected
      && typeof focusTarget.focus === 'function'
    ) {
      window.setTimeout(() => focusTarget.focus(), 0);
    }
  }

  return {
    closeActionSheet,
    openActionSheet,
  };
})();

export { openActionSheet, closeActionSheet };
