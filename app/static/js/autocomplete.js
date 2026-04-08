// ── Shared autocomplete logic ──

function _positionAutocomplete(itemsCount) {
  if (!acDropdown) return false;
  const wrap = (typeof shellPromptWrap !== 'undefined' && shellPromptWrap) || acDropdown.parentElement;
  const composerHost = (typeof mobileComposerHost !== 'undefined' && mobileComposerHost) || null;
  const composerRow = (typeof mobileComposerRow !== 'undefined' && mobileComposerRow) || null;
  const prefix = wrap && wrap.querySelector ? wrap.querySelector('.prompt-prefix') : null;
  const mobileTerminalMode = !!(document.body && document.body.classList.contains('mobile-terminal-mode'));
  const mobileComposerMode = mobileTerminalMode;
  const anchor = mobileTerminalMode && composerRow ? composerRow : (mobileTerminalMode && composerHost ? composerHost : wrap);
  acDropdown.classList.toggle('ac-mobile', mobileTerminalMode);
  if (mobileTerminalMode) {
    const rect = anchor && typeof anchor.getBoundingClientRect === 'function'
      ? anchor.getBoundingClientRect()
      : { top: 0 };
    const rowH = 44;
    const desired = Math.min(8, Math.max(1, itemsCount)) * rowH + 10;
    const targetHeight = Math.max(88, Math.min(360, desired));
    const available = Math.max(0, rect.top - 12);
    const maxHeight = Math.max(0, Math.min(targetHeight, available));
    acDropdown.style.position = 'absolute';
    acDropdown.style.left = '0';
    acDropdown.style.right = '0';
    acDropdown.style.width = '100%';
    acDropdown.style.minWidth = '0';
    acDropdown.style.maxHeight = `${Math.round(maxHeight)}px`;
    acDropdown.style.top = 'auto';
    acDropdown.style.bottom = 'calc(100% + 4px)';
    acDropdown.classList.add('ac-up');
    return true;
  }
  acDropdown.classList.remove('ac-mobile');
  const prefixOffset = mobileComposerMode ? 0 : (prefix ? Math.max(0, Math.ceil(prefix.getBoundingClientRect().width) + 8) : 0);
  const wrapRect = anchor && typeof anchor.getBoundingClientRect === 'function' ? anchor.getBoundingClientRect() : null;
  acDropdown.style.position = 'fixed';
  acDropdown.style.left = `${Math.max(0, Math.round((wrapRect ? wrapRect.left : 0) + prefixOffset))}px`;
  acDropdown.style.right = 'auto';
  acDropdown.style.minWidth = mobileComposerMode ? '0' : '24ch';
  acDropdown.style.width = mobileComposerMode && wrapRect ? `${Math.max(220, Math.round(wrapRect.width || 0))}px` : '';

  if (!anchor || typeof anchor.getBoundingClientRect !== 'function') {
    acDropdown.classList.remove('ac-up');
    return false;
  }
  const rect = anchor.getBoundingClientRect();
  const rowH = 22;
  const desired = Math.min(10, Math.max(1, itemsCount)) * rowH + 10;
  const targetHeight = Math.max(88, Math.min(260, desired));
  const spaceBelow = Math.max(0, window.innerHeight - rect.bottom - 8);
  const spaceAbove = Math.max(0, rect.top - 8);
  const safetyPad = 20;
  const canFitBelow = spaceBelow >= (targetHeight + safetyPad);
  const canFitAbove = spaceAbove >= (targetHeight + safetyPad);
  const showAbove = mobileComposerMode || (!canFitBelow && (canFitAbove || spaceAbove > spaceBelow));
  acDropdown.classList.toggle('ac-up', showAbove);
  const available = showAbove ? spaceAbove : spaceBelow;
  const edgeBuffer = mobileComposerMode ? 12 : (showAbove ? 20 : 30);
  const maxHeight = Math.max(0, Math.min(mobileComposerMode ? 200 : 260, available > edgeBuffer ? available - edgeBuffer : available));
  const visibleHeight = Math.max(0, Math.min(targetHeight, maxHeight || targetHeight));
  acDropdown.style.maxHeight = `${Math.round(maxHeight)}px`;
  acDropdown.style.top = showAbove
    ? `${Math.max(8, Math.round(rect.top - visibleHeight - 2))}px`
    : `${Math.max(8, Math.round(rect.bottom + 2))}px`;
  acDropdown.style.bottom = 'auto';
  return showAbove;
}

function _scrollAutocompleteActiveItem(forceBottom = false) {
  if (!acDropdown) return;
  const activeItem = acDropdown.querySelector('.ac-item.ac-active');
  if (!activeItem) return;

  if (forceBottom) {
    acDropdown.scrollTop = Math.max(0, acDropdown.scrollHeight - acDropdown.clientHeight);
    return;
  }

  const viewHeight = acDropdown.clientHeight || 0;
  const itemTop = typeof activeItem.offsetTop === 'number' ? activeItem.offsetTop : null;
  const itemHeight = typeof activeItem.offsetHeight === 'number' ? activeItem.offsetHeight : null;
  if (viewHeight > 0 && itemTop !== null && itemHeight !== null) {
    const itemBottom = itemTop + itemHeight;
    const viewTop = acDropdown.scrollTop || 0;
    const viewBottom = viewTop + viewHeight;
    const padding = 4;
    if (itemTop < viewTop + padding) {
      acDropdown.scrollTop = Math.max(0, itemTop - padding);
    } else if (itemBottom > viewBottom - padding) {
      acDropdown.scrollTop = Math.max(0, itemBottom - viewHeight + padding);
    }
    return;
  }

  if (typeof activeItem.scrollIntoView === 'function') {
    activeItem.scrollIntoView({ block: 'nearest' });
  }
}

function acShow(items) {
  acDropdown.innerHTML = '';
  if (!items.length) { hideAcDropdown(); return; }
  const previousIndex = acIndex;
  const showAbove = _positionAutocomplete(items.length);
  const pinToBottom = showAbove && previousIndex < 0;
  if (showAbove && acIndex < 0) acIndex = 0;
  if (acIndex >= items.length) acIndex = items.length - 1;
  const renderItems = showAbove ? [...items].reverse() : items;
  const currentValue = (typeof getComposerValue === 'function')
    ? getComposerValue()
    : cmdInput.value;
  renderItems.forEach((s, i) => {
    const originalIndex = showAbove ? (items.length - 1 - i) : i;
    const div = document.createElement('div');
    div.className = 'ac-item' + (originalIndex === acIndex ? ' ac-active' : '');
    const val = currentValue;
    const idx = s.toLowerCase().indexOf(val.toLowerCase());
    if (idx >= 0 && val) {
      div.innerHTML = escapeHtml(s.slice(0, idx))
        + '<span class="ac-match">' + escapeHtml(s.slice(idx, idx + val.length)) + '</span>'
        + escapeHtml(s.slice(idx + val.length));
    } else {
      div.textContent = s;
    }
    div.addEventListener('mousedown', e => { e.preventDefault(); acAccept(s); });
    div.addEventListener('touchstart', e => { e.preventDefault(); acAccept(s); }, { passive: false });
    acDropdown.appendChild(div);
  });
  showAcDropdown();
  _positionAutocomplete(items.length);
  _scrollAutocompleteActiveItem(pinToBottom);
}

function acHide() {
  hideAcDropdown();
  acIndex = -1;
}

function acAccept(s) {
  setComposerValue(s, s.length, s.length);
  acHide();
  if (typeof focusAnyComposerInput === 'function' && focusAnyComposerInput({ preventScroll: true })) return;
  acSuppressInputOnce = true;
}
