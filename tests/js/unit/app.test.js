import { MemoryStorage, fromDomScripts } from './helpers/extract.js'

async function loadAppFns({
  theme = null,
  apiFetch: apiFetchOverride = null,
  doKill: doKillOverride = vi.fn(),
  pendingKillTabId = null,
  requestWelcomeSettle: requestWelcomeSettleOverride = vi.fn(),
} = {}) {
  document.body.className = ''
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

  const apiFetch = apiFetchOverride || vi.fn((url) => {
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

  const runSearch = vi.fn()
  const clearSearch = vi.fn()
  const navigateSearch = vi.fn()
  const logClientError = vi.fn()
  const cmdInput = document.getElementById('cmd')
  cmdInput.focus = vi.fn()

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
    cmdInput,
    runBtn: document.getElementById('run-btn'),
    searchBar: document.getElementById('search-bar'),
    searchInput: document.getElementById('search-input'),
    searchCaseBtn: document.getElementById('search-case-btn'),
    searchRegexBtn: document.getElementById('search-regex-btn'),
    historyPanel: document.getElementById('history-panel'),
    runSearch,
    clearSearch,
    refreshHistoryPanel: () => {},
    navigateSearch,
    searchCaseSensitive: false,
    searchRegexMode: false,
    confirmHistAction: vi.fn(),
    executeHistAction: vi.fn(),
    histDelOverlay: document.getElementById('hist-del-overlay'),
    killOverlay: document.getElementById('kill-overlay'),
    pendingHistAction: null,
    pendingKillTabId,
    acHide: () => {},
    acSuggestions: [],
    acFiltered: [],
    acIndex: -1,
    acShow: () => {},
    acAccept: () => {},
    resetCmdHistoryNav: () => {},
    navigateCmdHistory: () => false,
    logClientError,
    tabs: [],
    activeTabId: 'tab-1',
    requestWelcomeSettle: requestWelcomeSettleOverride,
    runCommand: () => {},
    doKill: doKillOverride,
    Event,
    setTimeout: (fn) => {
      fn()
      return 0
    },
  }, `{
    _setTsMode,
    confirmHistAction,
    executeHistAction,
    doKill,
  }`)

  await Promise.resolve()
  await Promise.resolve()

  return { ...fns, storage, apiFetch, runSearch, clearSearch, navigateSearch, cmdInput, requestWelcomeSettle: requestWelcomeSettleOverride, logClientError }
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

  it('bootstraps cleanly when config and allowed-commands fetches fail', async () => {
    const apiFetch = vi.fn((url) => {
      if (url === '/config' || url === '/allowed-commands' || url === '/autocomplete') {
        return Promise.reject(new Error('network down'))
      }
      if (url === '/faq') {
        return Promise.resolve({ json: () => Promise.resolve({ items: [] }) })
      }
      return Promise.resolve({ json: () => Promise.resolve({}) })
    })

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

    const { storage, logClientError } = await loadAppFns({ apiFetch })
    await Promise.resolve()
    await Promise.resolve()

    expect(apiFetch).toHaveBeenCalledWith('/config')
    expect(apiFetch).toHaveBeenCalledWith('/allowed-commands')
    expect(apiFetch).toHaveBeenCalledWith('/autocomplete')
    expect(logClientError).toHaveBeenCalledWith('failed to load /config', expect.any(Error))
    expect(logClientError).toHaveBeenCalledWith('failed to load /allowed-commands', expect.any(Error))
    expect(logClientError).toHaveBeenCalledWith('failed to load /autocomplete', expect.any(Error))
    expect(document.body.classList.contains('light')).toBe(false)
    expect(storage.getItem('theme')).toBeNull()
  })

  it('settles the welcome intro immediately when the user types into the active welcome tab', async () => {
    const requestWelcomeSettle = vi.fn()
    const { cmdInput } = await loadAppFns({ requestWelcomeSettle })

    cmdInput.value = 'dig '
    cmdInput.dispatchEvent(new Event('input', { bubbles: true }))

    expect(requestWelcomeSettle).toHaveBeenCalledWith('tab-1')
  })

  it('wires the history delete modal buttons and backdrop correctly', async () => {
    const { confirmHistAction, executeHistAction } = await loadAppFns()
    const histDelOverlay = document.getElementById('hist-del-overlay')

    confirmHistAction.mockClear()
    executeHistAction.mockClear()

    document.getElementById('hist-clear-all-btn').click()
    expect(confirmHistAction).toHaveBeenCalledWith('clear')

    histDelOverlay.style.display = 'flex'
    document.getElementById('hist-del-cancel').click()
    expect(histDelOverlay.style.display).toBe('none')

    histDelOverlay.style.display = 'flex'
    document.getElementById('hist-del-nonfav').click()
    expect(histDelOverlay.style.display).toBe('none')
    expect(executeHistAction).toHaveBeenCalledWith('clear-nonfav')

    histDelOverlay.style.display = 'flex'
    document.getElementById('hist-del-confirm').click()
    expect(histDelOverlay.style.display).toBe('none')
    expect(executeHistAction).toHaveBeenCalled()

    histDelOverlay.style.display = 'flex'
    histDelOverlay.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(histDelOverlay.style.display).toBe('none')
  })

  it('wires the kill modal buttons and backdrop correctly', async () => {
    await loadAppFns()
    const killOverlay = document.getElementById('kill-overlay')

    killOverlay.style.display = 'flex'
    document.getElementById('kill-cancel').click()
    expect(killOverlay.style.display).toBe('none')

    const doKill = vi.fn()
    await loadAppFns({ doKill, pendingKillTabId: 'tab-1' })
    const killOverlay2 = document.getElementById('kill-overlay')

    killOverlay2.style.display = 'flex'
    document.getElementById('kill-confirm').click()
    expect(doKill).toHaveBeenCalledWith('tab-1')
    expect(killOverlay2.style.display).toBe('none')

    killOverlay2.style.display = 'flex'
    killOverlay2.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(killOverlay2.style.display).toBe('none')
  })

  it('wires search controls and Escape dismissal correctly', async () => {
    const { runSearch, clearSearch, navigateSearch, cmdInput } = await loadAppFns()
    const searchBar = document.getElementById('search-bar')
    const searchInput = document.getElementById('search-input')

    searchBar.style.display = 'none'
    document.getElementById('search-toggle-btn').click()
    expect(searchBar.style.display).toBe('flex')
    expect(runSearch).toHaveBeenCalledTimes(1)

    document.getElementById('search-prev').click()
    document.getElementById('search-next').click()
    expect(navigateSearch).toHaveBeenCalledWith(-1)
    expect(navigateSearch).toHaveBeenCalledWith(1)

    searchBar.style.display = 'flex'
    searchInput.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(searchBar.style.display).toBe('none')
    expect(clearSearch).toHaveBeenCalled()
    expect(cmdInput.focus).toHaveBeenCalled()

    searchBar.style.display = 'none'
    document.getElementById('search-toggle-btn').click()
    document.getElementById('search-toggle-btn').click()
    expect(clearSearch).toHaveBeenCalledTimes(3)
    expect(searchBar.style.display).toBe('none')
  })

  it('opens and closes the FAQ overlay through the wired controls', async () => {
    await loadAppFns()
    const faqOverlay = document.getElementById('faq-overlay')

    document.getElementById('faq-btn').click()
    expect(faqOverlay.classList.contains('open')).toBe(true)

    faqOverlay.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(faqOverlay.classList.contains('open')).toBe(false)

    document.getElementById('faq-btn').click()
    document.querySelector('.faq-close').click()
    expect(faqOverlay.classList.contains('open')).toBe(false)
  })
})
