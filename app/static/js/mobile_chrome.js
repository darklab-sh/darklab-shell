// ── Mobile chrome controller ──
// Owns the mobile-only UI: progress bar + runtime pill, recent peek row,
// bottom-sheet menu from the hamburger, and the keyboard-aware edit helper
// row. Loaded after dom.js, state.js, ui_helpers.js, history.js, tabs.js,
// app.js, controller.js, shell_chrome.js so every helper it delegates to is
// already defined.

(function initMobileChrome(global) {
  if (typeof document === 'undefined') return;

  // Bail on desktop-only builds: every mobile-specific node below is absent
  // when the page is rendered without the mobile shell.
  const mobileShell = document.getElementById('mobile-shell');
  if (!mobileShell) return;

  // ── Elements ────────────────────────────────────────────────────
  const mobileShellChrome     = document.getElementById('mobile-shell-chrome');
  const mobileComposer        = document.getElementById('mobile-composer');
  const mobileEditBar         = document.getElementById('mobile-edit-bar');
  const legacyMobileMenu      = document.getElementById('mobile-menu');
  const hamburgerBtnEl        = document.getElementById('hamburger-btn');
  const statusPillEl          = document.getElementById('status');
  const runTimerEl            = document.getElementById('run-timer');

  const recentPeek            = document.getElementById('mobile-recent-peek');
  const recentPeekCount       = document.getElementById('mobile-recent-peek-count');
  const recentPeekPreview     = document.getElementById('mobile-recent-peek-preview');
  const recentsSheet          = document.getElementById('mobile-recents-sheet');
  const recentsSheetScrim     = document.getElementById('mobile-recents-sheet-scrim');
  const recentsSheetCloseBtn  = document.getElementById('mobile-recents-close');
  const recentsSheetClearBtn  = document.getElementById('mobile-recents-clear');
  const recentsSheetSearch    = document.getElementById('mobile-recents-search');
  const recentsSheetList      = document.getElementById('mobile-recents-list');
  const recentsSheetGrab      = recentsSheet?.querySelector('.sheet-grab') || null;
  const menuSheet             = document.getElementById('mobile-menu-sheet');
  const menuSheetScrim        = document.getElementById('mobile-menu-sheet-scrim');
  const menuSheetCloseBtn     = document.getElementById('mobile-menu-sheet-close');
  const menuLnState           = document.getElementById('mobile-menu-ln-state');
  const menuTsState           = document.getElementById('mobile-menu-ts-state');
  const menuWorkflowsCount    = document.getElementById('mobile-menu-workflows-count');
  const menuThemeHint         = document.getElementById('mobile-menu-theme-hint');
  const kbHelper              = document.getElementById('mobile-kb-helper');

  // ── Progress bar + runtime pill mounted programmatically ──────
  // Placed inside #mobile-shell-chrome so the teleport logic in app.js that
  // moves the tab bar in and out on viewport changes does not clobber them.
  let progressBar  = null;
  let runtimePill  = null;
  let runtimeLabel = null;

  function ensureChromeMounts() {
    if (!mobileShellChrome) return;
    if (!progressBar) {
      progressBar = document.createElement('div');
      progressBar.id = 'mobile-progress-bar';
      progressBar.className = 'shell-progress-bar u-hidden';
      mobileShellChrome.appendChild(progressBar);
    }
    if (!runtimePill) {
      runtimePill = document.createElement('span');
      runtimePill.id = 'mobile-runtime';
      runtimePill.className = 'status-runtime u-hidden';
      runtimeLabel = document.createElement('span');
      runtimeLabel.textContent = '0s';
      runtimePill.appendChild(runtimeLabel);
      mobileShellChrome.appendChild(runtimePill);
    }
  }
  ensureChromeMounts();

  // ── Helpers ─────────────────────────────────────────────────────
  const show = (el) => el && el.classList && el.classList.remove('u-hidden');
  const hide = (el) => el && el.classList && el.classList.add('u-hidden');
  const isRunning = () => !!(statusPillEl && statusPillEl.classList && statusPillEl.classList.contains('running'));

  // ── 2A+2B: Status-driven progress bar, runtime mirror, composer ring ──
  function syncRunState() {
    const running = isRunning();
    if (running) {
      show(progressBar);
      show(runtimePill);
      if (mobileComposer && mobileComposer.classList) mobileComposer.classList.add('is-running');
    } else {
      hide(progressBar);
      hide(runtimePill);
      if (runtimeLabel) runtimeLabel.textContent = '0s';
      if (mobileComposer && mobileComposer.classList) mobileComposer.classList.remove('is-running');
    }
  }
  if (statusPillEl && typeof MutationObserver === 'function') {
    const obs = new MutationObserver(syncRunState);
    obs.observe(statusPillEl, { attributes: true, attributeFilter: ['class'] });
  }
  syncRunState();

  if (runTimerEl && typeof MutationObserver === 'function') {
    const obs = new MutationObserver(() => {
      if (!runtimeLabel) return;
      runtimeLabel.textContent = runTimerEl.textContent || '0s';
    });
    obs.observe(runTimerEl, { characterData: true, childList: true, subtree: true });
  }

  // ── 2C: Menu sheet ───────────────────────────────────────────────
  function setActionHint(el, text) {
    if (el) el.textContent = text || '';
  }
  function setTogglePressed(labelEl, value) {
    if (!labelEl) return;
    const btn = labelEl.closest('button[data-menu-action]');
    if (!btn) return;
    const on = typeof value === 'string' && /^on$/i.test(value.trim());
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
  }
  function refreshMenuStateHints() {
    const ln = legacyMobileMenu?.querySelector('button[data-action="ln"]');
    const ts = legacyMobileMenu?.querySelector('button[data-action="ts"]');
    if (ln) {
      const match = /line numbers:\s*(\S+)/i.exec(ln.textContent || '');
      const value = match ? match[1] : '';
      setActionHint(menuLnState, value);
      setTogglePressed(menuLnState, value);
    }
    if (ts) {
      const match = /timestamps:\s*(\S+)/i.exec(ts.textContent || '');
      const value = match ? match[1] : '';
      setActionHint(menuTsState, value);
      setTogglePressed(menuTsState, value);
    }
  }
  function refreshWorkflowsCount(items) {
    if (!menuWorkflowsCount) return;
    const list = Array.isArray(items) ? items : [];
    menuWorkflowsCount.textContent = list.length ? `${list.length} saved` : '';
  }
  function refreshThemeHint() {
    if (!menuThemeHint) return;
    const name = (document.body && document.body.dataset && document.body.dataset.theme) || '';
    menuThemeHint.textContent = name;
  }
  function openMenuSheet() {
    refreshMenuStateHints();
    refreshThemeHint();
    show(menuSheetScrim);
    show(menuSheet);
  }
  function closeMenuSheet() {
    hide(menuSheet);
    hide(menuSheetScrim);
  }
  function isMenuSheetOpen() {
    return !!(menuSheet && menuSheet.classList && !menuSheet.classList.contains('u-hidden'));
  }

  // Take over the shared mobile-menu helpers so every caller (hamburger click,
  // outside-click dismissal, overlay coordination) opens the new sheet instead.
  // The legacy #mobile-menu node stays in the DOM so its action click handlers
  // (registered in controller.js) still run when we proxy through it below.
  global.showMobileMenu = openMenuSheet;
  global.hideMobileMenu = closeMenuSheet;
  global.isMobileMenuOpen = isMenuSheetOpen;

  // Proxy menu-sheet button clicks to the legacy mobile-menu buttons so the
  // existing action dispatch in controller.js runs unchanged. The 'history'
  // action is re-routed to the new pull-up recents sheet instead of the
  // legacy history panel.
  menuSheet?.querySelectorAll('button[data-menu-action]').forEach(btn => {
    btn.addEventListener('click', () => {
      const action = btn.dataset.menuAction;
      closeMenuSheet();
      if (action === 'history') {
        showRecentsSheet();
        return;
      }
      const proxy = legacyMobileMenu?.querySelector(`button[data-action="${action}"]`);
      if (proxy) proxy.click();
    });
  });
  menuSheetScrim?.addEventListener('click', closeMenuSheet);
  menuSheetCloseBtn?.addEventListener('click', closeMenuSheet);

  // controller.js's global click listener dismisses the mobile menu when the
  // target is outside _uiOverlayRefs.mobileMenu. Repoint that reference at
  // the new sheet so taps inside the sheet are recognized as "inside" and
  // don't trigger an immediate close.
  if (global._uiOverlayRefs && menuSheet) {
    global._uiOverlayRefs.mobileMenu = menuSheet;
  }

  // ── 2D: Recent peek ─────────────────────────────────────────────
  function readCmdHistory() {
    const h = global.cmdHistory;
    return Array.isArray(h) ? h : [];
  }
  function renderRecentPeek() {
    if (!recentPeek) return;
    const items = readCmdHistory();
    if (!items.length) { hide(recentPeek); return; }
    if (recentPeekCount) recentPeekCount.textContent = String(items.length);
    if (recentPeekPreview) recentPeekPreview.textContent = items.slice(0, 3).join(' · ');
    show(recentPeek);
  }

  // ── 2D+: Pull-up recents sheet ─────────────────────────────────
  // Populated on open from the /history API so the list reflects persisted
  // runs (not just the in-memory cmdHistory chip list). Row click rehydrates
  // the composer; per-row actions reuse the existing history.js helpers.
  let _recentsRuns = [];
  let _recentsSearchQuery = '';
  const _recentsFilterState = { root: '', exit: 'all', date: 'all', starred: false };

  function _recentsFormatTime(iso) {
    if (!iso) return '';
    try {
      const d = new Date(iso);
      if (Number.isNaN(d.getTime())) return '';
      return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit', second: '2-digit' });
    } catch (_) { return ''; }
  }
  function _recentsDateMatch(iso, mode) {
    if (mode === 'all') return true;
    if (!iso) return false;
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return false;
    const now = Date.now();
    const delta = now - d.getTime();
    if (mode === 'today') {
      const today = new Date(); today.setHours(0,0,0,0);
      return d.getTime() >= today.getTime();
    }
    if (mode === 'week') return delta <= 7 * 24 * 60 * 60 * 1000;
    return true;
  }
  function _recentsFilter(runs) {
    const q = _recentsSearchQuery.trim().toLowerCase();
    const root = _recentsFilterState.root.trim().toLowerCase();
    const starredSet = _recentsFilterState.starred ? _recentsStarred() : null;
    return runs.filter(r => {
      const cmd = (r.command || '').toLowerCase();
      if (q && !cmd.includes(q)) return false;
      if (root) {
        const first = cmd.trim().split(/\s+/)[0] || '';
        if (first !== root) return false;
      }
      if (_recentsFilterState.exit === 'success' && r.exit_code !== 0) return false;
      if (_recentsFilterState.exit === 'failed' && (r.exit_code === 0 || r.exit_code == null)) return false;
      if (!_recentsDateMatch(r.started_at, _recentsFilterState.date)) return false;
      if (starredSet && !starredSet.has(r.command || '')) return false;
      return true;
    });
  }
  function _recentsFiltersActiveCount() {
    let n = 0;
    if (_recentsFilterState.root.trim()) n++;
    if (_recentsFilterState.exit !== 'all') n++;
    if (_recentsFilterState.date !== 'all') n++;
    if (_recentsFilterState.starred) n++;
    return n;
  }
  function _recentsStarred() {
    try {
      if (typeof global._getStarred === 'function') return global._getStarred();
    } catch (_) { /* non-critical */ }
    return new Set();
  }
  function _recentsMakeAction(label, handler) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'sheet-item-action';
    btn.textContent = label;
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      try { handler(); } catch (_) { /* non-critical */ }
    });
    return btn;
  }
  function _recentsRenderList() {
    if (!recentsSheetList) return;
    recentsSheetList.replaceChildren();
    const filtered = _recentsFilter(_recentsRuns);
    const starred = _recentsStarred();
    if (!filtered.length) {
      const empty = document.createElement('div');
      empty.className = 'sheet-item';
      empty.style.color = 'var(--muted)';
      empty.style.opacity = '0.7';
      empty.style.justifyContent = 'center';
      empty.style.alignItems = 'center';
      empty.textContent = _recentsSearchQuery ? 'no matches' : 'no recent commands';
      recentsSheetList.appendChild(empty);
      return;
    }
    filtered.forEach(run => {
      const cmd = run.command || '';
      const isStarred = starred.has(cmd);
      const item = document.createElement('div');
      item.className = 'sheet-item';
      item.dataset.cmd = cmd;

      const head = document.createElement('div');
      head.className = 'sheet-item-head';
      const star = document.createElement('span');
      star.className = 'sheet-item-star' + (isStarred ? ' starred' : '');
      star.textContent = isStarred ? '★' : '☆';
      star.setAttribute('role', 'button');
      star.setAttribute('tabindex', '0');
      star.setAttribute('aria-label', isStarred ? 'Unstar' : 'Star');
      star.addEventListener('click', (e) => {
        e.stopPropagation();
        if (typeof global._toggleStar === 'function') {
          try { global._toggleStar(cmd); } catch (_) { /* non-critical */ }
        }
        _recentsRenderList();
      });
      const cmdEl = document.createElement('span');
      cmdEl.className = 'sheet-item-cmd';
      cmdEl.textContent = cmd;
      head.appendChild(star);
      head.appendChild(cmdEl);

      const meta = document.createElement('div');
      meta.className = 'sheet-item-meta';
      const timeEl = document.createElement('span');
      timeEl.className = 'sheet-item-time';
      timeEl.textContent = _recentsFormatTime(run.started_at || run.created_at);
      const exitEl = document.createElement('span');
      const exitCode = (run.exit_code ?? null);
      exitEl.className = 'sheet-item-exit' + (exitCode !== null && exitCode !== 0 ? ' nonzero' : '');
      exitEl.textContent = exitCode === null ? '—' : `exit ${exitCode}`;
      meta.appendChild(timeEl);
      meta.appendChild(exitEl);

      const actions = document.createElement('div');
      actions.className = 'sheet-item-actions';
      actions.appendChild(_recentsMakeAction('copy', () => {
        if (typeof global.copyTextToClipboard === 'function') {
          global.copyTextToClipboard(cmd)
            .then(() => global.showToast && global.showToast('Command copied'))
            .catch(() => global.showToast && global.showToast('Copy failed', 'error'));
        }
      }));
      actions.appendChild(_recentsMakeAction('permalink', () => {
        if (!run.id) return;
        const url = `${location.origin}/history/${run.id}`;
        if (typeof global.shareUrl === 'function') {
          global.shareUrl(url).catch(() => global.showToast && global.showToast('Share failed', 'error'));
        }
      }));
      actions.appendChild(_recentsMakeAction('delete', () => {
        if (!run.id) return;
        if (typeof global.confirmHistAction === 'function') {
          global.confirmHistAction('delete', run.id, run.command);
        }
      }));

      item.appendChild(head);
      item.appendChild(meta);
      item.appendChild(actions);

      item.addEventListener('click', (e) => {
        if (e.target.closest('.sheet-item-action, .sheet-item-star')) return;
        if (typeof global.restoreHistoryRunIntoTab === 'function') {
          const cmdEl2 = item.querySelector('.sheet-item-cmd');
          if (cmdEl2) cmdEl2.textContent = 'loading…';
          global.restoreHistoryRunIntoTab(run, { hidePanelOnSuccess: false })
            .then(() => closeRecentsSheet())
            .catch(() => {
              if (cmdEl2) cmdEl2.textContent = cmd;
              if (typeof global.showToast === 'function') global.showToast('Failed to load run');
            });
        } else {
          closeRecentsSheet();
        }
      });

      recentsSheetList.appendChild(item);
    });
  }
  function _recentsFetch() {
    if (typeof global.apiFetch !== 'function') return Promise.resolve([]);
    return global.apiFetch('/history')
      .then(r => r.json())
      .then(data => Array.isArray(data.runs) ? data.runs : [])
      .catch(() => []);
  }
  function showRecentsSheet() {
    if (!recentsSheet) return;
    _recentsSearchQuery = '';
    if (recentsSheetSearch) recentsSheetSearch.value = '';
    if (typeof global.blurVisibleComposerInputIfMobile === 'function') {
      try { global.blurVisibleComposerInputIfMobile(); } catch (_) { /* non-critical */ }
    }
    // Reset filter UI each open so users don't inherit stale state.
    _recentsFilterState.root = '';
    _recentsFilterState.exit = 'all';
    _recentsFilterState.date = 'all';
    _recentsFilterState.starred = false;
    if (recentsFiltersToggle) recentsFiltersToggle.setAttribute('aria-expanded', 'false');
    if (recentsFiltersExpanded) recentsFiltersExpanded.classList.add('u-hidden');
    _recentsSyncFilterUI();
    show(recentsSheetScrim);
    show(recentsSheet);
    _recentsFetch().then(runs => {
      _recentsRuns = runs;
      _recentsRenderList();
    });
  }
  function closeRecentsSheet() {
    _closeRecentsDropdowns();
    hide(recentsSheet);
    hide(recentsSheetScrim);
  }
  function isRecentsSheetOpen() {
    return !!(recentsSheet && recentsSheet.classList && !recentsSheet.classList.contains('u-hidden'));
  }

  recentsSheetScrim?.addEventListener('click', closeRecentsSheet);
  recentsSheetCloseBtn?.addEventListener('click', closeRecentsSheet);
  recentsSheetClearBtn?.addEventListener('click', () => {
    if (typeof global.confirmHistAction === 'function') {
      global.confirmHistAction('clear');
    }
  });

  // After the legacy confirm modal runs a delete/clear, refreshHistoryPanel
  // is the signal that the server state changed — piggyback on it to refresh
  // our sheet list so the UI stays in sync without a manual re-fetch.
  if (typeof global.refreshHistoryPanel === 'function') {
    const _origRefreshHistoryPanel = global.refreshHistoryPanel;
    global.refreshHistoryPanel = function wrappedRefreshHistoryPanel(...args) {
      const result = _origRefreshHistoryPanel.apply(this, args);
      if (isRecentsSheetOpen()) {
        _recentsFetch().then(runs => {
          _recentsRuns = runs;
          _recentsRenderList();
        });
      }
      return result;
    };
  }

  let _recentsSearchTimer = null;
  recentsSheetSearch?.addEventListener('input', (e) => {
    _recentsSearchQuery = e.target.value || '';
    if (_recentsSearchTimer) clearTimeout(_recentsSearchTimer);
    _recentsSearchTimer = setTimeout(_recentsRenderList, 100);
  });

  // Grab handle: tap closes, drag-down (>= 30px) closes. Pointer events cover
  // mouse + touch in WKWebView without needing a separate touch path.
  if (recentsSheetGrab) {
    let dragStartY = null;
    let maxDy = 0;
    recentsSheetGrab.addEventListener('pointerdown', (e) => {
      dragStartY = e.clientY;
      maxDy = 0;
      try { recentsSheetGrab.setPointerCapture(e.pointerId); } catch (_) { /* non-critical */ }
    });
    recentsSheetGrab.addEventListener('pointermove', (e) => {
      if (dragStartY === null) return;
      const dy = e.clientY - dragStartY;
      if (dy > maxDy) maxDy = dy;
      if (dy > 30) {
        dragStartY = null;
        closeRecentsSheet();
      }
    });
    const endDrag = (e) => {
      if (dragStartY !== null && maxDy < 10) {
        // Treat as a tap: close the sheet.
        closeRecentsSheet();
      }
      dragStartY = null;
      maxDy = 0;
    };
    recentsSheetGrab.addEventListener('pointerup', endDrag);
    recentsSheetGrab.addEventListener('pointercancel', () => { dragStartY = null; maxDy = 0; });
    recentsSheetGrab.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        closeRecentsSheet();
      }
    });
  }

  const recentsFiltersToggle   = document.getElementById('mobile-recents-filters-toggle');
  const recentsFiltersExpanded = document.getElementById('mobile-recents-filters-expanded');
  const recentsFiltersClear    = document.getElementById('mobile-recents-filters-clear');
  const recentsFilterRoot      = document.getElementById('mobile-recents-filter-root');
  const recentsFilterStarred   = recentsSheet?.querySelector('[data-recents-filter="starred"]') || null;
  const recentsDropdowns       = Array.from(recentsSheet?.querySelectorAll('[data-recents-dropdown]') || []);
  const recentsChipsEl         = document.getElementById('mobile-recents-chips');

  const _dropdownLabels = {
    exit: { all: 'all', success: 'success (0)', failed: 'failed (non-zero)' },
    date: { all: 'all', today: 'today', week: 'this week' },
  };
  // Short labels used inside the active-filter chips (desktop uses the same
  // pattern: shorter inside chips than inside the filter rows).
  const _chipLabels = {
    exit: { success: 'exit 0', failed: 'exit ≠ 0' },
    date: { today: 'today', week: 'past week' },
  };

  function _clearOneFilter(key) {
    if (key === 'root')    _recentsFilterState.root = '';
    if (key === 'exit')    _recentsFilterState.exit = 'all';
    if (key === 'date')    _recentsFilterState.date = 'all';
    if (key === 'starred') _recentsFilterState.starred = false;
    _recentsSyncFilterUI();
    _recentsRenderList();
  }

  function _renderRecentsChips() {
    if (!recentsChipsEl) return;
    recentsChipsEl.replaceChildren();
    const push = (key, text) => {
      const chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'filter-chip';
      chip.dataset.chipKey = key;
      chip.setAttribute('aria-label', `Clear filter ${text}`);
      const label = document.createElement('span');
      label.textContent = text;
      const x = document.createElement('span');
      x.className = 'filter-chip-x';
      x.textContent = '×';
      chip.append(label, x);
      chip.addEventListener('click', () => _clearOneFilter(key));
      recentsChipsEl.appendChild(chip);
    };
    const s = _recentsFilterState;
    if (s.root.trim())        push('root',    `root: ${s.root.trim()}`);
    if (s.exit !== 'all')     push('exit',    _chipLabels.exit[s.exit] || s.exit);
    if (s.date !== 'all')     push('date',    _chipLabels.date[s.date] || s.date);
    if (s.starred)            push('starred', 'starred');
  }

  function _closeRecentsDropdowns(except) {
    recentsDropdowns.forEach(wrap => {
      if (wrap === except) return;
      wrap.classList.remove('open');
      wrap.querySelector('.sheet-filter-dropdown')?.setAttribute('aria-expanded', 'false');
    });
  }

  function _recentsSyncFilterUI() {
    if (recentsFilterRoot) {
      recentsFilterRoot.value = _recentsFilterState.root;
      recentsFilterRoot.closest('.sheet-filter-row')?.classList.toggle('active', !!_recentsFilterState.root.trim());
    }
    recentsDropdowns.forEach(wrap => {
      const key = wrap.dataset.recentsDropdown;
      const val = _recentsFilterState[key] || 'all';
      const labelMap = _dropdownLabels[key] || {};
      const labelEl = wrap.querySelector('[data-dropdown-label]');
      if (labelEl) labelEl.textContent = labelMap[val] || val;
      wrap.classList.toggle('active', val !== 'all');
      wrap.querySelectorAll('[data-dropdown-value]').forEach(opt => {
        opt.setAttribute('aria-selected', opt.dataset.dropdownValue === val ? 'true' : 'false');
      });
    });
    if (recentsFilterStarred) {
      recentsFilterStarred.setAttribute('aria-pressed', _recentsFilterState.starred ? 'true' : 'false');
    }
    if (recentsFiltersToggle) {
      const count = _recentsFiltersActiveCount();
      const open = recentsFiltersToggle.getAttribute('aria-expanded') === 'true';
      recentsFiltersToggle.textContent = (open ? 'hide filters' : 'filters') + (count ? ` (${count})` : '');
    }
    _renderRecentsChips();
  }

  recentsFiltersToggle?.addEventListener('click', () => {
    const open = recentsFiltersToggle.getAttribute('aria-expanded') === 'true';
    const next = !open;
    recentsFiltersToggle.setAttribute('aria-expanded', next ? 'true' : 'false');
    if (recentsFiltersExpanded) recentsFiltersExpanded.classList.toggle('u-hidden', !next);
    if (!next) _closeRecentsDropdowns();
    _recentsSyncFilterUI();
  });

  let _recentsRootTimer = null;
  recentsFilterRoot?.addEventListener('input', (e) => {
    _recentsFilterState.root = e.target.value || '';
    if (_recentsRootTimer) clearTimeout(_recentsRootTimer);
    _recentsRootTimer = setTimeout(() => {
      _recentsSyncFilterUI();
      _recentsRenderList();
    }, 100);
  });

  recentsDropdowns.forEach(wrap => {
    const key = wrap.dataset.recentsDropdown;
    const trigger = wrap.querySelector('.sheet-filter-dropdown');
    trigger?.addEventListener('click', (e) => {
      e.stopPropagation();
      const open = wrap.classList.contains('open');
      _closeRecentsDropdowns(open ? null : wrap);
      wrap.classList.toggle('open', !open);
      trigger.setAttribute('aria-expanded', !open ? 'true' : 'false');
    });
    wrap.querySelectorAll('[data-dropdown-value]').forEach(opt => {
      opt.addEventListener('click', (e) => {
        e.stopPropagation();
        _recentsFilterState[key] = opt.dataset.dropdownValue;
        wrap.classList.remove('open');
        trigger?.setAttribute('aria-expanded', 'false');
        _recentsSyncFilterUI();
        _recentsRenderList();
      });
    });
  });

  // Close dropdowns on outside click within the sheet.
  recentsSheet?.addEventListener('click', (e) => {
    if (!e.target.closest?.('[data-recents-dropdown]')) _closeRecentsDropdowns();
  });

  recentsFilterStarred?.addEventListener('click', () => {
    _recentsFilterState.starred = !_recentsFilterState.starred;
    _recentsSyncFilterUI();
    _recentsRenderList();
  });

  recentsFiltersClear?.addEventListener('click', () => {
    _recentsFilterState.root = '';
    _recentsFilterState.exit = 'all';
    _recentsFilterState.date = 'all';
    _recentsFilterState.starred = false;
    _closeRecentsDropdowns();
    _recentsSyncFilterUI();
    _recentsRenderList();
  });

  // Escape dismisses whichever sheet is on top.
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    if (isRecentsSheetOpen()) { e.preventDefault(); closeRecentsSheet(); return; }
    if (isMenuSheetOpen()) { e.preventDefault(); closeMenuSheet(); }
  });

  // Peek: tap opens the sheet; vertical swipe-up also opens it.
  function openRecentsFromPeek() { showRecentsSheet(); }
  recentPeek?.addEventListener('click', openRecentsFromPeek);
  recentPeek?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      openRecentsFromPeek();
    }
  });

  if (recentPeek) {
    let peekStartY = null;
    recentPeek.addEventListener('pointerdown', (e) => { peekStartY = e.clientY; });
    recentPeek.addEventListener('pointermove', (e) => {
      if (peekStartY === null) return;
      const dy = peekStartY - e.clientY;
      if (dy > 8) {
        peekStartY = null;
        openRecentsFromPeek();
      }
    });
    const endPeekDrag = () => { peekStartY = null; };
    recentPeek.addEventListener('pointerup', endPeekDrag);
    recentPeek.addEventListener('pointercancel', endPeekDrag);
  }

  if (typeof global.renderHistory === 'function') {
    const originalRenderHistory = global.renderHistory;
    global.renderHistory = function wrappedMobileRenderHistory(...args) {
      const result = originalRenderHistory.apply(this, args);
      try { renderRecentPeek(); } catch (_) { /* non-critical */ }
      return result;
    };
  }
  renderRecentPeek();

  // Mirror the workflows list count into the menu-sheet hint so "workflows"
  // advertises how many are available without opening the overlay.
  if (typeof global.renderRailWorkflows === 'function') {
    const originalRenderRailWorkflows = global.renderRailWorkflows;
    global.renderRailWorkflows = function wrappedMobileRenderRailWorkflows(items) {
      const result = originalRenderRailWorkflows.apply(this, arguments);
      try { refreshWorkflowsCount(items); } catch (_) { /* non-critical */ }
      return result;
    };
  }

  // ── 2E: Keyboard helper row ─────────────────────────────────────
  function syncKbHelper() {
    const open = !!(document.body && document.body.classList
                    && document.body.classList.contains('mobile-keyboard-open'));
    if (open) {
      show(kbHelper);
      // body.mobile-keyboard-open #mobile-edit-bar outranks .u-hidden, so
      // suppress the legacy bar with an inline style while the helper row is
      // active. Reset the style on close so the default CSS display:none
      // applies again.
      if (mobileEditBar && mobileEditBar.style) mobileEditBar.style.display = 'none';
    } else {
      hide(kbHelper);
      if (mobileEditBar && mobileEditBar.style) mobileEditBar.style.display = '';
    }
  }
  if (document.body && typeof MutationObserver === 'function') {
    const obs = new MutationObserver(syncKbHelper);
    obs.observe(document.body, { attributes: true, attributeFilter: ['class'] });
  }
  syncKbHelper();

  // The legacy #mobile-edit-bar handlers in app.js are bound to pointerdown,
  // not click, so proxy.click() on them does nothing. Invoke the same
  // performMobileEditAction entry point directly. preventDefault on
  // pointerdown keeps the composer input from losing focus when a helper
  // key is tapped.
  kbHelper?.querySelectorAll('button[data-kb-action]').forEach(btn => {
    const action = btn.dataset.kbAction;
    const fire = () => {
      if (typeof global.performMobileEditAction === 'function') {
        try { global.performMobileEditAction(action); } catch (_) { /* non-critical */ }
      }
    };
    btn.addEventListener('pointerdown', (e) => { e.preventDefault(); fire(); });
    btn.addEventListener('mousedown',   (e) => { e.preventDefault(); });
    btn.addEventListener('click',       (e) => { e.preventDefault(); });
  });

  global._mobileChrome = {
    nodes: {
      mobileShellChrome, recentPeek, recentPeekCount, recentPeekPreview,
      menuSheet, menuSheetScrim, menuSheetCloseBtn, menuLnState, menuTsState,
      menuWorkflowsCount, menuThemeHint, kbHelper, progressBar, runtimePill, runtimeLabel,
    },
    openMenuSheet, closeMenuSheet, isMenuSheetOpen,
    renderRecentPeek, syncRunState, syncKbHelper,
    refreshMenuStateHints, refreshWorkflowsCount, refreshThemeHint,
  };
})(typeof window !== 'undefined' ? window : this);
