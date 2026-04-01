// ── Autocomplete ──
let acSuggestions = [];
let acFiltered = [];
let acIndex = -1;

function acShow(items) {
  acDropdown.innerHTML = '';
  if (!items.length) { acDropdown.style.display = 'none'; return; }
  items.forEach((s, i) => {
    const div = document.createElement('div');
    div.className = 'ac-item' + (i === acIndex ? ' ac-active' : '');
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
}
