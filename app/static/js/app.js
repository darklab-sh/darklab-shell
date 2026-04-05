// ── app.js — Initialization ──
// This file wires event listeners and bootstraps the app after all modules load.

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
}

document.getElementById('ts-btn').addEventListener('click', () => {
  _setTsMode(_tsModes[(_tsModes.indexOf(tsMode) + 1) % _tsModes.length]);
});

document.getElementById('theme-btn').addEventListener('click', () => {
  document.body.classList.toggle('light');
  localStorage.setItem('theme', document.body.classList.contains('light') ? 'light' : 'dark');
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
    }
    if (action === 'theme') {
      document.body.classList.toggle('light');
      localStorage.setItem('theme', document.body.classList.contains('light') ? 'light' : 'dark');
    }
    if (action === 'faq') openFaq();
  });
});

// ── FAQ ──
function openFaq() { document.getElementById('faq-overlay').classList.add('open'); }
function closeFaq() { document.getElementById('faq-overlay').classList.remove('open'); }

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
    chip.title = 'Click to load into command bar';
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
    el.innerHTML = 'Click any command to load it into the command bar:';
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
    el.innerHTML = 'Click any command to load it into the command bar:';
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
createTab('tab 1');
runWelcome();

document.getElementById('new-tab-btn').addEventListener('click', () => {
  createTab('tab ' + (tabs.length + 1));
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
  killOverlay.style.display = 'none';
  pendingKillTabId = null;
});
document.getElementById('kill-confirm').addEventListener('click', () => {
  killOverlay.style.display = 'none';
  if (pendingKillTabId) { doKill(pendingKillTabId); pendingKillTabId = null; }
});
killOverlay.addEventListener('click', e => {
  if (e.target === killOverlay) { killOverlay.style.display = 'none'; pendingKillTabId = null; }
});

// ── Global keyboard shortcuts ──
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') { closeFaq(); searchBar.style.display = 'none'; clearSearch(); }
});

// ── Global click: dismiss mobile menu and autocomplete ──
document.addEventListener('click', e => {
  if (!mobileMenu.contains(e.target) && e.target !== hamburgerBtn) {
    mobileMenu.classList.remove('open');
  }
  if (!e.target.closest('.prompt-wrap')) acHide();
});

// ── Autocomplete ──
apiFetch('/autocomplete').then(r => r.json()).then(data => {
  acSuggestions = data.suggestions || [];
}).catch(err => {
  if (typeof logClientError === 'function') logClientError('failed to load /autocomplete', err);
});

cmdInput.addEventListener('input', () => {
  resetCmdHistoryNav();
  const val = cmdInput.value;
  if (val.trim() && typeof requestWelcomeSettle === 'function') {
    requestWelcomeSettle(activeTabId);
  }
  acIndex = -1;
  if (!val.trim()) { acHide(); return; }
  acFiltered = acSuggestions.filter(s => s.toLowerCase().includes(val.toLowerCase())).slice(0, 12);
  acShow(acFiltered);
});

cmdInput.addEventListener('keydown', e => {
  if (e.key === 'Enter') {
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
    if (acFiltered.length) {
      acIndex = Math.min(acIndex + 1, acFiltered.length - 1);
      acShow(acFiltered);
      return;
    }
    if (navigateCmdHistory(-1)) acHide();
    return;
  }
  if (e.key === 'ArrowUp') {
    e.preventDefault();
    if (acFiltered.length) {
      acIndex = Math.max(acIndex - 1, -1);
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
