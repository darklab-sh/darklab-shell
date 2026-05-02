import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../../..')
const SHELL_CHROME_SRC = readFileSync(resolve(REPO_ROOT, 'app/static/js/shell_chrome.js'), 'utf8')

function tick() {
  return new Promise(resolve => setTimeout(resolve, 0))
}

function loadShellChrome({ fetch, preferences = {}, openRunMonitor = vi.fn(() => Promise.resolve(true)) } = {}) {
  document.body.innerHTML = `
    <aside id="rail">
      <button id="rail-collapse-btn"></button>
      <div id="rail-resize-handle"></div>
      <div id="rail-split-area">
        <section id="rail-section-recent">
          <button id="rail-recent-header"></button>
          <div id="rail-recent-list"></div>
          <span id="rail-recent-count"></span>
        </section>
        <div id="rail-splitter"></div>
        <section id="rail-section-workflows">
          <button id="rail-workflows-header"></button>
          <div id="rail-workflows-list"></div>
          <span id="rail-workflows-count"></span>
        </section>
      </div>
      <nav id="rail-nav"></nav>
    </aside>
    <footer id="hud">
      <button id="hud-status-cell"></button>
      <span id="hud-last-exit"></span>
      <span id="hud-tabs"></span>
      <span id="hud-latency"></span>
      <span id="hud-session"></span>
      <span id="hud-uptime"></span>
      <span id="hud-clock"></span>
      <span id="hud-db"></span>
      <span id="hud-redis"></span>
      <div id="hud-actions"></div>
    </footer>
  `

  const intervalCallbacks = []
  const global = {
    document,
    window,
    tabs: [],
    recentPreviewHistory: [],
    renderHudClock: null,
    toggleRailCollapsed: null,
    openRunMonitor,
  }

  new Function(
    'global',
    'document',
    'window',
    'performance',
    'fetch',
    'localStorage',
    'setInterval',
    'clearInterval',
    'getPreference',
    'setPreferenceCookie',
    'bindDisclosure',
    'bindPressable',
    'bindOutsideClickClose',
    'onUiEvent',
    'getActiveTabId',
    'getTab',
    'maskSessionToken',
    'refocusComposerAfterAction',
    'confirmKill',
    'permalinkTab',
    'copyTab',
    'saveTab',
    'exportTabHtml',
    'exportTabPdf',
    'cancelWelcome',
    'clearTab',
    'renderWorkflowItems',
    'openWorkflows',
    'showWorkflowsOverlay',
    'openRunMonitor',
    `
      const globalThis = global;
      ${SHELL_CHROME_SRC}
    `,
  )(
    global,
    document,
    window,
    performance,
    fetch || vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ uptime: 1, db: 'ok', redis: 'ok' }),
    }),
    localStorage,
    (fn) => {
      intervalCallbacks.push(fn)
      return 1
    },
    () => {},
    name => preferences[name] || '',
    (name, value) => { preferences[name] = String(value) },
    (el, options) => {
      let open = !!options.initialOpen
      el.setAttribute('aria-expanded', open ? 'true' : 'false')
      el.addEventListener('click', () => {
        open = !open
        el.setAttribute('aria-expanded', open ? 'true' : 'false')
        options.onToggle?.(open)
      })
    },
    (el, options) => el.addEventListener('click', options.onActivate),
    () => {},
    () => {},
    () => 'tab-1',
    () => null,
    token => token,
    () => {},
    () => {},
    () => {},
    () => {},
    () => {},
    () => {},
    () => {},
    () => {},
    () => {},
    () => {},
    () => {},
    openRunMonitor,
  )

  return {
    runPoll: () => intervalCallbacks[0](),
    db: document.getElementById('hud-db'),
    redis: document.getElementById('hud-redis'),
    railSplitArea: document.getElementById('rail-split-area'),
    railSplitter: document.getElementById('rail-splitter'),
    railWorkflowsHeader: document.getElementById('rail-workflows-header'),
    railSectionWorkflows: document.getElementById('rail-section-workflows'),
    preferences,
    openRunMonitor,
  }
}

describe('shell chrome rail sections', () => {
  it('opens Status Monitor from the desktop rail nav item', () => {
    const openRunMonitor = vi.fn(() => Promise.resolve(true))
    const shell = loadShellChrome({ openRunMonitor })
    const nav = document.getElementById('rail-nav')
    nav.innerHTML = '<button data-action="run-monitor" type="button"></button>'

    nav.querySelector('[data-action="run-monitor"]').click()

    expect(shell.openRunMonitor).toHaveBeenCalledWith({ source: 'rail' })
  })

  it('keeps the default split when workflows is closed and reopened before resizing', async () => {
    const shell = loadShellChrome()

    expect(shell.railSplitArea.classList.contains('recent-fixed')).toBe(false)
    expect(shell.railSplitArea.style.getPropertyValue('--recent-h')).toBe('')

    shell.railWorkflowsHeader.click()
    expect(shell.railSectionWorkflows.classList.contains('closed')).toBe(true)

    shell.railWorkflowsHeader.click()
    await tick()

    expect(shell.railSectionWorkflows.classList.contains('closed')).toBe(false)
    expect(shell.railSplitArea.classList.contains('recent-fixed')).toBe(false)
    expect(shell.railSplitArea.style.getPropertyValue('--recent-h')).toBe('')
  })

  it('restores the last split height when workflows is closed and reopened', async () => {
    const shell = loadShellChrome()
    Object.defineProperty(shell.railSplitArea, 'getBoundingClientRect', {
      configurable: true,
      value: () => ({ top: 0, height: 420 }),
    })

    shell.railSplitter.dispatchEvent(new MouseEvent('mousedown', { clientY: 0, bubbles: true }))
    window.dispatchEvent(new MouseEvent('mousemove', { clientY: 170, bubbles: true }))
    window.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))

    expect(shell.railSplitArea.style.getPropertyValue('--recent-h')).toBe('170px')

    shell.railWorkflowsHeader.click()
    expect(shell.railSectionWorkflows.classList.contains('closed')).toBe(true)

    shell.railWorkflowsHeader.click()
    expect(shell.railSectionWorkflows.classList.contains('closed')).toBe(false)
    expect(shell.railSplitArea.classList.contains('recent-fixed')).toBe(true)
    expect(shell.railSplitArea.style.getPropertyValue('--recent-h')).toBe('170px')
  })
})

describe('shell chrome HUD status', () => {
  it('marks Redis offline when the status poll cannot reach the server', async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ uptime: 1, db: 'ok', redis: 'ok' }),
      })
      .mockRejectedValueOnce(new Error('server down'))

    const hud = loadShellChrome({ fetch })
    await tick()

    expect(hud.redis.textContent).toBe('ONLINE')
    expect(hud.db.textContent).toBe('ONLINE')

    await hud.runPoll()

    expect(hud.db.textContent).toBe('OFFLINE')
    expect(hud.redis.textContent).toBe('OFFLINE')
  })

  it('keeps Redis as N/A on a failed poll when Redis was not configured', async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce({
        ok: true,
        json: () => Promise.resolve({ uptime: 1, db: 'ok', redis: 'none' }),
      })
      .mockRejectedValueOnce(new Error('server down'))

    const hud = loadShellChrome({ fetch })
    await tick()

    expect(hud.redis.textContent).toBe('N/A')

    await hud.runPoll()

    expect(hud.db.textContent).toBe('OFFLINE')
    expect(hud.redis.textContent).toBe('N/A')
  })
})
