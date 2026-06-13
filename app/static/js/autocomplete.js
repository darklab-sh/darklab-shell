// Autocomplete dropdown rendering and keyboard interaction.
const autocompleteDropdownCore = (typeof window !== 'undefined' && window.DarklabAutocompleteCore)
  ? window.DarklabAutocompleteCore
  : (typeof DarklabAutocompleteCore !== 'undefined' ? DarklabAutocompleteCore : null);

function _isAutocompleteBlockedByTerminalConfirm() {
  return typeof hasPendingTerminalConfirm === 'function' && hasPendingTerminalConfirm();
}

function _isAutocompleteBlockedByActiveRun() {
  return typeof isActiveTabRunning === 'function' && isActiveTabRunning();
}

function _positionAutocomplete(itemsCount) {
  // Desktop anchors the dropdown to the prompt row; mobile anchors it above the
  // simplified composer so suggestions never hide behind the keyboard.
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
    // Cap at 360px max but don't further cap by available space — the dropdown
    // grows upward (bottom: calc(100% + 4px)) and the parent container clips it
    // if it would go off-screen. This ensures all items are visible without
    // requiring the user to scroll, which is unreliable on touch due to item
    // tap handlers competing with the native scroll gesture.
    const maxHeight = Math.max(88, Math.min(360, desired));
    acDropdown.style.position = 'absolute';
    acDropdown.style.left = '0';
    acDropdown.style.right = '0';
    acDropdown.style.width = '100%';
    acDropdown.style.minWidth = '0';
    acDropdown.style.maxHeight = `${Math.round(maxHeight)}px`;
    acDropdown.style.top = 'auto';
    acDropdown.style.bottom = 'calc(100% + 4px)';
    acDropdown.classList.add('ac-up');
    acDropdown.classList.add('dropdown-up');
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
    acDropdown.classList.remove('dropdown-up');
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
  acDropdown.classList.toggle('dropdown-up', showAbove);
  const available = showAbove ? spaceAbove : spaceBelow;
  const edgeBuffer = mobileComposerMode ? 12 : (showAbove ? 20 : 30);
  const maxHeight = Math.max(0, Math.min(mobileComposerMode ? 200 : 260, available > edgeBuffer ? available - edgeBuffer : available));
  acDropdown.style.maxHeight = `${Math.round(maxHeight)}px`;
  if (showAbove) {
    acDropdown.style.top = 'auto';
    acDropdown.style.bottom = `${Math.max(8, Math.round(window.innerHeight - rect.top + 2))}px`;
  } else {
    acDropdown.style.top = `${Math.max(8, Math.round(rect.bottom + 2))}px`;
    acDropdown.style.bottom = 'auto';
  }
  return showAbove;
}

