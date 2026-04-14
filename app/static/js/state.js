// ── Shared UI state ──
// The browser scripts still read/write these names directly, but the actual
// storage lives here so the app can move away from prompt-specific globals in
// a controlled way without changing every module at once.
(function initSharedState(global) {
  const defaults = {
    tabs: [],
    activeTabId: null,
    acSuggestions: [],
    acContextRegistry: {},
    acSpecialCommands: [],
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
    _welcomePromptAfterSettle: false,
    _welcomeBootPending: true,
    _composerValue: '',
    _composerSelectionStart: 0,
    _composerSelectionEnd: 0,
    _composerActiveInput: 'desktop',
    _mobileKeyboardOffsetBaseline: null,
    _mobileViewportClosedHeight: null,
    _mobileKeyboardLastOpenOffset: 0,
    timerInterval: null,
    timerStart: null,
    pendingKillTabId: null,
  };
  const state = global.APP_STATE || (global.APP_STATE = {});
  Object.assign(state, defaults);

  const bindings = [
    'tabs',
    'activeTabId',
    'acSuggestions',
    'acContextRegistry',
    'acSpecialCommands',
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
    '_welcomePromptAfterSettle',
    '_welcomeBootPending',
    '_composerValue',
    '_composerSelectionStart',
    '_composerSelectionEnd',
    '_composerActiveInput',
    '_mobileKeyboardOffsetBaseline',
    '_mobileViewportClosedHeight',
    '_mobileKeyboardLastOpenOffset',
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
  global.getComposerState = () => ({
    value: state._composerValue,
    selectionStart: state._composerSelectionStart,
    selectionEnd: state._composerSelectionEnd,
    activeInput: state._composerActiveInput,
  });
  global.setComposerState = (next = {}) => {
    if (Object.prototype.hasOwnProperty.call(next, 'value')) {
      state._composerValue = String(next.value ?? '');
    }
    if (Object.prototype.hasOwnProperty.call(next, 'selectionStart')) {
      state._composerSelectionStart = Math.max(0, Number(next.selectionStart) || 0);
    }
    if (Object.prototype.hasOwnProperty.call(next, 'selectionEnd')) {
      state._composerSelectionEnd = Math.max(0, Number(next.selectionEnd) || 0);
    }
    if (Object.prototype.hasOwnProperty.call(next, 'activeInput')) {
      state._composerActiveInput = next.activeInput === 'mobile' ? 'mobile' : 'desktop';
    }
    return global.getComposerState();
  };
  global.resetComposerState = () => {
    state._composerValue = defaults._composerValue;
    state._composerSelectionStart = defaults._composerSelectionStart;
    state._composerSelectionEnd = defaults._composerSelectionEnd;
    state._composerActiveInput = defaults._composerActiveInput;
    return global.getComposerState();
  };
  global.APP_STATE_API = {
    getState: () => state,
    reset: () => Object.assign(state, defaults),
    getTabs: () => state.tabs,
    setTabs: (v) => { state.tabs = v; },
    getActiveTabId: () => state.activeTabId,
    setActiveTabId: (v) => { state.activeTabId = v; },
    getActiveTab: () => state.tabs.find(t => t.id === state.activeTabId),
    getTab: (id) => state.tabs.find(t => t.id === id),
    getComposerState: () => global.getComposerState(),
    setComposerState: (next) => global.setComposerState(next),
    resetComposerState: () => global.resetComposerState(),
  };

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

})(globalThis);
