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
  acDropdown.style.left = `${prefixOffset}px`;
  acDropdown.style.right = 'auto';
  acDropdown.style.minWidth = '24ch';

  if (!wrap || typeof wrap.getBoundingClientRect !== 'function') {
    acDropdown.classList.remove('ac-up');
    return false;
  }
  const rect = wrap.getBoundingClientRect();
  const rowH = 22;
  const desired = Math.min(10, Math.max(1, itemsCount)) * rowH + 10;
  const spaceBelow = Math.max(0, window.innerHeight - rect.bottom - 8);
  const spaceAbove = Math.max(0, rect.top - 8);
  const showAbove = spaceBelow < Math.min(desired, 140) && spaceAbove > spaceBelow;
  acDropdown.classList.toggle('ac-up', showAbove);
  const available = showAbove ? spaceAbove : spaceBelow;
  const maxHeight = Math.max(88, Math.min(260, available > 0 ? available : desired));
  acDropdown.style.maxHeight = `${Math.round(maxHeight)}px`;
  return showAbove;
}

function acShow(items) {
  acDropdown.innerHTML = '';
  if (!items.length) { acDropdown.style.display = 'none'; return; }
  const showAbove = _positionAutocomplete(items.length);
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
