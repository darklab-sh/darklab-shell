// ── app.js — Initialization ──
// This file wires event listeners and bootstraps the app after all modules load.

function syncShellPrompt() {
  if (typeof shellPromptText === 'undefined' || !shellPromptText || !cmdInput) return;
  const value = cmdInput.value || '';
  const len = value.length;
  let start = typeof cmdInput.selectionStart === 'number' ? cmdInput.selectionStart : len;
  let end = typeof cmdInput.selectionEnd === 'number' ? cmdInput.selectionEnd : len;
  start = Math.max(0, Math.min(start, len));
  end = Math.max(0, Math.min(end, len));
  if (start > end) [start, end] = [end, start];

  if (typeof shellPromptWrap !== 'undefined' && shellPromptWrap) {
    shellPromptWrap.classList.toggle('shell-prompt-empty', len === 0);
    shellPromptWrap.classList.toggle('shell-prompt-has-value', len > 0);
  }

  shellPromptText.replaceChildren();
  if (!len) return;

  if (start > 0) shellPromptText.appendChild(document.createTextNode(value.slice(0, start)));

  if (end > start) {
    const sel = document.createElement('span');
    sel.className = 'shell-prompt-selection';
    sel.textContent = value.slice(start, end);
    shellPromptText.appendChild(sel);
  } else {
    if (start < len) {
      const caretChar = document.createElement('span');
      caretChar.className = 'shell-caret-char';
      caretChar.setAttribute('aria-hidden', 'true');
      caretChar.textContent = value.slice(start, start + 1);
      shellPromptText.appendChild(caretChar);
      if (start + 1 < len) shellPromptText.appendChild(document.createTextNode(value.slice(start + 1)));
      return;
    }
    const caret = document.createElement('span');
    caret.className = 'shell-inline-caret';
    caret.setAttribute('aria-hidden', 'true');
    caret.textContent = '';
    shellPromptText.appendChild(caret);
  }

  if (end < len) shellPromptText.appendChild(document.createTextNode(value.slice(end)));
}

function refocusTerminalInput() {
  if (!cmdInput || typeof cmdInput.focus !== 'function') return;
  setTimeout(() => cmdInput.focus(), 0);
}

function isEditableTarget(target) {
  return !!(target && target.closest && target.closest('input, textarea, [contenteditable="true"]'));
}

function shouldIgnoreGlobalShortcutTarget(target) {
  return isEditableTarget(target) && target !== cmdInput;
}

function createNextTabLabel() {
  return 'tab ' + (tabs.length + 1);
}

function createShortcutTab() {
  if (typeof createTab !== 'function') return;
  createTab(createNextTabLabel());
}

function activateRelativeTab(offset) {
  if (!Array.isArray(tabs) || !tabs.length || typeof activateTab !== 'function') return;
  const currentIndex = tabs.findIndex(tab => tab.id === activeTabId);
  const baseIndex = currentIndex >= 0 ? currentIndex : 0;
  const nextIndex = (baseIndex + offset + tabs.length) % tabs.length;
  activateTab(tabs[nextIndex].id);
}

function closeActiveShortcutTab() {
  if (!activeTabId || typeof closeTab !== 'function') return;
  closeTab(activeTabId);
}

function permalinkActiveShortcutTab() {
  if (!activeTabId || typeof permalinkTab !== 'function') return;
  permalinkTab(activeTabId);
}

function copyActiveShortcutTab() {
  if (!activeTabId || typeof copyTab !== 'function') return;
  copyTab(activeTabId);
}

function clearActiveShortcutTab() {
  if (!activeTabId || typeof clearTab !== 'function') return;
  if (typeof cancelWelcome === 'function') cancelWelcome(activeTabId);
  clearTab(activeTabId);
}

function closeKillOverlay() {
  killOverlay.style.display = 'none';
  pendingKillTabId = null;
  refocusTerminalInput();
}

function confirmPendingKill() {
  killOverlay.style.display = 'none';
  if (pendingKillTabId) {
    doKill(pendingKillTabId);
    pendingKillTabId = null;
  }
  refocusTerminalInput();
}

function eventMatchesCode(e, code) {
  return !!(e && e.code === code);
}

function eventMatchesLetter(e, letter) {
  if (eventMatchesCode(e, `Key${letter.toUpperCase()}`)) return true;
  const key = e && typeof e.key === 'string' ? e.key.toLowerCase() : '';
  return key === letter.toLowerCase();
}

