// ── Mobile chrome controller ──
// Owns the mobile-only UI: progress bar, recent peek row,
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
  const mobileKillBtn         = document.getElementById('mobile-kill-btn');
  const mobileEditBar         = document.getElementById('mobile-edit-bar');
  const hamburgerBtnEl        = document.getElementById('hamburger-btn');
  const statusPillEl          = document.getElementById('status');
  const recentPeek            = document.getElementById('mobile-recent-peek');
  const recentPeekCount       = document.getElementById('mobile-recent-peek-count');
  const recentPeekPreview     = document.getElementById('mobile-recent-peek-preview');
  const recentsSheet          = document.getElementById('mobile-recents-sheet');
  const recentsSheetScrim     = document.getElementById('mobile-recents-sheet-scrim');
  const recentsSheetClearBtn  = document.getElementById('mobile-recents-clear');
  const recentsSheetSearch    = document.getElementById('mobile-recents-search');
  const recentsSheetList      = document.getElementById('mobile-recents-list');
  const menuSheet             = document.getElementById('mobile-menu-sheet');
  const menuSheetScrim        = document.getElementById('mobile-menu-sheet-scrim');
  const menuLnState           = document.getElementById('mobile-menu-ln-state');
  const menuTsState           = document.getElementById('mobile-menu-ts-state');
  const menuWorkflowsCount    = document.getElementById('mobile-menu-workflows-count');
  const menuHistoryCount      = document.getElementById('mobile-menu-history-count');
  const menuThemeHint         = document.getElementById('mobile-menu-theme-hint');
  const kbHelper              = document.getElementById('mobile-kb-helper');

  // ── Progress bar mounted programmatically ──────────────────────
  // Placed inside #mobile-shell-chrome so the teleport logic in app.js that
  // moves the tab bar in and out on viewport changes does not clobber them.
  let progressBar  = null;

  function ensureChromeMounts() {
    if (!mobileShellChrome) return;
    if (!progressBar) {
      progressBar = document.createElement('div');
      progressBar.id = 'mobile-progress-bar';
      progressBar.className = 'shell-progress-bar u-hidden';
      mobileShellChrome.appendChild(progressBar);
    }
  }
  ensureChromeMounts();

  // ── Helpers ─────────────────────────────────────────────────────
  const show = (el) => el && el.classList && el.classList.remove('u-hidden');
  const hide = (el) => el && el.classList && el.classList.add('u-hidden');
  const isRunning = () => !!(statusPillEl && statusPillEl.classList && statusPillEl.classList.contains('running'));

  // ── 2A+2B: Status-driven progress bar and composer ring ─────────
  function syncRunState() {
    const running = isRunning();
    if (running) {
      show(progressBar);
      if (mobileComposer && mobileComposer.classList) mobileComposer.classList.add('is-running');
    } else {
      hide(progressBar);
      if (mobileComposer && mobileComposer.classList) mobileComposer.classList.remove('is-running');
    }
    // Mobile only: the desktop pill intentionally shows only IDLE/RUNNING
    // (HUD LAST EXIT carries the rest), but with no HUD on mobile, an IDLE
    // label sitting inside a red killed/fail pill reads as a bug. Reflect the
    // terminal state in the pill text so the color and label agree. Gated on
    // body.mobile-terminal-mode so the desktop pill stays binary when the
    // mobile DOM is present but the shell is rendering desktop chrome.
    if (statusPillEl && statusPillEl.classList && document.body.classList.contains('mobile-terminal-mode')) {
      if (statusPillEl.classList.contains('killed')) statusPillEl.textContent = 'KILLED';
      else if (statusPillEl.classList.contains('fail')) statusPillEl.textContent = 'FAILED';
    }
  }

  if (mobileKillBtn) {
    mobileKillBtn.addEventListener('click', () => {
      const tabId = typeof global.getActiveTabId === 'function' ? global.getActiveTabId() : null;
      if (tabId && typeof confirmKill === 'function') confirmKill(tabId);
    });
  }
  if (statusPillEl && typeof MutationObserver === 'function') {
    const obs = new MutationObserver(syncRunState);
    obs.observe(statusPillEl, { attributes: true, attributeFilter: ['class'] });
  }
  syncRunState();

  // ── Mobile non-active running-state indicator ──
  // The mobile status pill reflects the active tab only; this surface is
  // the system-level signal that work is happening on a backgrounded tab.
  // Trailing-edge chip with the running non-active count cycles through
  // those tabs on tap (in tab-row order).
  //
  // Kill switch for debugging iOS scroll interactions: append ?ri=off
  // (or ?ri=0) to the URL to fully skip mounting the chip and observers.
  const _runningIndicatorDisabled = (() => {
    try {
      const q = (typeof location !== 'undefined' && location.search) ? location.search : '';
      return /[?&]ri=(?:off|0)\b/.test(q);
    } catch (_) { return false; }
  })();
  const tabsBarEl    = _runningIndicatorDisabled ? null : document.getElementById('tabs-bar');
  const terminalBarEl = tabsBarEl ? tabsBarEl.closest('.terminal-bar') : null;
  let runningChipEl       = null;
  let runningChipCountEl  = null;
  let edgeGlowLeftEl      = null;
  let edgeGlowRightEl     = null;
  let _runningCycleIdx    = 0;

  function _ensureRunningIndicatorMounts() {
    if (!terminalBarEl) return;
    if (!runningChipEl) {
      runningChipEl = document.createElement('button');
      runningChipEl.type = 'button';
      runningChipEl.id = 'mobile-running-chip';
      runningChipEl.className = 'mobile-running-chip u-hidden';
      runningChipEl.setAttribute('aria-label', 'Cycle to next running tab');
      runningChipEl.title = 'Cycle to next running tab';
      const dot = document.createElement('span');
      dot.className = 'mobile-running-dot';
      dot.setAttribute('aria-hidden', 'true');
      dot.textContent = '●';
      runningChipCountEl = document.createElement('span');
      runningChipCountEl.className = 'mobile-running-count';
      runningChipCountEl.textContent = '0';
      runningChipEl.append(dot, runningChipCountEl);
      runningChipEl.addEventListener('click', _onRunningChipTap);
      terminalBarEl.appendChild(runningChipEl);
    }
    // Edge glows are position:fixed overlays parented to body so they
    // never live inside the tabs-bar flex/scroll chain (which empirically
    // destabilises iOS Safari momentum scroll — see the comment block in
    // mobile.css for the full rationale).
    if (!edgeGlowLeftEl && document.body) {
      edgeGlowLeftEl = document.createElement('span');
      edgeGlowLeftEl.className = 'tab-edge-glow tab-edge-glow-left';
      edgeGlowLeftEl.setAttribute('aria-hidden', 'true');
      document.body.appendChild(edgeGlowLeftEl);
    }
    if (!edgeGlowRightEl && document.body) {
      edgeGlowRightEl = document.createElement('span');
      edgeGlowRightEl.className = 'tab-edge-glow tab-edge-glow-right';
      edgeGlowRightEl.setAttribute('aria-hidden', 'true');
      document.body.appendChild(edgeGlowRightEl);
    }
  }

  function _runningNonActiveTabs() {
    if (!tabsBarEl) return [];
    const tabsList = (typeof global.getTabs === 'function') ? global.getTabs() : null;
    if (!Array.isArray(tabsList)) return [];
    const activeId = (typeof global.getActiveTabId === 'function') ? global.getActiveTabId() : null;
    const byId = new Map(tabsList.map(t => [t.id, t]));
    // Tab-row order is the visual order, not the array order — drag-reorder
    // mutates the DOM but not the underlying tabs array.
    const orderedIds = Array.from(tabsBarEl.querySelectorAll('.tab')).map(n => n.dataset.id);
    return orderedIds
      .map(id => byId.get(id))
      .filter(t => !!t && t.st === 'running' && t.id !== activeId);
  }

  // iOS Safari has a known bug where smooth scrollTo/scrollIntoView is
  // silently dropped on the first call to a horizontal scroll container
  // that has never been scrolled (the "cold container" case). Subsequent
  // calls work because the container is "warm". We avoid the bug by
  // setting scrollLeft directly, which always takes effect.
  function _scrollTabIntoView(id) {
    if (!tabsBarEl || !id) return;
    const node = tabsBarEl.querySelector(`.tab[data-id="${id}"]`);
    if (!node) return;
    const tabRect = node.getBoundingClientRect();
    const barRect = tabsBarEl.getBoundingClientRect();
    const visibleLeft = tabRect.left >= barRect.left;
    const visibleRight = tabRect.right <= barRect.right;
    if (visibleLeft && visibleRight) return;
    const tabLeftInContent = tabRect.left - barRect.left + tabsBarEl.scrollLeft;
    const centered = tabLeftInContent - (barRect.width - tabRect.width) / 2;
    const maxScroll = Math.max(0, tabsBarEl.scrollWidth - tabsBarEl.clientWidth);
    tabsBarEl.scrollLeft = Math.max(0, Math.min(maxScroll, centered));
  }

  function _onRunningChipTap() {
    const running = _runningNonActiveTabs();
    if (running.length === 0) return;
    const next = running[_runningCycleIdx % running.length];
    _runningCycleIdx += 1;
    const activate = (typeof window !== 'undefined' && typeof window.activateTab === 'function')
      ? window.activateTab
      : (typeof activateTab === 'function' ? activateTab : null);
    if (activate) activate(next.id, { focusComposer: false });
    // activateTab calls ensureActiveTabVisible internally with smooth
    // scroll, but that gets dropped on the first (cold-container) call.
    // Override with an instant scrollLeft after the activation DOM work
    // has settled so the user always sees the newly-active tab.
    _scrollTabIntoView(next.id);
  }

  function _hideEdgeGlows() {
    if (edgeGlowLeftEl) edgeGlowLeftEl.classList.remove('is-active');
    if (edgeGlowRightEl) edgeGlowRightEl.classList.remove('is-active');
  }

  function _syncEdgeGlows(running) {
    if (!tabsBarEl || !edgeGlowLeftEl || !edgeGlowRightEl) return;
    if (!running || running.length === 0) { _hideEdgeGlows(); return; }
    const barRect = tabsBarEl.getBoundingClientRect();
    // Position both overlays flush against the visible tab-bar edges.
    // Round to whole pixels so the glow edge doesn't sub-pixel blur.
    const top = Math.round(barRect.top) + 'px';
    const height = Math.round(barRect.height) + 'px';
    edgeGlowLeftEl.style.top = top;
    edgeGlowLeftEl.style.height = height;
    edgeGlowLeftEl.style.left = Math.round(barRect.left) + 'px';
    edgeGlowRightEl.style.top = top;
    edgeGlowRightEl.style.height = height;
    edgeGlowRightEl.style.left = Math.round(barRect.right - 22) + 'px';
    // Direction: which side(s) have a running non-active tab off-screen.
    let leftActive = false;
    let rightActive = false;
    for (const t of running) {
      const node = tabsBarEl.querySelector(`.tab[data-id="${t.id}"]`);
      if (!node) continue;
      const r = node.getBoundingClientRect();
      if (r.right < barRect.left + 4) leftActive = true;
      else if (r.left > barRect.right - 4) rightActive = true;
    }
    edgeGlowLeftEl.classList.toggle('is-active', leftActive);
    edgeGlowRightEl.classList.toggle('is-active', rightActive);
  }

  let _runningSyncRaf = 0;
  let _scrollSyncTimer = 0;

  function _applyRunningState() {
    if (!terminalBarEl || !tabsBarEl) return;
    const isMobile = !!(document.body && document.body.classList.contains('mobile-terminal-mode'));
    if (!isMobile) {
      if (runningChipEl) runningChipEl.classList.add('u-hidden');
      _hideEdgeGlows();
      return;
    }
    _ensureRunningIndicatorMounts();
    const running = _runningNonActiveTabs();
    const count = running.length;
    if (count === 0) {
      runningChipEl.classList.add('u-hidden');
      _hideEdgeGlows();
      _runningCycleIdx = 0;
      return;
    }
    runningChipEl.classList.remove('u-hidden');
    runningChipCountEl.textContent = String(count);
    _syncEdgeGlows(running);
  }

  // rAF-coalesced so a burst of class mutations on the tab row folds
  // into a single sync per frame.
  function syncRunningIndicator() {
    if (_runningSyncRaf) return;
    _runningSyncRaf = (typeof requestAnimationFrame === 'function'
      ? requestAnimationFrame
      : (cb) => setTimeout(cb, 16))(() => {
      _runningSyncRaf = 0;
      _applyRunningState();
    });
  }

  if (terminalBarEl && tabsBarEl && typeof MutationObserver === 'function') {
    _ensureRunningIndicatorMounts();
    // Narrow the observer to attribute changes on direct .tab children.
    // Running/active state lives in per-tab classes; we don't need
    // subtree+childList which would also fire on timer textNode updates
    // and drag-reorder DOM moves (both irrelevant to the chip count).
    new MutationObserver(syncRunningIndicator).observe(tabsBarEl, {
      attributes: true,
      attributeFilter: ['class'],
      subtree: true,
    });
    // Also observe childList at the top level so tab add/remove retriggers.
    new MutationObserver(syncRunningIndicator).observe(tabsBarEl, {
      childList: true,
    });
    window.addEventListener('resize', syncRunningIndicator);
    // Edge glow direction depends on scroll position; debounce to
    // scroll-end so we never force layout during momentum. 120ms feels
    // immediate enough once the finger lifts but avoids firing per-frame
    // during the flick.
    tabsBarEl.addEventListener('scroll', () => {
      if (_scrollSyncTimer) clearTimeout(_scrollSyncTimer);
      _scrollSyncTimer = setTimeout(syncRunningIndicator, 120);
    }, { passive: true });
  }
  syncRunningIndicator();

  // ── 2C: Menu sheet ───────────────────────────────────────────────
  function setActionHint(el, text) {
    if (el) el.textContent = text || '';
  }
  function setTogglePressed(labelEl, value) {
    if (!labelEl) return;
    const btn = labelEl.closest('button[data-menu-action]');
    if (!btn) return;
    // Any value other than empty/off counts as "on" — line numbers toggles on/off,
    // but timestamps cycles through off / elapsed / clock so we can't match /^on$/.
    const normalized = typeof value === 'string' ? value.trim().toLowerCase() : '';
    const on = normalized && normalized !== 'off';
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
  }
  function refreshMenuStateHints() {
    // Read current modes from body classes — the canonical source of truth set
    // by output.js / app.js when the user toggles either preference.
    const cls = (document.body && document.body.classList) || null;
    const lnValue = cls && cls.contains('ln-on') ? 'on' : 'off';
    let tsValue = 'off';
    if (cls && cls.contains('ts-elapsed')) tsValue = 'elapsed';
    else if (cls && cls.contains('ts-clock')) tsValue = 'clock';
    setActionHint(menuLnState, lnValue);
    setTogglePressed(menuLnState, lnValue);
    setActionHint(menuTsState, tsValue);
    setTogglePressed(menuTsState, tsValue);
    // Sync the timestamps sub-menu: pressed state on the currently-selected
    // mode, unpressed on the other two. Aria-pressed drives the radio styling.
    menuSheet?.querySelectorAll('[data-menu-action="ts-set"]').forEach((btn) => {
      const isActive = btn.dataset.tsMode === tsValue;
      btn.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    });
  }
  function refreshWorkflowsCount(items) {
    if (!menuWorkflowsCount) return;
    const list = Array.isArray(items) ? items : [];
    menuWorkflowsCount.textContent = list.length ? `${list.length} saved` : '';
  }
  function refreshHistoryCount() {
    if (!menuHistoryCount) return;
    const runs = Array.isArray(_recentsRuns) && _recentsRuns.length
      ? _recentsRuns
      : readCmdHistory();
    menuHistoryCount.textContent = runs.length ? `${runs.length}` : '';
  }
  function refreshThemeHint() {
    if (!menuThemeHint) return;
    const name = (document.body && document.body.dataset && document.body.dataset.theme) || '';
    menuThemeHint.textContent = name;
  }
  // Bind the timestamps sub-menu as a disclosure so aria-expanded and the
  // submenu's u-hidden class stay coordinated. The handle is also used by
  // openMenuSheet() to reset the sub-menu to collapsed each time the sheet
  // opens (so the user never returns to a previously-expanded surface).
  const tsToggleBtn = menuSheet?.querySelector('[data-menu-action="ts-toggle"]');
  const tsSubmenuEl = document.getElementById('mobile-menu-ts-submenu');
  const tsDisclosure = tsToggleBtn ? bindDisclosure(tsToggleBtn, {
    panel: tsSubmenuEl,
    openClass: null,
    hiddenClass: 'u-hidden',
  }) : null;

  function openMenuSheet() {
    refreshMenuStateHints();
    refreshThemeHint();
    refreshHistoryCount();
    tsDisclosure?.close();
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
  global.showMobileMenu = openMenuSheet;
  global.hideMobileMenu = closeMenuSheet;
  global.isMobileMenuOpen = isMenuSheetOpen;

  // Mobile re-routes the 'history' action to the recents pull-up sheet rather
  // than the legacy history panel. controller.js owns the rest of the dispatch.
  menuSheet?.querySelectorAll('button[data-menu-action]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const action = btn.dataset.menuAction;
      if (action === 'history') {
        e.stopImmediatePropagation();
        closeMenuSheet();
        showRecentsSheet();
      }
    }, true);
  });
  // Scrim click + Escape are owned by bindDismissible
  // (ui_dismissible.js) so every sheet/panel/modal surface uses the same
  // registry-driven close cascade instead of hand-rolled wiring.
  if (typeof global.bindDismissible === 'function') {
    global.bindDismissible(menuSheet, {
      level: 'sheet',
      isOpen: isMenuSheetOpen,
      onClose: closeMenuSheet,
      backdropEl: menuSheetScrim,
    });
  }

  // ── 2D: Recent peek ─────────────────────────────────────────────
  function readCmdHistory() {
    const h = global.recentPreviewHistory;
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

  function _recentsParseDate(iso) {
    if (!iso) return null;
    try {
      const d = new Date(iso);
      return Number.isNaN(d.getTime()) ? null : d;
    } catch (_) { return null; }
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
      if (!_recentsDateMatch(r.started, _recentsFilterState.date)) return false;
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
    bindPressable(btn, {
      onActivate: (e) => {
        e.stopPropagation();
        try { handler(); } catch (_) { /* non-critical */ }
      },
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
      const starLabel = isStarred
        ? 'Unstar — stop pinning this command to the top'
        : 'Star — keep this command pinned at the top';
      star.setAttribute('aria-label', starLabel);
      star.title = starLabel;
      bindPressable(star, {
        refocusComposer: false,
        clearPressStyle: true,
        onActivate: (e) => {
          e.stopPropagation();
          if (typeof global._toggleStar === 'function') {
            try { global._toggleStar(cmd); } catch (_) { /* non-critical */ }
          }
          _recentsRenderList();
        },
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
      const parsed = _recentsParseDate(run.started);
      const relFn = typeof _historyRelativeTime === 'function' ? _historyRelativeTime : null;
      timeEl.textContent = parsed && relFn ? relFn(parsed) : '';
      if (parsed) timeEl.title = parsed.toLocaleString();
      const exitEl = document.createElement('span');
      const exitCode = (run.exit_code ?? null);
      exitEl.className = 'sheet-item-exit' + (exitCode !== null && exitCode !== 0 ? ' nonzero' : '');
      exitEl.textContent = exitCode === null ? '—' : `exit ${exitCode}`;
      meta.appendChild(timeEl);
      meta.appendChild(exitEl);

      const actions = document.createElement('div');
      actions.className = 'sheet-item-actions';
      actions.appendChild(_recentsMakeAction('restore', () => {
        if (typeof global.restoreHistoryRunIntoTab !== 'function') return;
        const cmdEl2 = item.querySelector('.sheet-item-cmd');
        if (cmdEl2) cmdEl2.textContent = 'loading…';
        global.restoreHistoryRunIntoTab(run, { hidePanelOnSuccess: false })
          .then(() => closeRecentsSheet())
          .catch(() => {
            if (cmdEl2) cmdEl2.textContent = cmd;
            if (typeof global.showToast === 'function') global.showToast('Failed to load run');
          });
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
        if (typeof global.setComposerValue === 'function') {
          global.setComposerValue(cmd, cmd.length, cmd.length);
        }
        closeRecentsSheet();
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

  // Scrim click + Escape are owned by bindDismissible so
  // the sheet participates in the unified modal > sheet > panel Escape
  // cascade (see ui_dismissible.js).
  if (typeof global.bindDismissible === 'function') {
    global.bindDismissible(recentsSheet, {
      level: 'sheet',
      isOpen: isRecentsSheetOpen,
      onClose: closeRecentsSheet,
      backdropEl: recentsSheetScrim,
    });
  }
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

  // Drag/tap/keyboard close behavior is provided by the shared bindMobileSheet
  // helper (see app/static/js/mobile_sheet.js) so the recents sheet matches
  // every other mobile bottom sheet.
  if (typeof global.bindMobileSheet === 'function') {
    global.bindMobileSheet(recentsSheet, { onClose: closeRecentsSheet });
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
      const labelEl = recentsFiltersToggle.querySelector('.sheet-filter-toggle-label');
      const text = (open ? 'hide filters' : 'filters') + (count ? ` (${count})` : '');
      if (labelEl) labelEl.textContent = text;
      else recentsFiltersToggle.textContent = text;
    }
    _renderRecentsChips();
  }

  if (recentsFiltersToggle) {
    bindDisclosure(recentsFiltersToggle, {
      panel: recentsFiltersExpanded,
      openClass: null,
      hiddenClass: 'u-hidden',
      onToggle: (open) => {
        if (!open) _closeRecentsDropdowns();
        // _recentsSyncFilterUI() rewrites the toggle label ("filters" vs
        // "hide filters") using the just-synced aria-expanded value, so it
        // must run after the helper's sync(), which is already the order
        // onToggle fires in.
        _recentsSyncFilterUI();
      },
    });
  }

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
    trigger?.addEventListener('click', () => {
      const open = wrap.classList.contains('open');
      _closeRecentsDropdowns(open ? null : wrap);
      wrap.classList.toggle('open', !open);
      trigger.setAttribute('aria-expanded', !open ? 'true' : 'false');
    });
    wrap.querySelectorAll('[data-dropdown-value]').forEach(opt => {
      opt.addEventListener('click', () => {
        _recentsFilterState[key] = opt.dataset.dropdownValue;
        wrap.classList.remove('open');
        trigger?.setAttribute('aria-expanded', 'false');
        _recentsSyncFilterUI();
        _recentsRenderList();
      });
    });
  });

  // Close dropdowns on ambient click anywhere in the recents sheet that
  // doesn't land inside a dropdown. bindOutsideClickClose owns the trigger
  // exemption: clicks on the dropdown triggers / option items bubble up but
  // are skipped because they're inside [data-recents-dropdown].
  if (recentsSheet && typeof bindOutsideClickClose === 'function') {
    bindOutsideClickClose(null, {
      scope: recentsSheet,
      isOpen: () => recentsDropdowns.some(w => w.classList.contains('open')),
      onClose: () => _closeRecentsDropdowns(),
      exemptSelectors: ['[data-recents-dropdown]'],
    });
  }

  if (recentsFilterStarred) {
    bindPressable(recentsFilterStarred, {
      refocusComposer: false,
      onActivate: () => {
        _recentsFilterState.starred = !_recentsFilterState.starred;
        _recentsSyncFilterUI();
        _recentsRenderList();
      },
    });
  }

  if (recentsFiltersClear) {
    bindPressable(recentsFiltersClear, {
      refocusComposer: false,
      onActivate: () => {
        _recentsFilterState.root = '';
        _recentsFilterState.exit = 'all';
        _recentsFilterState.date = 'all';
        _recentsFilterState.starred = false;
        _closeRecentsDropdowns();
        _recentsSyncFilterUI();
        _recentsRenderList();
      },
    });
  }

  // Escape-to-close is owned by bindDismissible's unified dispatcher
  // (closeTopmostDismissible). The sheets are registered above so they
  // participate in the same modal > sheet > panel cascade as every
  // other surface.

  // Peek: tap opens the sheet; vertical swipe-up also opens it.
  function openRecentsFromPeek() { showRecentsSheet(); }
  if (recentPeek) {
    // role="button" div — Enter/Space handled by bindPressable; opt into
    // clearPressStyle so the :hover/:active residue on touch doesn't stick
    // after activation (native blur is a no-op on non-focusable elements).
    bindPressable(recentPeek, {
      refocusComposer: false,
      clearPressStyle: true,
      onActivate: openRecentsFromPeek,
    });
  }

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

  // ── Pull-to-refresh suppression ───────────────────────────────────
  // The CSS rule `overscroll-behavior-y: contain` (in mobile-chrome.css) does
  // not actually disable iOS Safari's or Firefox mobile's native pull-to-
  // refresh in this layout. Both engines only honour the property when the
  // element it is set on is itself a non-trivial scroll container — and the
  // mobile shell deliberately keeps body content within the viewport so the
  // body never grows tall enough to scroll. The browsers therefore treat the
  // downward swipe as a navigation-level gesture before any container can
  // claim it.
  //
  // The fix is a delegated touchmove guard: when in mobile-terminal-mode, walk
  // the touch target's ancestor chain looking for a scrollable element that
  // can absorb the gesture. If one exists and isn't already at the boundary
  // for the current direction, let the gesture through. Otherwise call
  // preventDefault on the touchmove so the browser cannot interpret it as
  // pull-to-refresh / overscroll bounce. This intentionally does not interfere
  // with the sheet drag handlers in mobile_sheet.js, which run on Pointer
  // Events with setPointerCapture and `touch-action: none` on the grab — those
  // already bypass the browser's default touch handling.
  let _touchStartX = null;
  let _touchStartY = null;
  document.addEventListener('touchstart', (e) => {
    if (e.touches.length === 1) {
      _touchStartX = e.touches[0].clientX;
      _touchStartY = e.touches[0].clientY;
    } else {
      _touchStartX = null;
      _touchStartY = null;
    }
  }, { passive: true });
  document.addEventListener('touchmove', (e) => {
    if (!document.body.classList.contains('mobile-terminal-mode')) return;
    if (_touchStartY == null || e.touches.length !== 1) return;
    const dy = e.touches[0].clientY - _touchStartY;
    const dx = e.touches[0].clientX - _touchStartX;
    if (dy === 0) return;
    // Predominantly horizontal gestures are never pull-to-refresh
    // candidates; bailing out here lets horizontal scroll containers
    // (e.g. the mobile tab bar, with overflow-y:hidden so the vertical
    // walk below wouldn't find them) receive the full gesture.
    if (Math.abs(dx) >= Math.abs(dy)) return;
    let el = e.target;
    while (el && el !== document.body && el !== document.documentElement) {
      if (el.scrollHeight > el.clientHeight) {
        const oy = getComputedStyle(el).overflowY;
        if (oy === 'auto' || oy === 'scroll') {
          // Scrolling down (dy > 0) is only "would-overscroll" at scrollTop 0.
          // Scrolling up (dy < 0) is only "would-overscroll" at the bottom.
          if (dy > 0 && el.scrollTop > 0) return;
          if (dy < 0 && el.scrollTop + el.clientHeight < el.scrollHeight) return;
          break;
        }
      }
      el = el.parentElement;
    }
    if (e.cancelable) e.preventDefault();
  }, { passive: false });

  global._mobileChrome = {
    nodes: {
      mobileShellChrome, recentPeek, recentPeekCount, recentPeekPreview,
      menuSheet, menuSheetScrim, menuLnState, menuTsState,
      menuWorkflowsCount, menuThemeHint, kbHelper, progressBar,
    },
    openMenuSheet, closeMenuSheet, isMenuSheetOpen,
    renderRecentPeek, syncRunState, syncKbHelper,
    refreshMenuStateHints, refreshWorkflowsCount, refreshThemeHint,
    syncRunningIndicator,
  };
})(typeof window !== 'undefined' ? window : this);
