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
  // existing action dispatch in controller.js runs unchanged.
  menuSheet?.querySelectorAll('button[data-menu-action]').forEach(btn => {
    btn.addEventListener('click', () => {
      const action = btn.dataset.menuAction;
      closeMenuSheet();
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
    if (recentPeekPreview) recentPeekPreview.textContent = items[0] || '';
    show(recentPeek);
  }
  function openRecentsFromPeek() {
    if (typeof global.showHistoryPanel === 'function') {
      if (typeof global.blurVisibleComposerInputIfMobile === 'function') {
        try { global.blurVisibleComposerInputIfMobile(); } catch (_) { /* non-critical */ }
      }
      if (typeof global.resetHistoryMobileFilters === 'function') {
        try { global.resetHistoryMobileFilters(); } catch (_) { /* non-critical */ }
      }
      global.showHistoryPanel();
      if (typeof global.refreshHistoryPanel === 'function') {
        try { global.refreshHistoryPanel(); } catch (_) { /* non-critical */ }
      }
    }
  }
  recentPeek?.addEventListener('click', openRecentsFromPeek);
  recentPeek?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      openRecentsFromPeek();
    }
  });

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

  // Proxy kb-helper clicks to the legacy mobile-edit-bar buttons so the
  // existing cursor/word/delete handlers in app.js run unchanged.
  kbHelper?.querySelectorAll('button[data-kb-action]').forEach(btn => {
    btn.addEventListener('pointerdown', e => e.preventDefault());
    btn.addEventListener('click', (e) => {
      e.preventDefault();
      const action = btn.dataset.kbAction;
      const proxy = mobileEditBar?.querySelector(
        `button[data-mobile-edit="${action}"], button[data-edit-action="${action}"]`,
      );
      if (proxy) proxy.click();
    });
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