function eventMatchesDigit(e, digit) {
  if (eventMatchesCode(e, `Digit${digit}`)) return true;
  return !!(e && e.key === String(digit));
}

function handleTabShortcut(e) {
  if (!e.altKey || e.ctrlKey || e.metaKey) return false;
  if (shouldIgnoreGlobalShortcutTarget(e.target)) return false;
  if (eventMatchesLetter(e, 't')) {
    createShortcutTab();
    e.preventDefault();
    return true;
  }
  if (eventMatchesLetter(e, 'w')) {
    closeActiveShortcutTab();
    e.preventDefault();
    return true;
  }
  if (e.key === 'ArrowRight') {
    activateRelativeTab(1);
    e.preventDefault();
    return true;
  }
  if (e.key === 'ArrowLeft') {
    activateRelativeTab(-1);
    e.preventDefault();
    return true;
  }
  const matchedDigit = [1, 2, 3, 4, 5, 6, 7, 8, 9].find(digit => eventMatchesDigit(e, digit));
  if (matchedDigit) {
    const tabIndex = matchedDigit - 1;
    if (tabs[tabIndex] && typeof activateTab === 'function') activateTab(tabs[tabIndex].id);
    e.preventDefault();
    return true;
  }
  return false;
}

function handleActionShortcut(e) {
  if (shouldIgnoreGlobalShortcutTarget(e.target)) return false;
  if (e.altKey && !e.ctrlKey && !e.metaKey && eventMatchesLetter(e, 'p')) {
    permalinkActiveShortcutTab();
    e.preventDefault();
    return true;
  }
  if (e.altKey && !e.ctrlKey && !e.metaKey && e.shiftKey && eventMatchesLetter(e, 'c')) {
    copyActiveShortcutTab();
    e.preventDefault();
    return true;
  }
  if (e.ctrlKey && !e.altKey && !e.metaKey && (e.key === 'l' || e.key === 'L')) {
    clearActiveShortcutTab();
    e.preventDefault();
    return true;
  }
  return false;
}

function isKillOverlayOpen() {
  return !!(killOverlay && killOverlay.style && killOverlay.style.display === 'flex');
}

function getCmdSelection(value = cmdInput.value || '') {
  let start = typeof cmdInput.selectionStart === 'number' ? cmdInput.selectionStart : value.length;
  let end = typeof cmdInput.selectionEnd === 'number' ? cmdInput.selectionEnd : value.length;
  if (start > end) [start, end] = [end, start];
  return { start, end };
}

function replaceCmdRange(value, start, end, replacement = '') {
  cmdInput.value = value.slice(0, start) + replacement + value.slice(end);
  const nextPos = start + replacement.length;
  cmdInput.setSelectionRange(nextPos, nextPos);
  cmdInput.dispatchEvent(new Event('input'));
}

function findWordBoundaryLeft(value, index) {
  let next = Math.max(0, index);
  while (next > 0 && /\s/.test(value[next - 1])) next--;
  while (next > 0 && !/\s/.test(value[next - 1])) next--;
  return next;
}

function findWordBoundaryRight(value, index) {
  let next = Math.min(value.length, index);
  while (next < value.length && /\s/.test(value[next])) next++;
  while (next < value.length && !/\s/.test(value[next])) next++;
  return next;
}

// ── Theme ──
const savedTheme = localStorage.getItem('theme');
if (savedTheme === 'light') document.body.classList.add('light');

// ── Timestamps ──
const _tsModes  = ['off', 'elapsed', 'clock'];
const _tsLabels = { off: 'timestamps: off', elapsed: 'timestamps: elapsed', clock: 'timestamps: clock' };

function _setTsMode(mode) {
  tsMode = mode;
  document.body.classList.remove('ts-elapsed', 'ts-clock');
  if (mode === 'elapsed') document.body.classList.add('ts-elapsed');
  if (mode === 'clock')   document.body.classList.add('ts-clock');
  const label = _tsLabels[mode];
  const tsBtn = document.getElementById('ts-btn');
  if (tsBtn) { tsBtn.textContent = label; tsBtn.classList.toggle('active', mode !== 'off'); }
  const mobileTs = document.querySelector('#mobile-menu [data-action="ts"]');
  if (mobileTs) mobileTs.textContent = label;
  if (typeof syncOutputPrefixes === 'function') syncOutputPrefixes();
}

