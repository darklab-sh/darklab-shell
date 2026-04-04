import { MemoryStorage, fromDomScripts } from './helpers/extract.js'

async function loadAppFns({ theme = null } = {}) {
  document.body.innerHTML = `
    <header><h1></h1></header>
    <button id="ts-btn"></button>
    <button id="theme-btn"></button>
    <button id="faq-btn"></button>
    <button id="hamburger-btn"></button>
    <button id="new-tab-btn"></button>
    <button id="search-toggle-btn"></button>
    <button id="run-btn"></button>
    <button id="search-prev"></button>
    <button id="search-next"></button>
    <button id="hist-btn"></button>
    <button id="history-close"></button>
    <button id="hist-clear-all-btn"></button>
    <button id="hist-del-cancel"></button>
    <button id="hist-del-nonfav"></button>
    <button id="hist-del-confirm"></button>
    <button id="kill-cancel"></button>
    <button id="kill-confirm"></button>
    <div id="version-label"></div>
    <div id="motd"></div>
    <div id="motd-wrap"></div>
    <div id="faq-limits-text"></div>
    <div id="faq-allowed-text"></div>
    <div id="mobile-menu">
      <button data-action="ts"></button>
      <button data-action="search"></button>
      <button data-action="history"></button>
      <button data-action="theme"></button>
      <button data-action="faq"></button>
    </div>
    <div id="faq-overlay"></div>
    <button class="faq-close"></button>
    <div class="faq-body"></div>
    <input id="cmd" />
    <div id="history-panel"></div>
    <div id="history-list"></div>
    <div id="kill-overlay"></div>
    <div id="hist-del-overlay"></div>
    <div id="search-bar"></div>
    <input id="search-input" />
    <span id="search-count"></span>
    <button id="search-case-btn"></button>
    <button id="search-regex-btn"></button>
    <div class="prompt-wrap"></div>
  `

  const storage = new MemoryStorage()
  if (theme !== null) storage.setItem('theme', theme)

  const apiFetch = vi.fn((url) => {
    if (url === '/config') {
      return Promise.resolve({
        json: () => Promise.resolve({
          app_name: 'shell.darklab.sh',
          version: '1.2',
          default_theme: 'dark',
          motd: '',
          command_timeout_seconds: 0,
          max_output_lines: 0,
          permalink_retention_days: 0,
        }),
      })
    }
    if (url === '/allowed-commands') {
      return Promise.resolve({ json: () => Promise.resolve({ restricted: false, commands: [], groups: [] }) })
    }
    if (url === '/faq') {
      return Promise.resolve({ json: () => Promise.resolve({ items: [] }) })
    }
    return Promise.resolve({ json: () => Promise.resolve({}) })
  })

  const fns = fromDomScripts([
    'app/static/js/app.js',
  ], {
    document,
    localStorage: storage,
    apiFetch,
    APP_CONFIG: {},
    tsMode: 'off',
    renderMotd: (text) => text,
    updateNewTabBtn: () => {},
    createTab: () => 'tab-1',
    runWelcome: () => {},
    closeFaq: () => {},
    openFaq: () => {},
    cmdInput: document.getElementById('cmd'),
    runBtn: document.getElementById('run-btn'),
    searchBar: document.getElementById('search-bar'),
    searchInput: document.getElementById('search-input'),
    searchCaseBtn: document.getElementById('search-case-btn'),
    searchRegexBtn: document.getElementById('search-regex-btn'),
    historyPanel: document.getElementById('history-panel'),
    runSearch: () => {},
    clearSearch: () => {},
    refreshHistoryPanel: () => {},
    navigateSearch: () => {},
    searchCaseSensitive: false,
    searchRegexMode: false,
    confirmHistAction: () => {},
    executeHistAction: () => {},
    histDelOverlay: document.getElementById('hist-del-overlay'),
    killOverlay: document.getElementById('kill-overlay'),
    pendingHistAction: null,
    pendingKillTabId: null,
    acHide: () => {},
    acSuggestions: [],
    acFiltered: [],
    acIndex: -1,
    acShow: () => {},
    acAccept: () => {},
    tabs: [],
    runCommand: () => {},
    Event,
    setTimeout: (fn) => {
      fn()
      return 0
    },
  }, `{
    _setTsMode,
  }`)

  await Promise.resolve()
  await Promise.resolve()

  return { ...fns, storage, apiFetch }
}

describe('app helpers', () => {
  it('applies the saved light theme at startup', async () => {
    await loadAppFns({ theme: 'light' })

    expect(document.body.classList.contains('light')).toBe(true)
  })

  it('_setTsMode updates body classes and button labels', async () => {
    const { _setTsMode } = await loadAppFns()

    _setTsMode('elapsed')

    expect(document.body.classList.contains('ts-elapsed')).toBe(true)
    expect(document.body.classList.contains('ts-clock')).toBe(false)
    expect(document.getElementById('ts-btn').textContent).toBe('timestamps: elapsed')
    expect(document.querySelector('#mobile-menu [data-action="ts"]').textContent).toBe('timestamps: elapsed')
  })

  it('_setTsMode marks the timestamps button inactive in off mode', async () => {
    const { _setTsMode } = await loadAppFns()
    const tsBtn = document.getElementById('ts-btn')

    _setTsMode('off')

    expect(tsBtn.classList.contains('active')).toBe(false)
    expect(tsBtn.textContent).toBe('timestamps: off')
  })
})
