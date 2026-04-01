// ── Shared DOM references ──
// Declared here once so all subsequent modules can reference them as globals.
// All elements exist in the DOM by the time these scripts are parsed (scripts
// load at the end of <body> after all HTML is rendered).
const cmdInput    = document.getElementById('cmd');
const runBtn      = document.getElementById('run-btn');
const status      = document.getElementById('status');
const histRow     = document.getElementById('history-row');
const tabsBar     = document.getElementById('tabs-bar');
const tabPanels   = document.getElementById('tab-panels');
const searchBar   = document.getElementById('search-bar');
const searchInput = document.getElementById('search-input');
const searchCount = document.getElementById('search-count');
const historyPanel = document.getElementById('history-panel');
const historyList  = document.getElementById('history-list');
const acDropdown   = document.getElementById('ac-dropdown');
const killOverlay  = document.getElementById('kill-overlay');
const histDelOverlay = document.getElementById('hist-del-overlay');
const runTimer     = document.getElementById('run-timer');