document.getElementById('ts-btn').addEventListener('click', () => {
  _setTsMode(_tsModes[(_tsModes.indexOf(tsMode) + 1) % _tsModes.length]);
  refocusTerminalInput();
});

document.getElementById('ln-btn').addEventListener('click', () => {
  _setLnMode(typeof lnMode !== 'undefined' ? (lnMode === 'on' ? 'off' : 'on') : 'on');
  refocusTerminalInput();
});

document.getElementById('theme-btn').addEventListener('click', () => {
  document.body.classList.toggle('light');
  localStorage.setItem('theme', document.body.classList.contains('light') ? 'light' : 'dark');
  refocusTerminalInput();
});

// ── Load config from server ──
apiFetch('/config').then(r => r.json()).then(cfg => {
  APP_CONFIG = cfg;
  document.title = cfg.app_name;
  document.querySelector('header h1').textContent = cfg.app_name;
  const verEl = document.getElementById('version-label');
  if (verEl && cfg.version) verEl.textContent = 'v' + cfg.version + ' · real-time';
  // Only apply server default theme if the user hasn't saved a local preference
  if (!localStorage.getItem('theme') && cfg.default_theme === 'light') {
    document.body.classList.add('light');
  }
  if (cfg.motd) {
    const motd = document.getElementById('motd');
    const wrap = document.getElementById('motd-wrap');
    if (motd && wrap) { motd.innerHTML = renderMotd(cfg.motd); wrap.style.display = 'block'; }
  }
  updateNewTabBtn();

  // ── Populate the retention/limits FAQ entry with live config values ──
  const limitsEl = document.getElementById('faq-limits-text');
  if (limitsEl) {
    function _fmtDuration(s) {
      if (s >= 3600 && s % 3600 === 0) return (s / 3600) + (s / 3600 === 1 ? ' hour' : ' hours');
      if (s >= 60   && s % 60   === 0) return (s / 60)   + (s / 60   === 1 ? ' minute' : ' minutes');
      return s + (s === 1 ? ' second' : ' seconds');
    }
    const timeout   = cfg.command_timeout_seconds  || 0;
    const maxLines  = cfg.max_output_lines         || 0;
    const retention = cfg.permalink_retention_days || 0;

    const rows = [
      {
        label: 'Command timeout',
        value: timeout > 0
          ? `<strong>${_fmtDuration(timeout)}</strong> — commands are automatically killed after this time; a notice appears inline in the output`
          : `<strong>None</strong> — commands run until they finish or you click ■ Kill`,
      },
      {
        label: 'Output line limit',
        value: maxLines > 0
          ? `<strong>${maxLines.toLocaleString()} lines</strong> per tab — older lines are dropped from the top when this is reached`
          : `<strong>Unlimited</strong>`,
      },
      {
        label: 'Permalink &amp; history retention',
        value: retention > 0
          ? `<strong>${retention} day${retention === 1 ? '' : 's'}</strong> — run history and share links are deleted after this period`
          : `<strong>Unlimited</strong> — run history and share links are kept indefinitely`,
      },
    ];

    const tableRows = rows.map(r =>
      `<tr><td style="padding:2px 12px 2px 0;white-space:nowrap;color:var(--muted)">${r.label}</td>` +
      `<td style="padding:2px 0">${r.value}</td></tr>`
    ).join('');

    limitsEl.innerHTML =
      `<table style="border-collapse:collapse;margin-bottom:6px">${tableRows}</table>` +
      `<span style="color:var(--muted);font-size:11px">These limits are configured by the operator of this instance.</span>`;
  }
}).catch(err => {
  if (typeof logClientError === 'function') logClientError('failed to load /config', err);
});

// ── Hamburger menu (mobile) ──
const hamburgerBtn = document.getElementById('hamburger-btn');
const mobileMenu   = document.getElementById('mobile-menu');

hamburgerBtn.addEventListener('click', e => {
  e.stopPropagation();
  mobileMenu.classList.toggle('open');
});

