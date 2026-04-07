// ── Shared UI state ──
// The browser scripts still read/write these names directly, but the actual
// storage lives here so the app can move away from prompt-specific globals in
// a controlled way.
(function initSharedState(global) {
  const defaults = {
    tabs: [],
    activeTabId: null,
    acSuggestions: [],
    acFiltered: [],
    acIndex: -1,
    acSuppressInputOnce: false,
    searchMatches: [],
    searchMatchIdx: -1,
    searchCaseSensitive: false,
    searchRegexMode: false,
    cmdHistory: [],
    _cmdHistoryNavIndex: -1,
    _cmdHistoryNavDraft: '',
    _suspendCmdHistoryNavReset: false,
    pendingHistAction: null,
    _welcomeActive: false,
    _welcomeDone: false,
    _welcomeTabId: null,
    _welcomeBanner: null,
    _welcomeLiveLine: null,
    _welcomeHintNode: null,
    _welcomeStatusNodes: [],
    _welcomePlan: null,
    _welcomeNextBlockIndex: 0,
    _welcomeSettleRequested: false,
    _welcomeBootPending: true,
    timerInterval: null,
    timerStart: null,
    pendingKillTabId: null,
  };
  const state = global.APP_STATE || (global.APP_STATE = {});
  Object.assign(state, defaults);
  const getMobileMenuEl = () => mobileMenu || null;

  const bindings = [
    'tabs',
    'activeTabId',
    'acSuggestions',
    'acFiltered',
    'acIndex',
    'acSuppressInputOnce',
    'searchMatches',
    'searchMatchIdx',
    'searchCaseSensitive',
    'searchRegexMode',
    'cmdHistory',
    '_cmdHistoryNavIndex',
    '_cmdHistoryNavDraft',
    '_suspendCmdHistoryNavReset',
    'pendingHistAction',
    '_welcomeActive',
    '_welcomeDone',
    '_welcomeTabId',
    '_welcomeBanner',
    '_welcomeLiveLine',
    '_welcomeHintNode',
    '_welcomeStatusNodes',
    '_welcomePlan',
    '_welcomeNextBlockIndex',
    '_welcomeSettleRequested',
    '_welcomeBootPending',
    'timerInterval',
    'timerStart',
    'pendingKillTabId',
  ];

  for (const name of bindings) {
    Object.defineProperty(global, name, {
      configurable: true,
      enumerable: true,
      get() {
        return state[name];
      },
      set(value) {
        state[name] = value;
      },
    });
  }

  global.getAppState = () => state;
  global.resetAppState = () => Object.assign(state, defaults);

  // ── Tab accessors ──
  // Use these instead of reading/writing tabs and activeTabId directly.
  // Direct access still works (via the property descriptors above), but these
  // setters make mutation sites explicit and provide a stable boundary for
  // future refactoring.
  global.getTabs = () => state.tabs;
  global.setTabs = (v) => { state.tabs = v; };
  global.getActiveTabId = () => state.activeTabId;
  global.setActiveTabId = (v) => { state.activeTabId = v; };
  global.getActiveTab = () => state.tabs.find(t => t.id === state.activeTabId);
  global.getTab = (id) => state.tabs.find(t => t.id === id);

  global.getComposerInputs = () => ({
    desktop: (typeof cmdInput !== 'undefined' && cmdInput) || null,
    mobile: (typeof mobileCmdInput !== 'undefined' && mobileCmdInput) || null,
  });
  global.getVisibleComposerInput = () => {
    const { desktop, mobile } = global.getComposerInputs();
    const mobileShellActive = !!(typeof document !== 'undefined'
      && document.body
      && document.body.classList
      && document.body.classList.contains('mobile-terminal-mode'));
    if (mobileShellActive && mobile) return mobile;
    return desktop;
  };
  global.getComposerValue = () => {
    const input = global.getVisibleComposerInput();
    return input ? input.value : '';
  };
  global.focusComposerInput = (input = null, { preventScroll = false } = {}) => {
    const target = input || global.getVisibleComposerInput();
    if (!target || typeof target.focus !== 'function') return false;
    try {
      if (preventScroll) target.focus({ preventScroll: true });
      else target.focus();
    } catch (_) {
      target.focus();
    }
    return true;
  };
  global.focusVisibleComposerInput = ({ preventScroll = false } = {}) => {
    const target = (typeof getVisibleComposerInput === 'function')
      ? getVisibleComposerInput()
      : global.getVisibleComposerInput();
    return global.focusComposerInput(target, { preventScroll });
  };
  global.blurVisibleComposerInput = () => {
    const target = (typeof getVisibleComposerInput === 'function')
      ? getVisibleComposerInput()
      : global.getVisibleComposerInput();
    if (!target || typeof target.blur !== 'function') return false;
    target.blur();
    return true;
  };
  global.blurVisibleComposerInputIfMobile = () => {
    if (typeof useMobileTerminalViewportMode !== 'function' || !useMobileTerminalViewportMode()) return false;
    return global.blurVisibleComposerInput();
  };
  global.focusAnyComposerInput = ({ preventScroll = false } = {}) => {
    return global.focusVisibleComposerInput({ preventScroll });
  };
  global.syncMobileComposerKeyboardState = (offset = null, { active = true } = {}) => {
    if (typeof document === 'undefined' || !document.body || !document.body.classList) return false;
    const nextOffset = typeof offset === 'number' ? offset : 0;
    document.documentElement?.style?.setProperty('--mobile-keyboard-offset', `${nextOffset}px`);
    const keyboardOpen = active && typeof isMobileKeyboardOpen === 'function' ? isMobileKeyboardOpen(nextOffset) : false;
    document.body.classList.toggle('mobile-keyboard-open', keyboardOpen);
    return keyboardOpen;
  };
  global.setComposerValue = (value, start = null, end = null, { dispatch = true } = {}) => {
    const nextValue = String(value ?? '');
    const { desktop, mobile } = global.getComposerInputs();
    const inputs = [];
    if (desktop) inputs.push(desktop);
    if (mobile && mobile !== desktop) inputs.push(mobile);
    for (const input of inputs) {
      input.value = nextValue;
      if (typeof input.setSelectionRange === 'function') {
        const nextStart = typeof start === 'number' ? start : nextValue.length;
        const nextEnd = typeof end === 'number' ? end : nextStart;
        input.setSelectionRange(nextStart, nextEnd);
      }
    }
    if (dispatch) {
      const dispatchTarget = desktop || mobile;
      if (dispatchTarget) dispatchTarget.dispatchEvent(new Event('input'));
    }
    return nextValue;
  };
  global.handleComposerInputChange = (sourceInput) => {
    if (!sourceInput) return;
    if (typeof syncShellPrompt === 'function') syncShellPrompt();
    if (typeof syncMobileViewportState === 'function') syncMobileViewportState();
    const value = sourceInput.value;
    const start = typeof sourceInput.selectionStart === 'number' ? sourceInput.selectionStart : value.length;
    const end = typeof sourceInput.selectionEnd === 'number' ? sourceInput.selectionEnd : value.length;
    global.setComposerValue(value, start, end, { dispatch: false });
    const keepHistoryNav = typeof _suspendCmdHistoryNavReset !== 'undefined' && _suspendCmdHistoryNavReset;
    if (keepHistoryNav) _suspendCmdHistoryNavReset = false;
    else if (typeof resetCmdHistoryNav === 'function') resetCmdHistoryNav();
    if (value.length > 0 && typeof requestWelcomeSettle === 'function') {
      requestWelcomeSettle(activeTabId);
    }
    if (typeof acSuppressInputOnce !== 'undefined' && acSuppressInputOnce) {
      acSuppressInputOnce = false;
      if (typeof acHide === 'function') acHide();
      return;
    }
    acIndex = -1;
    if (!value.trim()) {
      if (typeof acHide === 'function') acHide();
      return;
    }
    const q = value.toLowerCase();
    acFiltered = (typeof acSuggestions !== 'undefined' && acSuggestions ? acSuggestions : [])
      .filter(s => s.toLowerCase().startsWith(q))
      .slice(0, 12);
    if (typeof acShow === 'function') acShow(acFiltered);
  };
  global.showPanelOverlay = (el) => {
    if (el && el.classList) el.classList.add('open');
  };
  global.hidePanelOverlay = (el) => {
    if (el && el.classList) el.classList.remove('open');
  };
  global.togglePanelOverlay = (el, force = null) => {
    if (!el || !el.classList) return false;
    const next = force === null ? !el.classList.contains('open') : !!force;
    el.classList.toggle('open', next);
    return next;
  };
  global.isPanelOverlayOpen = (el) => !!(el && el.classList && el.classList.contains('open'));
  global.showModalOverlay = (el, display = 'flex') => {
    if (el && el.style) el.style.display = display;
  };
  global.hideModalOverlay = (el) => {
    if (el && el.style) el.style.display = 'none';
  };
  global.toggleModalOverlay = (el, force = null, display = 'flex') => {
    if (!el || !el.style) return false;
    const next = force === null ? el.style.display !== display : !!force;
    el.style.display = next ? display : 'none';
    return next;
  };
  global.isModalOverlayOpen = (el, display = 'flex') => !!(el && el.style && el.style.display === display);
  global.showKillOverlay = () => showModalOverlay(killOverlay, 'flex');
  global.hideKillOverlay = () => hideModalOverlay(killOverlay);
  global.isKillOverlayOpen = () => isModalOverlayOpen(killOverlay, 'flex');
  global.showHistoryPanel = () => showPanelOverlay(historyPanel);
  global.hideHistoryPanel = () => hidePanelOverlay(historyPanel);
  global.isHistoryPanelOpen = () => isPanelOverlayOpen(historyPanel);
  global.showFaqOverlay = () => showPanelOverlay(faqOverlay || null);
  global.hideFaqOverlay = () => hidePanelOverlay(faqOverlay || null);
  global.isFaqOverlayOpen = () => isPanelOverlayOpen(faqOverlay || null);
  global.showOptionsOverlay = () => showPanelOverlay(optionsOverlay || null);
  global.hideOptionsOverlay = () => hidePanelOverlay(optionsOverlay || null);
  global.isOptionsOverlayOpen = () => isPanelOverlayOpen(optionsOverlay || null);
  global.showHistoryDeleteOverlay = () => showModalOverlay(histDelOverlay, 'flex');
  global.hideHistoryDeleteOverlay = () => hideModalOverlay(histDelOverlay);
  global.isHistoryDeleteOverlayOpen = () => isModalOverlayOpen(histDelOverlay, 'flex');
  global.showHistoryLoadOverlay = () => {
    if (historyLoadOverlay && historyLoadOverlay.classList) historyLoadOverlay.classList.add('open');
    if (historyLoadOverlay) historyLoadOverlay.setAttribute('aria-hidden', 'false');
  };
  global.hideHistoryLoadOverlay = () => {
    if (historyLoadOverlay && historyLoadOverlay.classList) historyLoadOverlay.classList.remove('open');
    if (historyLoadOverlay) historyLoadOverlay.setAttribute('aria-hidden', 'true');
  };
  global.isHistoryLoadOverlayOpen = () => !!(historyLoadOverlay && historyLoadOverlay.classList && historyLoadOverlay.classList.contains('open'));
  global.showHistoryDeleteNonfav = () => {
    const btn = typeof histDelNonfavBtn !== 'undefined' ? histDelNonfavBtn : null;
    if (btn && btn.style) btn.style.display = 'inline-block';
  };
  global.hideHistoryDeleteNonfav = () => {
    const btn = typeof histDelNonfavBtn !== 'undefined' ? histDelNonfavBtn : null;
    if (btn && btn.style) btn.style.display = 'none';
  };
  global.showSearchBar = () => {
    if (searchBar && searchBar.style) searchBar.style.display = 'flex';
  };
  global.hideSearchBar = () => {
    if (searchBar && searchBar.style) searchBar.style.display = 'none';
  };
  global.isSearchBarOpen = () => !!(searchBar && searchBar.style && searchBar.style.display !== 'none');
  global.showHistoryRow = () => {
    if (histRow && histRow.style) histRow.style.display = 'flex';
  };
  global.hideHistoryRow = () => {
    if (histRow && histRow.style) histRow.style.display = 'none';
  };
  global.isHistoryRowVisible = () => !!(histRow && histRow.style && histRow.style.display !== 'none');
  global.showRunTimer = () => {
    if (runTimer && runTimer.style) runTimer.style.display = 'inline';
  };
  global.hideRunTimer = () => {
    if (runTimer && runTimer.style) runTimer.style.display = 'none';
    if (runTimer) runTimer.textContent = '';
  };
  global.isRunTimerVisible = () => !!(runTimer && runTimer.style && runTimer.style.display !== 'none');
  global.setRunButtonDisabled = (disabled) => {
    const next = !!disabled;
    if (runBtn) runBtn.disabled = next;
    if (typeof mobileRunBtn !== 'undefined' && mobileRunBtn) mobileRunBtn.disabled = next;
  };
  global.isRunButtonDisabled = () => !!((runBtn && runBtn.disabled) || (typeof mobileRunBtn !== 'undefined' && mobileRunBtn && mobileRunBtn.disabled));
  global.showTabKillBtn = (tabId) => {
    const btn = (typeof tabPanels !== 'undefined' && tabPanels) ? tabPanels.querySelector(`.tab-kill-btn[data-tab="${tabId}"]`) : null;
    if (btn && btn.style) btn.style.display = 'inline-block';
  };
  global.hideTabKillBtn = (tabId) => {
    const btn = (typeof tabPanels !== 'undefined' && tabPanels) ? tabPanels.querySelector(`.tab-kill-btn[data-tab="${tabId}"]`) : null;
    if (btn && btn.style) btn.style.display = 'none';
  };
  global.showMobileMenu = () => {
    const mobileMenu = getMobileMenuEl();
    if (mobileMenu && mobileMenu.classList) mobileMenu.classList.add('open');
  };
  global.hideMobileMenu = () => {
    const mobileMenu = getMobileMenuEl();
    if (mobileMenu && mobileMenu.classList) mobileMenu.classList.remove('open');
  };
  global.isMobileMenuOpen = () => {
    const mobileMenu = getMobileMenuEl();
    return !!(mobileMenu && mobileMenu.classList && mobileMenu.classList.contains('open'));
  };
  global.showMotdWrap = () => {
    if (typeof motdWrap !== 'undefined' && motdWrap && motdWrap.style) motdWrap.style.display = 'block';
  };
  global.hideMotdWrap = () => {
    if (typeof motdWrap !== 'undefined' && motdWrap && motdWrap.style) motdWrap.style.display = 'none';
  };
  global.isMotdWrapVisible = () => !!(typeof motdWrap !== 'undefined' && motdWrap && motdWrap.style && motdWrap.style.display !== 'none');
  global.showAcDropdown = () => {
    if (acDropdown && acDropdown.style) acDropdown.style.display = 'block';
  };
  global.hideAcDropdown = () => {
    if (acDropdown && acDropdown.style) acDropdown.style.display = 'none';
  };
  global.isAcDropdownOpen = () => !!(acDropdown && acDropdown.style && acDropdown.style.display !== 'none');
  global.setVisibilityState = (el, hidden, ariaHidden = null) => {
    if (!el) return;
    el.hidden = !!hidden;
    if (typeof el.setAttribute === 'function') {
      if (ariaHidden === null || typeof ariaHidden === 'undefined') {
        if (typeof el.removeAttribute === 'function') el.removeAttribute('aria-hidden');
      } else {
        el.setAttribute('aria-hidden', String(ariaHidden));
      }
    }
  };
  global.setDisplayState = (el, visible, display = 'block') => {
    if (!el || !el.style) return;
    el.style.display = visible ? display : 'none';
  };
})(globalThis);
