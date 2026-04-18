// ── Mobile chrome controller ──
// Owns the mobile-only UI: progress bar + runtime pill, recent peek row + pull-
// up recents sheet, bottom-sheet menu from the hamburger, and the keyboard-
// aware edit helper row. Loaded after dom.js, state.js, ui_helpers.js,
// history.js, tabs.js, app.js, controller.js, shell_chrome.js so every helper
// it delegates to is already defined.

(function initMobileChrome(global) {
  if (typeof document === 'undefined') return;

  // Bail on desktop-only builds: every mobile-specific node below is absent
  // when the page is rendered without the mobile shell.
  const mobileShell = document.getElementById('mobile-shell');
  if (!mobileShell) return;

  // ── Elements ────────────────────────────────────────────────────
  const mobileShellChrome     = document.getElementById('mobile-shell-chrome');
  const recentPeek            = document.getElementById('mobile-recent-peek');
  const recentPeekCount       = document.getElementById('mobile-recent-peek-count');
  const recentPeekPreview     = document.getElementById('mobile-recent-peek-preview');
  const recentsSheet          = document.getElementById('mobile-recents-sheet');
  const recentsSheetScrim     = document.getElementById('mobile-recents-sheet-scrim');
  const recentsList           = document.getElementById('mobile-recents-list');
  const recentsSearch         = document.getElementById('mobile-recents-search');
  const recentsChips          = document.getElementById('mobile-recents-chips');
  const recentsCloseBtn       = document.getElementById('mobile-recents-close');
  const recentsClearBtn       = document.getElementById('mobile-recents-clear');
  const menuSheet             = document.getElementById('mobile-menu-sheet');
  const menuSheetScrim        = document.getElementById('mobile-menu-sheet-scrim');
  const menuSheetCloseBtn     = document.getElementById('mobile-menu-sheet-close');
  const menuLnState           = document.getElementById('mobile-menu-ln-state');
  const menuTsState           = document.getElementById('mobile-menu-ts-state');
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

  // Phase 2 will wire: runtime tick, progress toggle, peek rendering,
  // recents sheet population, menu sheet actions, keyboard-aware kb-helper.
  // Phase 1 exposes the mount references so downstream code can reach them.
  global._mobileChrome = {
    nodes: {
      mobileShellChrome,
      recentPeek,
      recentPeekCount,
      recentPeekPreview,
      recentsSheet,
      recentsSheetScrim,
      recentsList,
      recentsSearch,
      recentsChips,
      recentsCloseBtn,
      recentsClearBtn,
      menuSheet,
      menuSheetScrim,
      menuSheetCloseBtn,
      menuLnState,
      menuTsState,
      kbHelper,
      progressBar,
      runtimePill,
      runtimeLabel,
    },
  };
})(typeof window !== 'undefined' ? window : this);