mobileMenu.querySelectorAll('button[data-action]').forEach(btn => {
  btn.addEventListener('click', () => {
    mobileMenu.classList.remove('open');
    const action = btn.dataset.action;
    if (action === 'search') {
      const visible = searchBar.style.display !== 'none';
      searchBar.style.display = visible ? 'none' : 'flex';
      if (!visible) { searchInput.focus(); runSearch(); } else clearSearch();
    }
    if (action === 'history') {
      historyPanel.classList.toggle('open');
      if (historyPanel.classList.contains('open')) refreshHistoryPanel();
    }
    if (action === 'ts') {
      _setTsMode(_tsModes[(_tsModes.indexOf(tsMode) + 1) % _tsModes.length]);
      refocusTerminalInput();
    }
    if (action === 'ln') {
      _setLnMode(typeof lnMode !== 'undefined' ? (lnMode === 'on' ? 'off' : 'on') : 'on');
      refocusTerminalInput();
    }
    if (action === 'theme') {
      document.body.classList.toggle('light');
      localStorage.setItem('theme', document.body.classList.contains('light') ? 'light' : 'dark');
      refocusTerminalInput();
    }
    if (action === 'faq') openFaq();
  });
});

// ── FAQ ──
function openFaq() { document.getElementById('faq-overlay').classList.add('open'); }
function closeFaq() {
  document.getElementById('faq-overlay').classList.remove('open');
  refocusTerminalInput();
}

document.getElementById('faq-btn').addEventListener('click', openFaq);
document.getElementById('faq-overlay').addEventListener('click', e => {
  if (e.target === document.getElementById('faq-overlay')) closeFaq();
});
document.querySelector('.faq-close').addEventListener('click', closeFaq);

apiFetch('/allowed-commands').then(r => r.json()).then(data => {
  const el = document.getElementById('faq-allowed-text');
  if (!data.restricted) {
    el.textContent = 'No restrictions are configured — all commands are permitted.';
    return;
  }

  function makeChip(cmd) {
    const chip = document.createElement('span');
    chip.className = 'allowed-chip';
    chip.textContent = cmd;
    chip.title = 'Click to load into prompt';
    chip.addEventListener('click', () => {
      cmdInput.value = cmd + ' ';
      closeFaq();
      cmdInput.focus();
      // Defer the input event so it fires after the click finishes bubbling
      // to document (which calls acHide). Without this, autocomplete opens
      // then immediately closes.
      setTimeout(() => cmdInput.dispatchEvent(new Event('input')), 0);
    });
    return chip;
  }

  if (data.groups && data.groups.length > 0) {
    el.innerHTML = 'Click any command to load it into the prompt:';
    data.groups.forEach(group => {
      const groupEl = document.createElement('div');
      groupEl.className = 'allowed-group';
      if (group.name) {
        const header = document.createElement('div');
        header.className = 'allowed-group-header';
        header.textContent = group.name;
        groupEl.appendChild(header);
      }
      const list = document.createElement('div');
      list.className = 'allowed-list';
      group.commands.forEach(cmd => list.appendChild(makeChip(cmd)));
      groupEl.appendChild(list);
      el.appendChild(groupEl);
    });
  } else {
    el.innerHTML = 'Click any command to load it into the prompt:';
    const list = document.createElement('div');
    list.className = 'allowed-list';
    data.commands.forEach(cmd => list.appendChild(makeChip(cmd)));
    el.appendChild(list);
  }
}).catch(err => {
  if (typeof logClientError === 'function') logClientError('failed to load /allowed-commands', err);
});

apiFetch('/faq').then(r => r.json()).then(data => {
  if (!data.items || !data.items.length) return;
  const faqBody = document.querySelector('.faq-body');
  data.items.forEach(item => {
    const div = document.createElement('div');
    div.className = 'faq-item';
    const q = document.createElement('div');
    q.className = 'faq-q';
    q.textContent = item.question;
    const a = document.createElement('div');
    a.className = 'faq-a';
    a.textContent = item.answer;
    div.appendChild(q);
    div.appendChild(a);
    faqBody.appendChild(div);
  });
}).catch(err => {
  if (typeof logClientError === 'function') logClientError('failed to load /faq', err);
});

apiFetch('/history').then(r => r.json()).then(data => {
  if (typeof hydrateCmdHistory === 'function') {
    hydrateCmdHistory(data.runs || []);
  }
}).catch(err => {
  if (typeof logClientError === 'function') logClientError('failed to load /history', err);
});

