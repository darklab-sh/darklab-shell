// ── Shared UI state ──
// Shared storage lives here; modules should use the explicit API below instead
// of top-level window state names.
const APP_STATE_API = (function initSharedState(global) {
  if (global?.APP_STATE_API && typeof global.APP_STATE_API.getState === 'function') {
    return global.APP_STATE_API;
  }
  const defaults = {
    tabs: [],
    activeTabId: null,
    acSuggestions: [],
    acContextRegistry: {},
    acWordlists: [],
    acSpecialCommands: [],
    acBuiltinCommandRoots: [],
    sessionVariables: [],
    acFiltered: [],
    acIndex: -1,
    acSuppressInputOnce: false,
    searchMatches: [],
    searchMatchIdx: -1,
    searchCaseSensitive: false,
    searchRegexMode: false,
    searchScope: 'text',
    searchDiscoverabilityPrompted: false,
    searchSignalCounts: null,
    cmdHistory: [],
    recentPreviewHistory: [],
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
  const state = (global.APP_STATE && typeof global.APP_STATE === 'object')
    ? global.APP_STATE
    : {};
  const cloneDefaultValue = (value) => {
    if (Array.isArray(value)) return value.slice();
    if (value && typeof value === 'object') return { ...value };
    return value;
  };
  Object.entries(defaults).forEach(([key, value]) => {
    if (!Object.prototype.hasOwnProperty.call(state, key)) state[key] = cloneDefaultValue(value);
  });

  const getAppState = () => state;
  const getComposerState = () => ({
    value: state._composerValue,
    selectionStart: state._composerSelectionStart,
    selectionEnd: state._composerSelectionEnd,
    activeInput: state._composerActiveInput,
  });
  const setComposerState = (next = {}) => {
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
    return getComposerState();
  };
  const resetComposerState = () => {
    state._composerValue = defaults._composerValue;
    state._composerSelectionStart = defaults._composerSelectionStart;
    state._composerSelectionEnd = defaults._composerSelectionEnd;
    state._composerActiveInput = defaults._composerActiveInput;
    return getComposerState();
  };
  const resetAppState = () => {
    Object.entries(defaults).forEach(([key, value]) => {
      state[key] = cloneDefaultValue(value);
    });
    return state;
  };
  const getTabs = () => state.tabs;
  const setTabs = (v) => { state.tabs = v; };
  const getActiveTabId = () => state.activeTabId;
  const setActiveTabId = (v) => { state.activeTabId = v; };
  const getActiveTab = () => state.tabs.find(t => t.id === state.activeTabId);
  const getTab = (id) => state.tabs.find(t => t.id === id);
  const getAutocompleteState = () => ({
    filtered: state.acFiltered,
    index: state.acIndex,
    suppressInputOnce: state.acSuppressInputOnce,
  });
  const setAutocompleteState = (next = {}) => {
    if (Object.prototype.hasOwnProperty.call(next, 'filtered')) {
      state.acFiltered = Array.isArray(next.filtered) ? next.filtered : [];
    }
    if (Object.prototype.hasOwnProperty.call(next, 'index')) {
      state.acIndex = Number.isFinite(Number(next.index)) ? Number(next.index) : -1;
    }
    if (Object.prototype.hasOwnProperty.call(next, 'suppressInputOnce')) {
      state.acSuppressInputOnce = !!next.suppressInputOnce;
    }
    return getAutocompleteState();
  };
  const getWelcomeState = () => ({
    active: state._welcomeActive,
    done: state._welcomeDone,
    tabId: state._welcomeTabId,
    settleRequested: state._welcomeSettleRequested,
    promptAfterSettle: state._welcomePromptAfterSettle,
    bootPending: state._welcomeBootPending,
  });
  const setWelcomeState = (next = {}) => {
    if (Object.prototype.hasOwnProperty.call(next, 'active')) {
      state._welcomeActive = !!next.active;
    }
    if (Object.prototype.hasOwnProperty.call(next, 'done')) {
      state._welcomeDone = !!next.done;
    }
    if (Object.prototype.hasOwnProperty.call(next, 'tabId')) {
      state._welcomeTabId = next.tabId == null ? null : String(next.tabId);
    }
    if (Object.prototype.hasOwnProperty.call(next, 'settleRequested')) {
      state._welcomeSettleRequested = !!next.settleRequested;
    }
    if (Object.prototype.hasOwnProperty.call(next, 'promptAfterSettle')) {
      state._welcomePromptAfterSettle = !!next.promptAfterSettle;
    }
    if (Object.prototype.hasOwnProperty.call(next, 'bootPending')) {
      state._welcomeBootPending = !!next.bootPending;
    }
    return getWelcomeState();
  };
  const api = {
    getState: getAppState,
    reset: resetAppState,
    getTabs,
    setTabs,
    getActiveTabId,
    setActiveTabId,
    getActiveTab,
    getTab,
    getComposerState,
    setComposerState,
    resetComposerState,
    getAutocompleteState,
    setAutocompleteState,
    getWelcomeState,
    setWelcomeState,
  };


  // ── Tab accessors ──
  // Use these instead of reading/writing tabs and activeTabId directly.
  // Direct access still works (via the property descriptors above), but these
  // setters make mutation sites explicit and provide a stable boundary for
  // future refactoring.

  // ── UI event helpers ──
  // Keep cross-module state sync explicit: publishers emit document-level
  // CustomEvents and subscribers opt in with add/remove listeners instead of
  // monkey-patching each other's globals after load.
  const emitUiEvent = (name, detail = {}) => {
    if (typeof document === 'undefined' || typeof document.dispatchEvent !== 'function') return false;
    if (typeof document.createEvent === 'function') {
      const event = document.createEvent('CustomEvent');
      event.initCustomEvent(name, false, false, detail);
      document.dispatchEvent(event);
      return true;
    }
    const EventCtor = document.defaultView?.CustomEvent
      || global.CustomEvent
      || (typeof CustomEvent === 'function' ? CustomEvent : null);
    if (!EventCtor) return false;
    document.dispatchEvent(new EventCtor(name, { detail }));
    return true;
  };
  const onUiEvent = (name, handler, options) => {
    if (typeof document === 'undefined' || typeof document.addEventListener !== 'function' || typeof handler !== 'function') {
      return () => {};
    }
    document.addEventListener(name, handler, options);
    return () => document.removeEventListener(name, handler, options);
  };

  if (global) {
    const publicApi = {
      APP_STATE_API: api,
      APP_STATE: state,
      getAppState: api.getState,
      resetAppState: api.reset,
      getTabs: api.getTabs,
      setTabs: api.setTabs,
      getActiveTabId: api.getActiveTabId,
      setActiveTabId: api.setActiveTabId,
      getActiveTab: api.getActiveTab,
      getTab: api.getTab,
      getComposerState: api.getComposerState,
      setComposerState: api.setComposerState,
      resetComposerState: api.resetComposerState,
      getAutocompleteState: api.getAutocompleteState,
      setAutocompleteState: api.setAutocompleteState,
      getWelcomeState: api.getWelcomeState,
      setWelcomeState: api.setWelcomeState,
      emitUiEvent,
      onUiEvent,
    };
    Object.assign(global, publicApi);
    if (typeof window !== 'undefined' && window !== global) {
      Object.assign(window, publicApi);
    }
  }
  return api;
})(globalThis);

const getAppState = (...args) => APP_STATE_API.getState(...args);
const resetAppState = (...args) => APP_STATE_API.reset(...args);
const getTabs = (...args) => APP_STATE_API.getTabs(...args);
const setTabs = (...args) => APP_STATE_API.setTabs(...args);
const getActiveTabId = (...args) => APP_STATE_API.getActiveTabId(...args);
const setActiveTabId = (...args) => APP_STATE_API.setActiveTabId(...args);
const getActiveTab = (...args) => APP_STATE_API.getActiveTab(...args);
const getTab = (...args) => APP_STATE_API.getTab(...args);
const getComposerState = (...args) => APP_STATE_API.getComposerState(...args);
const setComposerState = (...args) => APP_STATE_API.setComposerState(...args);
const resetComposerState = (...args) => APP_STATE_API.resetComposerState(...args);
const getAutocompleteState = (...args) => APP_STATE_API.getAutocompleteState(...args);
const setAutocompleteState = (...args) => APP_STATE_API.setAutocompleteState(...args);
const getWelcomeState = (...args) => APP_STATE_API.getWelcomeState(...args);
const setWelcomeState = (...args) => APP_STATE_API.setWelcomeState(...args);
const emitUiEvent = (...args) => (
  typeof globalThis.emitUiEvent === 'function' ? globalThis.emitUiEvent(...args) : false
);
const onUiEvent = (...args) => (
  typeof globalThis.onUiEvent === 'function' ? globalThis.onUiEvent(...args) : () => {}
);

export {
  APP_STATE_API,
  emitUiEvent,
  getActiveTab,
  getActiveTabId,
  getAutocompleteState,
  getAppState,
  getComposerState,
  getTab,
  getTabs,
  onUiEvent,
  resetAppState,
  resetComposerState,
  setActiveTabId,
  setAutocompleteState,
  setComposerState,
  setTabs,
  getWelcomeState,
  setWelcomeState,
};
