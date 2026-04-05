// ── Autocomplete ──
let acSuggestions = [];
let acFiltered = [];
let acIndex = -1;
let acSuppressInputOnce = false;

function _positionAutocomplete(itemsCount) {
  if (!acDropdown) return false;
  const wrap = (typeof shellPromptWrap !== 'undefined' && shellPromptWrap) || acDropdown.parentElement;
  const prefix = wrap && wrap.querySelector ? wrap.querySelector('.prompt-prefix') : null;
  const prefixOffset = prefix ? Math.max(0, Math.ceil(prefix.getBoundingClientRect().width) + 8) : 0;
  const wrapRect = wrap && typeof wrap.getBoundingClientRect === 'function' ? wrap.getBoundingClientRect() : null;
  acDropdown.style.position = 'fixed';
  acDropdown.style.left = `${Math.max(0, Math.round((wrapRect ? wrapRect.left : 0) + prefixOffset))}px`;
  acDropdown.style.right = 'auto';
  acDropdown.style.minWidth = '24ch';

  if (!wrap || typeof wrap.getBoundingClientRect !== 'function') {
    acDropdown.classList.remove('ac-up');
    return false;
  }
  const rect = wrap.getBoundingClientRect();
  const rowH = 22;
  const desired = Math.min(10, Math.max(1, itemsCount)) * rowH + 10;
  const targetHeight = Math.max(88, Math.min(260, desired));
  const spaceBelow = Math.max(0, window.innerHeight - rect.bottom - 8);
  const spaceAbove = Math.max(0, rect.top - 8);
  const safetyPad = 20;
  const canFitBelow = spaceBelow >= (targetHeight + safetyPad);
  const canFitAbove = spaceAbove >= (targetHeight + safetyPad);
  const showAbove = !canFitBelow && (canFitAbove || spaceAbove > spaceBelow);
  acDropdown.classList.toggle('ac-up', showAbove);
  const available = showAbove ? spaceAbove : spaceBelow;
  const edgeBuffer = showAbove ? 20 : 30;
  const maxHeight = Math.max(0, Math.min(260, available > edgeBuffer ? available - edgeBuffer : available));
  acDropdown.style.maxHeight = `${Math.round(maxHeight)}px`;
  acDropdown.style.top = showAbove
    ? `${Math.max(8, Math.round(rect.top - maxHeight - 2))}px`
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
  if (!items.length) { acDropdown.style.display = 'none'; return; }
  const previousIndex = acIndex;
  const showAbove = _positionAutocomplete(items.length);
  const pinToBottom = showAbove && previousIndex < 0;
  if (showAbove && acIndex < 0) acIndex = 0;
  if (acIndex >= items.length) acIndex = items.length - 1;
  const renderItems = showAbove ? [...items].reverse() : items;
  renderItems.forEach((s, i) => {
    const originalIndex = showAbove ? (items.length - 1 - i) : i;
    const div = document.createElement('div');
    div.className = 'ac-item' + (originalIndex === acIndex ? ' ac-active' : '');
    const val = cmdInput.value;
    const idx = s.toLowerCase().indexOf(val.toLowerCase());
    if (idx >= 0 && val) {
      div.innerHTML = escapeHtml(s.slice(0, idx))
        + '<span class="ac-match">' + escapeHtml(s.slice(idx, idx + val.length)) + '</span>'
        + escapeHtml(s.slice(idx + val.length));
    } else {
      div.textContent = s;
    }
    div.addEventListener('mousedown', e => { e.preventDefault(); acAccept(s); });
    acDropdown.appendChild(div);
  });
  acDropdown.style.display = 'block';
  _scrollAutocompleteActiveItem(pinToBottom);
}

function acHide() {
  acDropdown.style.display = 'none';
  acIndex = -1;
}

function acAccept(s) {
  cmdInput.value = s;
  acHide();
  cmdInput.focus();
  acSuppressInputOnce = true;
  cmdInput.dispatchEvent(new Event('input'));
}