// ── Tabs ──
if (typeof setupTabScrollControls === 'function') setupTabScrollControls();
createTab('tab 1');
runWelcome();
setTimeout(() => {
  if (cmdInput) cmdInput.focus();
}, 0);

document.getElementById('new-tab-btn').addEventListener('click', () => {
  createShortcutTab();
});

// ── Search ──
document.getElementById('search-toggle-btn').addEventListener('click', () => {
  const visible = searchBar.style.display !== 'none';
  searchBar.style.display = visible ? 'none' : 'flex';
  if (!visible) { searchInput.focus(); runSearch(); } else clearSearch();
});

searchInput.addEventListener('input', runSearch);
document.getElementById('search-prev').addEventListener('click', () => navigateSearch(-1));
document.getElementById('search-next').addEventListener('click', () => navigateSearch(1));
searchInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') navigateSearch(e.shiftKey ? -1 : 1);
  if (e.key === 'Escape') { searchBar.style.display = 'none'; clearSearch(); cmdInput.focus(); }
});

searchCaseBtn.addEventListener('click', () => {
  searchCaseSensitive = !searchCaseSensitive;
  searchCaseBtn.classList.toggle('active', searchCaseSensitive);
  runSearch();
});

searchRegexBtn.addEventListener('click', () => {
  searchRegexMode = !searchRegexMode;
  searchRegexBtn.classList.toggle('active', searchRegexMode);
  runSearch();
});

// ── Run history panel ──
document.getElementById('hist-btn').addEventListener('click', () => {
  historyPanel.classList.toggle('open');
  if (historyPanel.classList.contains('open')) refreshHistoryPanel();
});
document.getElementById('history-close').addEventListener('click', () => {
  historyPanel.classList.remove('open');
});

// ── History delete modal ──
document.getElementById('hist-clear-all-btn').addEventListener('click', () => {
  confirmHistAction('clear');
});
document.getElementById('hist-del-cancel').addEventListener('click', () => {
  histDelOverlay.style.display = 'none';
  pendingHistAction = null;
});
document.getElementById('hist-del-nonfav').addEventListener('click', () => {
  histDelOverlay.style.display = 'none';
  executeHistAction('clear-nonfav');
});
document.getElementById('hist-del-confirm').addEventListener('click', () => {
  histDelOverlay.style.display = 'none';
  executeHistAction();
});
histDelOverlay.addEventListener('click', e => {
  if (e.target === histDelOverlay) { histDelOverlay.style.display = 'none'; pendingHistAction = null; }
});

// ── Kill modal ──
document.getElementById('kill-cancel').addEventListener('click', () => {
  closeKillOverlay();
});
document.getElementById('kill-confirm').addEventListener('click', () => {
  confirmPendingKill();
});
killOverlay.addEventListener('click', e => {
  if (e.target === killOverlay) closeKillOverlay();
});

