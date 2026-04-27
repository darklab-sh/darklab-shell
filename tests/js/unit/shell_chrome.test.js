import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../../..')
const SHELL_CHROME_SRC = readFileSync(resolve(REPO_ROOT, 'app/static/js/shell_chrome.js'), 'utf8')

function tick() {
  return new Promise(resolve => setTimeout(resolve, 0))
}

function loadShellChrome({ fetch }) {
  document.body.innerHTML = `
    <aside id="rail">
      <button id="rail-collapse-btn"></button>
      <div id="rail-resize-handle"></div>
      <div id="rail-split-area"></div>
      <div id="rail-splitter"></div>
      <section id="rail-section-recent"></section>
      <div id="rail-recent-list"></div>
      <span id="rail-recent-count"></span>
      <button id="rail-recent-header"></button>
      <section id="rail-section-workflows"></section>
      <div id="rail-workflows-list"></div>
      <button id="rail-workflows-header"></button>
      <span id="rail-workflows-count"></span>
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
    `
      const globalThis = global;
      ${SHELL_CHROME_SRC}
    `,
  )(
    global,
    document,
    window,
    performance,
    fetch,
    localStorage,
    (fn) => {
      intervalCallbacks.push(fn)
      return 1
    },
    () => {},
    () => '',
    () => {},
    () => {},
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
  )

  return {
    runPoll: () => intervalCallbacks[0](),
    db: document.getElementById('hud-db'),
    redis: document.getElementById('hud-redis'),
  }
}

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