function _scrollAutocompleteActiveItem() {
  if (!acDropdown) return;
  const activeItem = acDropdown.querySelector('.ac-item.ac-active');
  if (!activeItem) return;

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

function acIsHintOnly(item) {
  return !!(item && typeof item === 'object' && item.hintOnly);
}

function acSelectableItems(items) {
  return (Array.isArray(items) ? items : []).filter(item => !acIsHintOnly(item));
}

function acSelectableIndexes(items) {
  return (Array.isArray(items) ? items : [])
    .map((item, index) => (acIsHintOnly(item) ? -1 : index))
    .filter(index => index >= 0);
}

function acFirstSelectableIndex(items) {
  const indexes = acSelectableIndexes(items);
  return indexes.length ? indexes[0] : -1;
}

function acLastSelectableIndex(items) {
  const indexes = acSelectableIndexes(items);
  return indexes.length ? indexes[indexes.length - 1] : -1;
}

function acNextSelectableIndex(items, currentIndex, direction = 1) {
  const indexes = acSelectableIndexes(items);
  if (!indexes.length) return -1;
  const currentPos = indexes.indexOf(currentIndex);
  if (currentPos < 0) return direction < 0 ? indexes[indexes.length - 1] : indexes[0];
  const nextPos = direction < 0
    ? (currentPos <= 0 ? indexes.length - 1 : currentPos - 1)
    : ((currentPos + 1) % indexes.length);
  return indexes[nextPos];
}

function acShow(items) {
  if (_isAutocompleteBlockedByTerminalConfirm() || _isAutocompleteBlockedByActiveRun()) {
    acHide();
    return;
  }
  acDropdown.innerHTML = '';
  if (!items.length) { hideAcDropdown(); return; }
  _positionAutocomplete(items.length);
  if (acIndex >= items.length) acIndex = acLastSelectableIndex(items);
  if (acIndex >= 0 && acIsHintOnly(items[acIndex])) acIndex = acFirstSelectableIndex(items);
  const currentValue = (typeof getComposerValue === 'function')
    ? getComposerValue()
    : cmdInput.value;
  const currentCursor = (typeof getComposerState === 'function')
    ? getComposerState().selectionStart
    : (cmdInput && typeof cmdInput.selectionStart === 'number' ? cmdInput.selectionStart : currentValue.length);
  const tokenCtx = _autocompleteTokenContext(currentValue, currentCursor);
  const matchValue = (items.length && typeof items[0] === 'object') ? tokenCtx.currentToken : currentValue;
  const maxExampleLabelLen = items.reduce((max, s) =>
    (s && s.isExample ? Math.max(max, autocompleteDropdownCore.itemText(s).length) : max), 0);
  let hasRenderedConcrete = false;
  let hasRenderedHint = false;
  items.forEach((s, i) => {
    const hintOnly = acIsHintOnly(s);
    const hintSeparated = hintOnly && hasRenderedConcrete && !hasRenderedHint;
    const div = document.createElement('div');
    div.className = 'ac-item dropdown-item dropdown-item-dense'
      + (!hintOnly && i === acIndex ? ' ac-active dropdown-item-active' : '')
      + (s && s.isExample ? ' ac-example' : '')
      + (hintOnly ? ' ac-hint-only' : '')
      + (hintSeparated ? ' ac-hint-separated' : '');
    if (hintOnly) div.setAttribute('aria-disabled', 'true');
    const label = autocompleteDropdownCore.itemText(s);
    const description = autocompleteDropdownCore.itemDescription(s);
    const val = s && typeof s === 'object' && s.matchQuery != null
      ? String(s.matchQuery || '')
      : String(matchValue || '');
    const main = document.createElement('span');
    main.className = 'ac-item-main';
    if (s && s.isExample && maxExampleLabelLen > 0) main.style.minWidth = maxExampleLabelLen + 'ch';
    main.innerHTML = hintOnly
      ? escapeHtml(label)
      : autocompleteDropdownCore.highlightedLabel(label, val);
    div.appendChild(main);
    if (description) {
      const desc = document.createElement('span');
      desc.className = 'ac-item-desc';
      desc.textContent = description;
      div.appendChild(desc);
    }
    div.addEventListener('mousedown', e => {
      e.preventDefault();
      if (!hintOnly) acAccept(s);
    });
    // touchstart must not call preventDefault so the container can scroll.
    // We detect taps by checking that the finger barely moved; swipes fall
    // through to the browser's native scroll handling.
    let _touchStartX = 0, _touchStartY = 0;
    div.addEventListener('touchstart', e => {
      const t = e.touches[0];
      _touchStartX = t ? t.clientX : 0;
      _touchStartY = t ? t.clientY : 0;
    }, { passive: true });
    div.addEventListener('touchend', e => {
      const t = e.changedTouches[0];
      const dx = t ? Math.abs(t.clientX - _touchStartX) : 99;
      const dy = t ? Math.abs(t.clientY - _touchStartY) : 99;
      if (dx < 10 && dy < 10) {
        e.preventDefault();
        if (!hintOnly) acAccept(s);
      }
    }, { passive: false });
    acDropdown.appendChild(div);
    if (hintOnly) hasRenderedHint = true;
    else hasRenderedConcrete = true;
  });
  showAcDropdown();
  _positionAutocomplete(items.length);
  _scrollAutocompleteActiveItem();
}

function acHide() {
  hideAcDropdown();
  acIndex = -1;
  if (typeof acFiltered !== 'undefined' && Array.isArray(acFiltered)) acFiltered = [];
}

function acExpandSharedPrefix(items) {
  if (!Array.isArray(items) || items.length < 2) return false;
  const currentValue = (typeof getComposerValue === 'function')
    ? getComposerValue()
    : (cmdInput ? cmdInput.value || '' : '');
  const firstItem = items[0];
  const sharedPrefix = autocompleteDropdownCore.sharedPrefix(items);
  if (!sharedPrefix) return false;
  if (firstItem && typeof firstItem === 'object') {
    const replaceStart = Number(firstItem.replaceStart);
    const replaceEnd = Number(firstItem.replaceEnd);
    if (!Number.isFinite(replaceStart) || !Number.isFinite(replaceEnd)) return false;
    const currentToken = currentValue.slice(replaceStart, replaceEnd);
    if (sharedPrefix.length <= currentToken.length) return false;
    if (!sharedPrefix.toLowerCase().startsWith(currentToken.toLowerCase())) return false;
    const next = currentValue.slice(0, replaceStart) + sharedPrefix + currentValue.slice(replaceEnd);
    const caret = replaceStart + sharedPrefix.length;
    setComposerValue(next, caret, caret);
    return true;
  }
  if (sharedPrefix.length <= currentValue.length) return false;
  if (!sharedPrefix.toLowerCase().startsWith(currentValue.toLowerCase())) return false;
  setComposerValue(sharedPrefix, sharedPrefix.length, sharedPrefix.length);
  return true;
}

function _scheduleAutocompleteRefreshAfterAccept(insertValue) {
  if (!String(insertValue || '').endsWith('/')) return;
  setTimeout(() => {
    if (typeof window.openAutocompleteForVisibleComposer === 'function' && window.openAutocompleteForVisibleComposer()) return;
    const input = typeof getVisibleComposerInput === 'function' ? getVisibleComposerInput() : cmdInput;
    if (input && typeof input.dispatchEvent === 'function') {
      input.dispatchEvent(new Event('input'));
    }
  }, 0);
}

function acAccept(s) {
  let acceptedInsertValue = '';
  if (_isAutocompleteBlockedByTerminalConfirm()) {
    acHide();
    refocusComposerAfterAction({ preventScroll: true });
    return;
  }
  if (s && typeof s === 'object') {
    // Placeholder-only hints (e.g. "<token>") are display-only: Tab should hide
    // the dropdown, not insert the literal placeholder text into the prompt.
    if (s.hintOnly) {
      refocusComposerAfterAction({ preventScroll: true });
      return;
    }
    const currentValue = (typeof getComposerValue === 'function')
      ? getComposerValue()
      : (cmdInput ? cmdInput.value || '' : '');
    const insertValue = autocompleteDropdownCore.itemInsertText(s);
    acceptedInsertValue = insertValue;
    const replaceStart = Number(s.replaceStart);
    const replaceEnd = Number(s.replaceEnd);
    if (typeof acSuppressInputOnce !== 'undefined') acSuppressInputOnce = true;
    if (Number.isFinite(replaceStart) && Number.isFinite(replaceEnd)) {
      const next = currentValue.slice(0, replaceStart) + insertValue + currentValue.slice(replaceEnd);
      const caret = replaceStart + insertValue.length;
      acHide();
      setComposerValue(next, caret, caret);
    } else {
      acHide();
      setComposerValue(insertValue, insertValue.length, insertValue.length);
    }
  } else {
    acceptedInsertValue = String(s || '');
    if (typeof acSuppressInputOnce !== 'undefined') acSuppressInputOnce = true;
    acHide();
    setComposerValue(s, s.length, s.length);
  }
  refocusComposerAfterAction({ preventScroll: true });
  _scheduleAutocompleteRefreshAfterAccept(acceptedInsertValue);
}

if (typeof window !== 'undefined') {
  Object.assign(window, {
    _positionAutocomplete,
    _scrollAutocompleteActiveItem,
    acIsHintOnly,
    acSelectableItems,
    acSelectableIndexes,
    acFirstSelectableIndex,
    acLastSelectableIndex,
    acNextSelectableIndex,
    acShow,
    acHide,
    acExpandSharedPrefix,
    acAccept,
  });
}