// ── Global keyboard shortcuts ──
// Current bindings intentionally stay narrow:
// - Ctrl+C: running => kill confirm, idle => fresh prompt line
// - welcome settle: printable typing, Enter, Escape
// - Escape: close FAQ and search UI
//
// Planned primary app-safe rollout:
// - Alt+T / Alt+W for new/close tab
// - Alt+ArrowLeft / Alt+ArrowRight for tab cycling
// - Alt+P for permalink, Alt+Shift+C for copy
// - Enter / Escape for kill-confirm accept / cancel
// Browser-native combos like Ctrl/Cmd+T or Ctrl/Cmd+W remain optional
// fallbacks because interception is environment-dependent.
document.addEventListener('keydown', e => {
  if (isKillOverlayOpen()) {
    if (e.key === 'Enter') {
      confirmPendingKill();
      e.preventDefault();
      return;
    }
    if (e.key === 'Escape') {
      closeKillOverlay();
      e.preventDefault();
      return;
    }
  }
  if (handleTabShortcut(e)) return;
  if (handleActionShortcut(e)) return;
  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'c' || e.key === 'C')) {
    if (e.target === cmdInput) return;
    const editable = isEditableTarget(e.target);
    if (editable) return;
    const activeTab = tabs.find(t => t.id === activeTabId);
    if (activeTab && activeTab.st === 'running') {
      if (typeof confirmKill === 'function') confirmKill(activeTabId);
    } else if (typeof interruptPromptLine === 'function') {
      interruptPromptLine(activeTabId);
    }
    e.preventDefault();
    return;
  }
  if (
    typeof _welcomeActive !== 'undefined' && _welcomeActive
    && typeof welcomeOwnsTab === 'function' && welcomeOwnsTab(activeTabId)
    && cmdInput
    && !e.metaKey && !e.ctrlKey && !e.altKey
    && !isEditableTarget(e.target)
    && e.key.length === 1
  ) {
    if (typeof mountShellPrompt === 'function') mountShellPrompt(activeTabId, true);
    cmdInput.focus();
    cmdInput.value += e.key;
    cmdInput.dispatchEvent(new Event('input'));
    e.preventDefault();
    return;
  }
  if (
    e.key === 'Enter'
    && typeof _welcomeActive !== 'undefined' && _welcomeActive
    && typeof welcomeOwnsTab === 'function' && welcomeOwnsTab(activeTabId)
  ) {
    if (typeof mountShellPrompt === 'function') mountShellPrompt(activeTabId, true);
    if (typeof requestWelcomeSettle === 'function') requestWelcomeSettle(activeTabId);
    if (cmdInput) cmdInput.focus();
    e.preventDefault();
    return;
  }
  if (
    e.key === 'Escape'
    && typeof _welcomeActive !== 'undefined' && _welcomeActive
    && typeof welcomeOwnsTab === 'function' && welcomeOwnsTab(activeTabId)
  ) {
    if (typeof mountShellPrompt === 'function') mountShellPrompt(activeTabId, true);
    if (typeof requestWelcomeSettle === 'function') requestWelcomeSettle(activeTabId);
    if (cmdInput) cmdInput.focus();
    e.preventDefault();
    return;
  }
  if (e.key === 'Escape') { closeFaq(); searchBar.style.display = 'none'; clearSearch(); }
});

// ── Global click: dismiss mobile menu and autocomplete ──
document.addEventListener('click', e => {
  if (!mobileMenu.contains(e.target) && e.target !== hamburgerBtn) {
    mobileMenu.classList.remove('open');
  }
  if (!(e.target && e.target.closest && e.target.closest('.prompt-wrap'))) acHide();
});

if (typeof shellPromptWrap !== 'undefined' && shellPromptWrap && cmdInput) {
  shellPromptWrap.addEventListener('click', e => {
    if (e.target === runBtn || (e.target && e.target.closest && e.target.closest('#run-btn'))) return;
    cmdInput.focus();
  });
}

if (cmdInput) {
  cmdInput.addEventListener('focus', () => {
    if (typeof shellPromptWrap !== 'undefined' && shellPromptWrap) shellPromptWrap.classList.add('shell-prompt-focused');
    syncShellPrompt();
  });
  cmdInput.addEventListener('blur', () => {
    if (typeof shellPromptWrap !== 'undefined' && shellPromptWrap) shellPromptWrap.classList.remove('shell-prompt-focused');
    syncShellPrompt();
  });
  cmdInput.addEventListener('select', syncShellPrompt);
  cmdInput.addEventListener('keyup', syncShellPrompt);
}

// ── Autocomplete ──
apiFetch('/autocomplete').then(r => r.json()).then(data => {
  acSuggestions = data.suggestions || [];
}).catch(err => {
  if (typeof logClientError === 'function') logClientError('failed to load /autocomplete', err);
});

cmdInput.addEventListener('input', () => {
  syncShellPrompt();
  const keepHistoryNav =
    typeof _suspendCmdHistoryNavReset !== 'undefined' && _suspendCmdHistoryNavReset;
  if (keepHistoryNav) _suspendCmdHistoryNavReset = false;
  else resetCmdHistoryNav();
  const val = cmdInput.value;
  if (val.length > 0 && typeof requestWelcomeSettle === 'function') {
    if (typeof mountShellPrompt === 'function') mountShellPrompt(activeTabId, true);
    requestWelcomeSettle(activeTabId);
  }
  if (typeof acSuppressInputOnce !== 'undefined' && acSuppressInputOnce) {
    acSuppressInputOnce = false;
    acHide();
    return;
  }
  acIndex = -1;
  if (!val.trim()) { acHide(); return; }
  const q = val.toLowerCase();
  acFiltered = acSuggestions.filter(s => s.toLowerCase().startsWith(q)).slice(0, 12);
  acShow(acFiltered);
});

