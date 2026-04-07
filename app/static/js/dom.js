// ── Shared utility module ──
// Declared here once so all subsequent modules can reference them as globals.
// All elements exist in the DOM by the time these scripts are parsed at the end of <body>.
const cmdInput    = document.getElementById('cmd');
const runBtn      = document.getElementById('run-btn');
const shellPromptWrap = document.getElementById('shell-prompt-wrap');
const shellPromptLine = document.getElementById('shell-prompt-line');
const shellPromptText = document.getElementById('shell-prompt-text');
const shellPromptCaret = document.getElementById('shell-prompt-caret');
const shellInputRow = document.getElementById('shell-input-row');
const terminalWrap = document.querySelector('.terminal-wrap');
const terminalBar = document.querySelector('.terminal-bar');
const status      = document.getElementById('status');
const histRow     = document.getElementById('history-row');
const tabsBar     = document.getElementById('tabs-bar');
const tabPanels   = document.getElementById('tab-panels');
const mobileShell = document.getElementById('mobile-shell');
const mobileComposerHost = document.getElementById('mobile-composer-host');
const mobileComposerRow = document.getElementById('mobile-composer-row');
const mobileEditBar = document.getElementById('mobile-edit-bar');
const searchBar   = document.getElementById('search-bar');
const searchInput = document.getElementById('search-input');
const searchCount = document.getElementById('search-count');
const historyPanel = document.getElementById('history-panel');
const historyList  = document.getElementById('history-list');
const historyLoadOverlay = document.getElementById('history-load-overlay');
const acDropdown   = document.getElementById('ac-dropdown');
const killOverlay    = document.getElementById('kill-overlay');
const histDelOverlay = document.getElementById('hist-del-overlay');
const runTimer       = document.getElementById('run-timer');
const searchCaseBtn  = document.getElementById('search-case-btn');
const searchRegexBtn = document.getElementById('search-regex-btn');
