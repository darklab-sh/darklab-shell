// Shared mobile action-sheet primitive.
//
// One singleton sheet is reused for every caller. It composes the app's
// bottom-sheet, dismissible, mobile-sheet, and pressable primitives while
// keeping caller-specific action logic in the caller.
(function initActionSheet(global) {
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

    if (typeof global.bindDismissible === 'function') {
      global.bindDismissible(overlay, {
        level: 'sheet',
        isOpen: () => !!(overlay && overlay.classList.contains('open')),
        onClose: () => closeActionSheet(),
        backdropEl: overlay,
      });
    }
    if (typeof global.bindMobileSheet === 'function') {
      global.bindMobileSheet(sheet, { onClose: () => closeActionSheet() });
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
    if (item.title) btn.title = item.title;
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
    if (typeof global.bindPressable === 'function') {
      global.bindPressable(btn, { refocusComposer: false });
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
    if (typeof global.enhanceAppSelects === 'function') {
      itemsEl.querySelectorAll('select.form-select').forEach((select) => {
        select.dataset.portalMenu = 'true';
      });
      global.enhanceAppSelects(itemsEl);
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

  global.openActionSheet = openActionSheet;
  global.closeActionSheet = closeActionSheet;
})(typeof window !== 'undefined' ? window : globalThis);