cmdInput.addEventListener('keydown', e => {
  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'c' || e.key === 'C')) {
    e.preventDefault();
    const activeTab = tabs.find(t => t.id === activeTabId);
    if (activeTab && activeTab.st === 'running') {
      if (typeof confirmKill === 'function') confirmKill(activeTabId);
      return;
    }
    if (typeof interruptPromptLine === 'function') interruptPromptLine(activeTabId);
    return;
  }

  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'w' || e.key === 'W')) {
    e.preventDefault();
    const value = cmdInput.value;
    const { start, end } = getCmdSelection(value);

    if (start !== end) {
      replaceCmdRange(value, start, end);
      return;
    }

    if (start === 0) return;

    const cut = findWordBoundaryLeft(value, start);
    replaceCmdRange(value, cut, start);
    return;
  }

  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'u' || e.key === 'U')) {
    e.preventDefault();
    const value = cmdInput.value;
    const { start, end } = getCmdSelection(value);
    if (start !== end) {
      replaceCmdRange(value, start, end);
      return;
    }
    if (start === 0) return;
    replaceCmdRange(value, 0, start);
    return;
  }

  if (e.ctrlKey && !e.metaKey && !e.altKey && (e.key === 'k' || e.key === 'K')) {
    e.preventDefault();
    const value = cmdInput.value;
    const { start, end } = getCmdSelection(value);
    if (start !== end) {
      replaceCmdRange(value, start, end);
      return;
    }
    if (start >= value.length) return;
    replaceCmdRange(value, start, value.length);
    return;
  }

  if (e.altKey && !e.ctrlKey && !e.metaKey && eventMatchesLetter(e, 'b')) {
    e.preventDefault();
    const value = cmdInput.value;
    const { start } = getCmdSelection(value);
    const next = findWordBoundaryLeft(value, start);
    cmdInput.setSelectionRange(next, next);
    syncShellPrompt();
    return;
  }

  if (e.altKey && !e.ctrlKey && !e.metaKey && eventMatchesLetter(e, 'f')) {
    e.preventDefault();
    const value = cmdInput.value;
    const { end } = getCmdSelection(value);
    const next = findWordBoundaryRight(value, end);
    cmdInput.setSelectionRange(next, next);
    syncShellPrompt();
    return;
  }

  if (e.key === 'Enter') {
    if (
      typeof _welcomeActive !== 'undefined' && _welcomeActive
      && typeof welcomeOwnsTab === 'function' && welcomeOwnsTab(activeTabId)
    ) {
      e.preventDefault();
      if (typeof requestWelcomeSettle === 'function') requestWelcomeSettle(activeTabId);
      if (cmdInput) cmdInput.focus();
      return;
    }
    if (acIndex >= 0 && acFiltered[acIndex]) { e.preventDefault(); acAccept(acFiltered[acIndex]); }
    else { acHide(); runCommand(); }
    return;
  }
  if (e.key === 'Tab') {
    e.preventDefault();
    if (acFiltered.length === 1) { acAccept(acFiltered[0]); }
    else if (acIndex >= 0 && acFiltered[acIndex]) { acAccept(acFiltered[acIndex]); }
    else if (acFiltered.length > 0) { acIndex = 0; acShow(acFiltered); }
    return;
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault();
    const acOpen = acDropdown && acDropdown.style.display !== 'none';
    if (acOpen && acFiltered.length) {
      const acAbove = acDropdown.classList.contains('ac-up');
      acIndex = acAbove
        ? Math.max(acIndex - 1, 0)
        : Math.min(acIndex + 1, acFiltered.length - 1);
      acShow(acFiltered);
      return;
    }
    if (navigateCmdHistory(-1)) acHide();
    return;
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault();
    const acOpen = acDropdown && acDropdown.style.display !== 'none';
    if (acOpen && acFiltered.length) {
      const acAbove = acDropdown.classList.contains('ac-up');
      acIndex = acAbove
        ? Math.min(acIndex + 1, acFiltered.length - 1)
        : Math.max(acIndex - 1, -1);
      acShow(acFiltered);
      return;
    }
    if (navigateCmdHistory(1)) acHide();
    return;
  }
  if (e.key === 'Escape')    { acHide(); return; }
});

// ── Run button ──
runBtn.addEventListener('click', runCommand);

syncShellPrompt();
