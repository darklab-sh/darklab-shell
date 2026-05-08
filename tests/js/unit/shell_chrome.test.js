import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../../..')
const SHELL_CHROME_SRC = readFileSync(resolve(REPO_ROOT, 'app/static/js/shell_chrome.js'), 'utf8')

function tick() {
  return new Promise(resolve => setTimeout(resolve, 0))
}

const PRESSABLE_PRIMITIVE_CLASSES = new Set([
  'btn',
  'nav-item',
  'close-btn',
  'toggle-btn',
  'kb-key',
  'dropdown-item',
  'control-row',
  'hud-action-cell',
  'diag-cmd-cell',
  'gesture-handle',
])

function expectProjectPressablesBound(selectors) {
  selectors.forEach((selector) => {
    const controls = Array.from(document.querySelectorAll(selector))
    expect(controls.length, `expected project pressables for ${selector}`).toBeGreaterThan(0)
    controls.forEach((control) => {
      const hasPrimitive = Array.from(control.classList).some(cls => PRESSABLE_PRIMITIVE_CLASSES.has(cls))
      expect(hasPrimitive, `${selector} should use an allowed primitive class`).toBe(true)
      expect(control.dataset.pressableBound, `${selector} should be bound through bindPressable`).toBe('1')
    })
  })
}

function loadShellChrome({
  fetch,
  apiFetch,
  preferences = {},
  openStatusMonitor = vi.fn(() => Promise.resolve(true)),
  restoreHistoryRunIntoTab = vi.fn(() => Promise.resolve('tab-restored')),
  showWorkspaceViewer = vi.fn(),
  showConfirm = vi.fn(() => Promise.resolve('remove')),
  fetchAndRenderHistoryComparison = vi.fn(),
  bindDismissible = null,
  bindPressable = (el, options = {}) => {
    if (el?.dataset) el.dataset.pressableBound = '1'
    if (typeof options.onActivate === 'function') {
      el.addEventListener('click', options.onActivate)
    }
    return { dispose: vi.fn() }
  },
  enhanceAppSelects = vi.fn(),
  syncAppSelect = vi.fn(),
  getProjectAutoLinkExternalRunsPreference = () => preferences.pref_project_auto_link_external_runs || 'on',
  applyProjectAutoLinkExternalRunsPreference = (mode) => { preferences.pref_project_auto_link_external_runs = mode },
} = {}) {
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
      <button id="hud-project-cell" type="button">
        <span id="hud-project"></span>
      </button>
      <span id="hud-uptime"></span>
      <span id="hud-clock"></span>
      <span id="hud-db"></span>
      <span id="hud-redis"></span>
      <div id="hud-actions"></div>
    </footer>
    <div id="project-workspace-overlay" class="u-hidden" aria-hidden="true">
      <div id="project-workspace-modal">
        <button class="project-workspace-close" type="button"></button>
        <p id="project-workspace-subtitle"></p>
        <div id="project-workspace-message" class="u-hidden"></div>
        <form id="project-workspace-create-form">
          <input id="project-workspace-name">
        </form>
        <form id="project-notes-form">
          <textarea id="project-notes-input"></textarea>
          <div id="project-notes-save-status" class="u-hidden">saved</div>
        </form>
        <div id="project-workspace-body"></div>
        <div id="project-explorer-body"></div>
      </div>
      <div id="project-target-editor-overlay" class="u-hidden" aria-hidden="true">
        <div id="project-target-editor-modal">
          <span id="project-target-editor-title"></span>
          <button class="project-target-editor-close" type="button"></button>
          <form id="project-target-create-form">
            <select id="project-target-type">
              <option value="domain">domain</option>
              <option value="host">host</option>
              <option value="ip">ip</option>
              <option value="cidr">cidr</option>
              <option value="url">url</option>
              <option value="port_set">port set</option>
            </select>
            <input id="project-target-value">
            <small id="project-target-value-help"></small>
            <div id="project-target-value-error" class="u-hidden"></div>
            <input id="project-target-label">
            <textarea id="project-target-notes"></textarea>
            <button class="project-target-editor-cancel" type="button"></button>
            <button id="project-target-submit" type="submit"></button>
          </form>
        </div>
      </div>
      <div id="project-package-manifest-overlay" class="u-hidden" aria-hidden="true">
        <div id="project-package-manifest-modal">
          <span id="project-package-manifest-title"></span>
          <button class="project-package-manifest-close" type="button"></button>
          <pre id="project-package-manifest-json"></pre>
        </div>
      </div>
      <div id="project-package-wizard-overlay" class="u-hidden" aria-hidden="true">
        <div id="project-package-wizard-modal">
          <div id="project-package-wizard-body"></div>
        </div>
      </div>
      <div id="project-entity-editor-overlay" class="u-hidden" aria-hidden="true">
        <div id="project-entity-editor-modal">
          <span id="project-entity-editor-title"></span>
          <div id="project-entity-editor-subtitle"></div>
          <button class="project-entity-editor-close" type="button"></button>
          <form id="project-entity-editor-form">
            <input id="project-entity-labels">
            <textarea id="project-entity-note"></textarea>
            <button class="project-entity-editor-cancel" type="button"></button>
            <button id="project-entity-submit" type="submit"></button>
          </form>
        </div>
      </div>
    </div>
  `

  const intervalCallbacks = []
  const global = {
    document,
    window,
    localStorage: {
      getItem: vi.fn(() => ''),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    },
    tabs: [],
    recentPreviewHistory: [],
    renderHudClock: null,
    toggleRailCollapsed: null,
    openStatusMonitor,
    restoreHistoryRunIntoTab,
    showWorkspaceViewer,
    showConfirm,
    fetchAndRenderHistoryComparison,
    bindDismissible,
    enhanceAppSelects,
    syncAppSelect,
  }

  new Function(
    'global',
    'document',
    'window',
    'performance',
    'fetch',
    'apiFetch',
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
    'openStatusMonitor',
    'showConfirm',
    'getProjectAutoLinkExternalRunsPreference',
    'applyProjectAutoLinkExternalRunsPreference',
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
    apiFetch || vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ project: null, projects: [], counts: {} }),
    }),
    window.localStorage,
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
    bindPressable,
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
    () => {},
    openStatusMonitor,
    showConfirm,
    getProjectAutoLinkExternalRunsPreference,
    applyProjectAutoLinkExternalRunsPreference,
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
    openStatusMonitor,
    restoreHistoryRunIntoTab,
    showWorkspaceViewer,
    showConfirm,
    bindDismissible,
    openProjectWorkspace: global.openProjectWorkspace,
    refreshProjectWorkspace: global.refreshProjectWorkspace,
    enhanceAppSelects,
    syncAppSelect,
  }
}

describe('shell chrome rail sections', () => {
  it('opens Status Monitor from the desktop rail nav item', () => {
    const openStatusMonitor = vi.fn(() => Promise.resolve(true))
    const shell = loadShellChrome({ openStatusMonitor })
    const nav = document.getElementById('rail-nav')
    nav.innerHTML = '<button data-action="status-monitor" type="button"></button>'

    nav.querySelector('[data-action="status-monitor"]').click()

    expect(shell.openStatusMonitor).toHaveBeenCalledWith({ source: 'rail' })
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

describe('shell chrome project workspace', () => {
  it('labels only the current active project in the project list', async () => {
    let activeProjectId = 'project-1'
    const projects = [
      { id: 'project-3', name: 'zulu.test', status: 'active' },
      { id: 'project-2', name: 'example.net', status: 'active' },
      { id: 'project-1', name: 'darklab.sh', status: 'active' },
      { id: 'project-4', name: 'alpha.test', status: 'active' },
    ]
    const apiFetch = vi.fn((url, options = {}) => {
      if (url === '/projects/active' && options.method === 'POST') {
        activeProjectId = JSON.parse(options.body).project_id
        const project = projects.find(item => item.id === activeProjectId) || null
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ ok: true, project }),
        })
      }
      if (url === '/projects/active') {
        const project = projects.find(item => item.id === activeProjectId) || null
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ project }),
        })
      }
      if (url === '/projects?include_archived=1') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ projects }),
        })
      }
      if (url.endsWith('/summary')) {
        const projectId = url.split('/')[2]
        const project = projects.find(item => item.id === projectId) || null
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            project,
            counts: { runs: 0, findings: 0, artifacts: 0, packages: 0, targets: 0, notes: 0 },
            runs: [],
            targets: [],
            artifacts: [],
            packages: [],
          }),
        })
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({}),
      })
    })
    const shell = loadShellChrome({ apiFetch })

    await shell.openProjectWorkspace()
    await tick()
    const rowText = projectId => document.querySelector(`[data-project-action="select"][data-project-id="${projectId}"]`)?.textContent || ''
    const orderedProjectIds = () => [...document.querySelectorAll('[data-project-action="select"]')]
      .map(row => row.dataset.projectId)
    expect(rowText('project-1')).toContain('active')
    expect(rowText('project-2')).not.toContain('active')
    expect(orderedProjectIds()).toEqual(['project-1', 'project-4', 'project-2', 'project-3'])

    document.querySelector('[data-project-action="select"][data-project-id="project-2"]').click()
    await tick()
    document.querySelector('[data-project-action="use"][data-project-id="project-2"]').click()
    await tick()
    await tick()

    expect(rowText('project-1')).not.toContain('active')
    expect(rowText('project-2')).toContain('active')
    expect(orderedProjectIds()).toEqual(['project-2', 'project-4', 'project-1', 'project-3'])
  })

  it('opens projects from the active project HUD chip', async () => {
    const apiFetch = vi.fn((url) => {
      if (url === '/projects/active') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ project: { id: 'project-1', name: 'darklab.sh', status: 'active' } }),
        })
      }
      if (url === '/projects?include_archived=1') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ projects: [{ id: 'project-1', name: 'darklab.sh', status: 'active' }] }),
        })
      }
      if (url === '/projects/project-1/summary') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            project: { id: 'project-1', name: 'darklab.sh', status: 'active' },
            counts: { runs: 0, findings: 0, artifacts: 0, packages: 0, targets: 0, notes: 0 },
            runs: [],
            targets: [],
            artifacts: [],
            packages: [],
          }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    loadShellChrome({ apiFetch })

    await tick()
    document.getElementById('hud-project-cell').click()
    await tick()
    await tick()

    expect(document.getElementById('project-workspace-overlay').classList.contains('open')).toBe(true)
    expect(apiFetch).toHaveBeenCalledWith('/projects?include_archived=1', { cache: 'no-store' })
  })

  it('separates current and archived projects when archived projects exist', async () => {
    const projects = [
      { id: 'project-1', name: 'darklab.sh', status: 'active' },
      { id: 'project-2', name: 'old.darklab.sh', status: 'archived' },
      { id: 'project-3', name: 'api.darklab.sh', status: 'active' },
    ]
    const apiFetch = vi.fn((url) => {
      if (url === '/projects/active') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ project: projects[0] }),
        })
      }
      if (url === '/projects?include_archived=1') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ projects }),
        })
      }
      if (url.endsWith('/summary')) {
        const projectId = url.split('/')[2]
        const project = projects.find(item => item.id === projectId) || null
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            project,
            counts: { runs: 0, findings: 0, artifacts: 0, packages: 0, targets: 0, notes: 0 },
            runs: [],
            targets: [],
            artifacts: [],
            packages: [],
          }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const shell = loadShellChrome({ apiFetch })

    await shell.openProjectWorkspace()
    await tick()

    const labels = [...document.querySelectorAll('.project-workspace-section-label')]
      .map(node => node.textContent)
    const orderedProjectIds = [...document.querySelectorAll('[data-project-action="select"]')]
      .map(row => row.dataset.projectId)
    expect(labels).toEqual(['Current', 'Archived'])
    expect(orderedProjectIds).toEqual(['project-1', 'project-3', 'project-2'])
  })

  it('unarchives archived projects without changing the active project', async () => {
    const projects = [
      { id: 'project-1', name: 'darklab.sh', status: 'active' },
      { id: 'project-2', name: 'old.darklab.sh', status: 'archived' },
    ]
    const apiFetch = vi.fn((url, options = {}) => {
      if (url === '/projects/active') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ project: projects[0] }),
        })
      }
      if (url === '/projects?include_archived=1') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ projects }),
        })
      }
      if (url.endsWith('/summary')) {
        const projectId = url.split('/')[2]
        const project = projects.find(item => item.id === projectId) || null
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            project,
            counts: { runs: 0, findings: 0, artifacts: 0, packages: 0, targets: 0, notes: 0 },
            runs: [],
            targets: [],
            artifacts: [],
            packages: [],
          }),
        })
      }
      if (url === '/projects/project-2' && options.method === 'PUT') {
        expect(JSON.parse(options.body)).toEqual({ status: 'active' })
        projects[1] = { ...projects[1], status: 'active' }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ ok: true, project: projects[1] }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const shell = loadShellChrome({ apiFetch })

    await shell.openProjectWorkspace()
    await tick()
    document.querySelector('[data-project-action="select"][data-project-id="project-2"]').click()
    await tick()
    document.querySelector('[data-project-action="unarchive"][data-project-id="project-2"]').click()
    await tick()
    await tick()

    expect(apiFetch).toHaveBeenCalledWith('/projects/project-2', expect.objectContaining({ method: 'PUT' }))
    expect(apiFetch).not.toHaveBeenCalledWith('/projects/active', expect.objectContaining({ method: 'POST' }))
    expect(document.getElementById('project-workspace-message').textContent).toContain('Project unarchived.')
    expect(document.querySelector('[data-project-action="archive"][data-project-id="project-2"]')).not.toBeNull()
  })

  it('deletes a project from the project explorer after confirmation', async () => {
    let projects = [{ id: 'project-1', name: 'darklab.sh', status: 'active' }]
    let activeProject = projects[0]
    const showConfirm = vi.fn(() => Promise.resolve('delete'))
    const apiFetch = vi.fn((url, options = {}) => {
      if (url === '/projects/active') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ project: activeProject }),
        })
      }
      if (url === '/projects?include_archived=1') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ projects }),
        })
      }
      if (url === '/projects/project-1/summary') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            project: projects[0] || null,
            counts: { runs: 0, findings: 0, artifacts: 0, packages: 0, targets: 0, notes: 0 },
            runs: [],
            targets: [],
            artifacts: [],
            packages: [],
          }),
        })
      }
      if (url === '/projects/project-1' && options.method === 'DELETE') {
        projects = []
        activeProject = null
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const shell = loadShellChrome({ apiFetch, showConfirm })

    await shell.openProjectWorkspace()
    await tick()
    document.querySelector('[data-project-action="delete"][data-project-id="project-1"]').click()
    await tick()
    await tick()

    expect(showConfirm).toHaveBeenCalledWith(expect.objectContaining({
      body: expect.objectContaining({ text: 'Delete project: darklab.sh?' }),
      tone: 'danger',
    }))
    expect(apiFetch).toHaveBeenCalledWith('/projects/project-1', expect.objectContaining({ method: 'DELETE' }))
    expect(document.getElementById('project-workspace-body').textContent)
      .toContain('No projects yet')
    expect(document.getElementById('project-workspace-message').textContent).toContain('Project deleted.')
  })

  it('toggles the active project external run capture preference', async () => {
    const apiFetch = vi.fn((url) => {
      if (url === '/projects/active') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ project: { id: 'project-1', name: 'darklab.sh' } }),
        })
      }
      if (url === '/projects?include_archived=1') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ projects: [{ id: 'project-1', name: 'darklab.sh', status: 'active' }] }),
        })
      }
      if (url === '/projects/project-1/summary') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            counts: { runs: 0, findings: 0, artifacts: 0, packages: 0, targets: 0, notes: 0 },
            runs: [],
            targets: [],
            artifacts: [],
            packages: [],
          }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const shell = loadShellChrome({ apiFetch })

    await shell.openProjectWorkspace()
    await tick()

    expect(document.querySelector('[data-project-auto-link-external-runs]')).toBeNull()
    expect(document.getElementById('project-explorer-body').textContent)
      .not.toContain('Add external command runs to the active project')
  })

  it('keeps the target editor dropdown value in sync with the last saved target type', async () => {
    const targets = []
    const apiFetch = vi.fn((url, options = {}) => {
      if (url === '/projects/active') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ project: { id: 'project-1', name: 'darklab.sh' } }),
        })
      }
      if (url === '/projects?include_archived=1') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ projects: [{ id: 'project-1', name: 'darklab.sh', status: 'active' }] }),
        })
      }
      if (url === '/projects/project-1/summary') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            counts: { runs: 0, findings: 0, artifacts: 0, packages: 0, targets: targets.length, notes: 0 },
            runs: [],
            targets,
            artifacts: [],
            packages: [],
          }),
        })
      }
      if (url === '/projects/project-1/targets' && options.method === 'POST') {
        const payload = JSON.parse(options.body)
        const target = { id: `target-${targets.length + 1}`, ...payload }
        targets.push(target)
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ target }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const syncAppSelect = vi.fn()
    const shell = loadShellChrome({ apiFetch, syncAppSelect })

    await shell.openProjectWorkspace()
    await tick()

    document.querySelector('[data-project-action="new-target"]').click()
    await tick()
    const typeSelect = document.getElementById('project-target-type')
    const valueInput = document.getElementById('project-target-value')
    const valueHelp = document.getElementById('project-target-value-help')
    expect(valueInput.placeholder).toBe('target.example.com')
    expect(valueHelp.textContent).toContain('darklab.sh')
    typeSelect.value = 'host'
    typeSelect.dispatchEvent(new Event('change', { bubbles: true }))
    expect(valueInput.placeholder).toBe('host.example.com')
    expect(valueHelp.textContent).toContain('Hostname or IP address')
    valueInput.value = 'api.darklab.sh'
    document.getElementById('project-target-create-form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await tick()
    await tick()
    await tick()

    document.querySelector('[data-project-action="new-target"]').click()
    await tick()

    expect(typeSelect.value).toBe('host')
    expect(syncAppSelect).toHaveBeenCalledWith(typeSelect)
    expect(valueInput.placeholder).toBe('host.example.com')
    expect(valueHelp.textContent).toContain('192.0.2.10')
    typeSelect.value = 'port_set'
    typeSelect.dispatchEvent(new Event('change', { bubbles: true }))
    expect(valueInput.placeholder).toBe('80,443,8000-8080')
    expect(valueHelp.textContent).toContain('8000-8080')
    typeSelect.value = 'host'
    typeSelect.dispatchEvent(new Event('change', { bubbles: true }))
    valueInput.value = 'www.darklab.sh'
    document.getElementById('project-target-create-form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await tick()

    expect(apiFetch).toHaveBeenCalledWith('/projects/project-1/targets', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({
        type: 'host',
        value: 'www.darklab.sh',
        label: '',
        notes: '',
      }),
    }))
  })

  it('validates project target values before saving', async () => {
    const apiFetch = vi.fn((url, options = {}) => {
      if (url === '/projects/active') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ project: { id: 'project-1', name: 'darklab.sh' } }),
        })
      }
      if (url === '/projects?include_archived=1') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ projects: [{ id: 'project-1', name: 'darklab.sh', status: 'active' }] }),
        })
      }
      if (url === '/projects/project-1/summary') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            counts: { runs: 0, findings: 0, artifacts: 0, packages: 0, targets: 0, notes: 0 },
            runs: [],
            targets: [],
            artifacts: [],
            packages: [],
          }),
        })
      }
      if (url === '/projects/project-1/targets' && options.method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ target: { id: 'target-1', ...JSON.parse(options.body) } }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const shell = loadShellChrome({ apiFetch })

    await shell.openProjectWorkspace()
    await tick()
    document.querySelector('[data-project-action="new-target"]').click()
    await tick()

    const typeSelect = document.getElementById('project-target-type')
    const valueInput = document.getElementById('project-target-value')
    const notesInput = document.getElementById('project-target-notes')
    const valueError = document.getElementById('project-target-value-error')
    const form = document.getElementById('project-target-create-form')
    expect(notesInput.maxLength).toBe(2000)

    valueInput.value = 'https://darklab.sh'
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await tick()
    expect(valueInput.getAttribute('aria-invalid')).toBe('true')
    expect(valueError.classList.contains('u-hidden')).toBe(false)
    expect(valueError.textContent).toContain('Use a domain name')
    expect(apiFetch.mock.calls.some(([url, options]) => url === '/projects/project-1/targets' && options?.method === 'POST')).toBe(false)

    valueInput.value = 'darklab.sh'
    valueInput.dispatchEvent(new Event('input', { bubbles: true }))
    expect(valueInput.getAttribute('aria-invalid')).toBe('false')
    expect(valueError.classList.contains('u-hidden')).toBe(true)

    typeSelect.value = 'port_set'
    typeSelect.dispatchEvent(new Event('change', { bubbles: true }))
    valueInput.value = '80,70000'
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await tick()
    expect(valueError.textContent).toContain('Use ports or ranges')
    expect(apiFetch.mock.calls.some(([url, options]) => url === '/projects/project-1/targets' && options?.method === 'POST')).toBe(false)

    valueInput.value = '80,443,8000-8080'
    notesInput.value = 'x'.repeat(2001)
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await tick()
    expect(valueInput.getAttribute('aria-invalid')).toBe('false')
    expect(notesInput.getAttribute('aria-invalid')).toBe('true')
    expect(valueError.textContent).toContain('Target notes must be 2,000 characters or fewer.')
    expect(apiFetch.mock.calls.some(([url, options]) => url === '/projects/project-1/targets' && options?.method === 'POST')).toBe(false)

    notesInput.value = 'Scope notes'
    notesInput.dispatchEvent(new Event('input', { bubbles: true }))
    expect(notesInput.getAttribute('aria-invalid')).toBe('false')
    expect(valueError.classList.contains('u-hidden')).toBe(true)

    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await tick()
    expect(apiFetch).toHaveBeenCalledWith('/projects/project-1/targets', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({
        type: 'port_set',
        value: '80,443,8000-8080',
        label: '',
        notes: 'Scope notes',
      }),
    }))
  })

  it('reloads project findings after linked runs change', async () => {
    let projectRuns = [
      { id: 'old-run', command: 'nuclei https://old.darklab.sh', started: '2026-05-07T00:00:00Z', exit_code: 0, output_line_count: 3, created: '2026-05-07T00:00:10Z' },
    ]
    let projectFindings = [
      {
        id: 'old-finding',
        run_id: 'old-run',
        run_command: 'nuclei https://old.darklab.sh',
        scope: 'http',
        title: 'old finding should not persist',
        raw_line: '[old] https://old.darklab.sh',
        line_number: 1,
        review_state: 'new',
      },
    ]
    const apiFetch = vi.fn((url) => {
      if (url === '/projects/active') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ project: { id: 'project-1', name: 'darklab.sh' } }),
        })
      }
      if (url === '/projects?include_archived=1') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ projects: [{ id: 'project-1', name: 'darklab.sh', status: 'active' }] }),
        })
      }
      if (url === '/projects/project-1/summary') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            counts: { runs: projectRuns.length, findings: projectFindings.length, artifacts: 0, packages: 0, targets: 0, notes: 0 },
            runs: projectRuns,
            targets: [],
            artifacts: [],
            packages: [],
          }),
        })
      }
      if (url === '/projects/project-1/findings') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ findings: projectFindings }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const shell = loadShellChrome({ apiFetch })

    await shell.openProjectWorkspace()
    document.querySelector('[data-project-tab="findings"]').click()
    await tick()
    await tick()
    expect(document.getElementById('project-explorer-body').textContent).toContain('old finding should not persist')

    projectRuns = [
      { id: 'new-run', command: 'nmap new.darklab.sh', started: '2026-05-07T00:01:00Z', exit_code: 0, output_line_count: 4, created: '2026-05-07T00:01:10Z' },
    ]
    projectFindings = [
      {
        id: 'new-finding',
        run_id: 'new-run',
        run_command: 'nmap new.darklab.sh',
        scope: 'port',
        title: 'new finding after relink',
        raw_line: '80/tcp open http',
        line_number: 2,
        review_state: 'new',
      },
    ]

    await shell.refreshProjectWorkspace()
    await tick()
    await tick()

    expect(document.getElementById('project-explorer-body').textContent).toContain('new finding after relink')
    expect(document.getElementById('project-explorer-body').textContent).not.toContain('old finding should not persist')
  })

  it('autosaves project notes while editing', async () => {
    const apiFetch = vi.fn((url, options = {}) => {
      if (url === '/projects/active') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ project: { id: 'project-1', name: 'darklab.sh', notes: 'Initial notes' } }),
        })
      }
      if (url === '/projects?include_archived=1') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ projects: [{ id: 'project-1', name: 'darklab.sh', status: 'active', notes: 'Initial notes' }] }),
        })
      }
      if (url === '/projects/project-1/summary') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            counts: { runs: 0, findings: 0, artifacts: 0, packages: 0, targets: 0, notes: 0 },
            runs: [],
            targets: [],
            artifacts: [],
            packages: [],
          }),
        })
      }
      if (url === '/projects/project-1' && options.method === 'PUT') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            project: { id: 'project-1', name: 'darklab.sh', status: 'active', notes: JSON.parse(options.body).notes },
          }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const shell = loadShellChrome({ apiFetch })

    await shell.openProjectWorkspace()
    const input = document.getElementById('project-notes-input')
    const saved = document.getElementById('project-notes-save-status')
    expect(input.value).toBe('Initial notes')
    expect(saved.classList.contains('u-hidden')).toBe(true)

    vi.useFakeTimers()
    try {
      input.value = 'Updated notes'
      input.dispatchEvent(new Event('input', { bubbles: true }))
      await vi.advanceTimersByTimeAsync(450)
      expect(saved.classList.contains('u-hidden')).toBe(true)
      await vi.advanceTimersByTimeAsync(200)
      expect(saved.classList.contains('u-hidden')).toBe(false)
    } finally {
      vi.useRealTimers()
    }

    expect(apiFetch).toHaveBeenCalledWith('/projects/project-1', expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({ notes: 'Updated notes' }),
    }))
  })

  it('opens a finding source run at the recorded line', async () => {
    const restoreHistoryRunIntoTab = vi.fn(() => Promise.resolve('tab-restored'))
    const showConfirm = vi.fn((options = {}) => (
      String(options.body || '').startsWith('Delete package:')
        ? Promise.resolve('delete')
        : Promise.resolve('remove')
    ))
    const dismissibles = []
    const bindDismissible = vi.fn((el, options) => {
      dismissibles.push({ el, options })
      return { dispose: vi.fn() }
    })
    let targetStates = [
      {
        id: 'target-1',
        type: 'domain',
        value: 'darklab.sh',
        label: 'Primary domain',
        notes: 'Scope approved',
      },
      {
        id: 'target-2',
        type: 'host',
        value: 'api.darklab.sh',
        label: 'API host',
        notes: 'Secondary scope',
      },
      {
        id: 'target-3',
        type: 'port_set',
        value: '80,443',
        label: 'Web ports',
        notes: 'Common web exposure',
      },
    ]
    let projectRuns = [
      { id: 'run-1', command: 'nuclei https://darklab.sh', started: '2026-05-07T00:00:00Z', exit_code: 0, output_line_count: 42, created: '2026-05-07T00:00:10Z' },
      { id: 'run-2', command: 'httpx https://darklab.sh', started: '2026-05-07T00:01:00Z', exit_code: 0, output_line_count: 12, created: '2026-05-07T00:01:10Z' },
    ]
    const projectArtifacts = [
      {
        id: 'artifact-1',
        run_id: 'run-1',
        workspace_path: 'reports/nuclei.json',
        display_name: 'nuclei.json',
        kind: 'output_file',
        byte_size: 2048,
        content_type: 'application/json',
        file_status: 'available',
        file_available: true,
        current_byte_size: 2048,
        created: '2026-05-07T00:00:12Z',
      },
      {
        id: 'artifact-2',
        run_id: 'run-2',
        workspace_path: 'reports/httpx.json',
        display_name: 'httpx.json',
        kind: 'output_file',
        byte_size: 1024,
        content_type: 'application/json',
        file_status: 'missing',
        file_available: false,
        current_byte_size: null,
        file_status_detail: 'workspace file is not available',
        created: '2026-05-07T00:01:12Z',
      },
    ]
    let projectPackages = [
      {
        id: 'pkg-1',
        name: 'Darklab evidence',
        description: 'Initial package',
        include_artifacts: true,
        status: 'draft',
        updated: '2026-05-07T00:02:12Z',
        manifest: {
          package_format_version: 1,
          preset: 'evidence',
          redaction_mode: 'raw',
          include_private_notes: true,
          options: {
            raw_artifacts: true,
            index_html: true,
            transcripts_html: true,
          },
          estimated_archive: {
            estimated_uncompressed_bytes: 32768,
          },
          counts: { runs: 2, findings: 3, artifacts: 2 },
          selected_entity_ids: {
            run_ids: ['run-1', 'run-missing'],
            transcript_run_ids: ['run-1', 'run-missing'],
            finding_ids: ['finding-1'],
            artifact_ids: ['artifact-1'],
            target_ids: ['target-1'],
          },
        },
      },
    ]
    const entityLabels = new Map([
      ['run:run-1', ['baseline']],
      ['finding:finding-1', ['old-label']],
      ['run_file_artifact:artifact-1', []],
    ])
    const entityNotes = new Map([
      ['run:run-1', 'Run note'],
      ['finding:finding-1', 'Old finding note'],
    ])
    const metadataKey = (entityType, entityId) => `${entityType}:${entityId}`
    const labelObjects = (entityType, entityId) => (
      entityLabels.get(metadataKey(entityType, entityId)) || []
    ).map((label, index) => ({
      id: `label-${entityId}-${index}`,
      entity_type: entityType,
      entity_id: entityId,
      label,
      source: 'manual',
    }))
    const noteObject = (entityType, entityId) => {
      const body = entityNotes.get(metadataKey(entityType, entityId)) || ''
      return body ? {
        id: `note-${entityId}`,
        entity_type: entityType,
        entity_id: entityId,
        body,
      } : null
    }
    let resolvePackageDownloadBlob
    const packageDownloadBlob = new Promise((resolve) => {
      resolvePackageDownloadBlob = resolve
    })
    const apiFetch = vi.fn((url, options = {}) => {
      if (url === '/projects/active') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ project: { id: 'project-1', name: 'darklab.sh' } }),
        })
      }
      if (url === '/projects?include_archived=1') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ projects: [{ id: 'project-1', name: 'darklab.sh', status: 'active' }] }),
        })
      }
      if (url === '/projects/project-1/summary') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            counts: {
              runs: projectRuns.length,
              findings: 3,
              artifacts: projectArtifacts.length,
              packages: projectPackages.length,
              targets: targetStates.length,
              notes: 0,
            },
            runs: projectRuns.map(run => ({
              ...run,
              labels: labelObjects('run', run.id),
              note: noteObject('run', run.id),
            })),
            targets: targetStates,
            artifacts: projectArtifacts.map(artifact => ({
              ...artifact,
              labels: labelObjects('run_file_artifact', artifact.id),
              note: noteObject('run_file_artifact', artifact.id),
            })),
            packages: projectPackages,
          }),
        })
      }
      if (url === '/projects/project-1/targets/target-1' && options.method === 'PUT') {
        targetStates = targetStates.map(target => (
          target.id === 'target-1' ? { ...target, ...JSON.parse(options.body) } : target
        ))
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ target: targetStates.find(target => target.id === 'target-1') }),
        })
      }
      if (url === '/projects/project-1/targets/target-1' && options.method === 'DELETE') {
        targetStates = targetStates.filter(target => target.id !== 'target-1')
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ ok: true }),
        })
      }
      if (url === '/projects/project-1/links' && options.method === 'DELETE') {
        const payload = JSON.parse(options.body)
        projectRuns = projectRuns.filter(run => run.id !== payload.entity_id)
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ ok: true }),
        })
      }
      if (url === '/projects/project-1/findings') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            findings: [
              {
                id: 'finding-1',
                run_id: 'run-1',
                run_command: 'nuclei https://darklab.sh',
                scope: 'http',
                title: 'missing security header',
                raw_line: '[http-missing-security-headers] https://darklab.sh',
                line_number: 42,
                target_id: 'target-1',
                review_state: 'new',
              },
              {
                id: 'finding-2',
                run_id: 'run-2',
                run_command: 'httpx https://darklab.sh',
                scope: 'http',
                title: 'api host responded',
                raw_line: 'https://api.darklab.sh [200]',
                line_number: 7,
                target_id: 'target-2',
                target_ids: ['target-2'],
                review_state: 'reviewed',
              },
              {
                id: 'finding-3',
                run_id: 'run-1',
                run_command: 'nuclei https://darklab.sh',
                scope: 'finding',
                title: 'web port responded',
                raw_line: '443/tcp open https',
                line_number: 13,
                target_id: 'target-1',
                target_ids: ['target-1', 'target-3'],
                review_state: 'important',
              },
            ].map(finding => ({
              ...finding,
              labels: labelObjects('finding', finding.id),
              note: noteObject('finding', finding.id),
            })),
          }),
        })
      }
      const labelsMatch = String(url).match(/^\/entities\/([^/]+)\/([^/]+)\/labels$/)
      if (labelsMatch) {
        const entityType = decodeURIComponent(labelsMatch[1])
        const entityId = decodeURIComponent(labelsMatch[2])
        const key = metadataKey(entityType, entityId)
        if (options.method === 'POST') {
          const payload = JSON.parse(options.body)
          const next = entityLabels.get(key) || []
          if (!next.includes(payload.label)) entityLabels.set(key, [...next, payload.label])
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ label: labelObjects(entityType, entityId).find(item => item.label === payload.label) }),
          })
        }
        if (options.method === 'DELETE') {
          const payload = JSON.parse(options.body)
          entityLabels.set(key, (entityLabels.get(key) || []).filter(label => label !== payload.label))
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ ok: true }),
          })
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ labels: labelObjects(entityType, entityId) }),
        })
      }
      const noteMatch = String(url).match(/^\/entities\/([^/]+)\/([^/]+)\/note$/)
      if (noteMatch) {
        const entityType = decodeURIComponent(noteMatch[1])
        const entityId = decodeURIComponent(noteMatch[2])
        const key = metadataKey(entityType, entityId)
        if (options.method === 'PUT') {
          const payload = JSON.parse(options.body)
          entityNotes.set(key, payload.body)
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ note: noteObject(entityType, entityId) }),
          })
        }
        if (options.method === 'DELETE') {
          entityNotes.delete(key)
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ ok: true }),
          })
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ note: noteObject(entityType, entityId) }),
        })
      }
      if (url === '/projects/project-1/artifacts/artifact-1/preview') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            artifact: projectArtifacts[0],
            text: '{"template":"ok"}\n',
          }),
        })
      }
      if (url === '/projects/project-1/artifacts/artifact-1/download') {
        return Promise.resolve({
          ok: true,
          blob: () => Promise.resolve(new Blob(['{"template":"ok"}\n'], { type: 'application/json' })),
        })
      }
      if (url === '/projects/project-1/packages/pkg-1') {
        if (options.method === 'DELETE') {
          projectPackages = projectPackages.filter(pkg => pkg.id !== 'pkg-1')
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({ ok: true }),
          })
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ package: projectPackages[0] }),
        })
      }
      if (url === '/projects/project-1/packages/pkg-1/download') {
        return Promise.resolve({
          ok: true,
          blob: () => packageDownloadBlob,
        })
      }
      if (url === '/projects/project-1/packages' && options.method === 'POST') {
        const payload = JSON.parse(options.body)
        projectPackages = [{
          id: 'pkg-2',
          name: payload.name,
          description: payload.description,
          include_artifacts: payload.include_artifacts,
          status: 'draft',
          updated: '2026-05-07T00:03:12Z',
          manifest: {
            package_format_version: 1,
            preset: payload.preset,
            counts: {
              runs: payload.selection.run_ids.length,
              findings: payload.selection.finding_ids.length,
              artifacts: payload.selection.artifact_ids.length,
              targets: payload.selection.target_ids.length,
            },
            selected_entity_ids: payload.selection,
            redaction_mode: payload.redaction_mode,
            estimated_archive: {
              estimated_uncompressed_bytes: 24576,
            },
          },
        }]
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ ok: true, package: projectPackages[0] }),
        })
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({}),
      })
    })
    const showWorkspaceViewer = vi.fn()
    const fetchAndRenderHistoryComparison = vi.fn()
    globalThis.URL.createObjectURL = vi.fn(() => 'blob:project-artifact')
    globalThis.URL.revokeObjectURL = vi.fn()
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const shell = loadShellChrome({
      apiFetch,
      restoreHistoryRunIntoTab,
      showWorkspaceViewer,
      showConfirm,
      fetchAndRenderHistoryComparison,
      bindDismissible,
    })

    await shell.openProjectWorkspace()
    expect(document.querySelector('.project-target-row')?.textContent).toContain('Primary domain')
    expect(document.querySelector('.project-explorer-section-heading')?.textContent).toContain('New')
    expect(bindDismissible).toHaveBeenCalledWith(
      document.getElementById('project-target-editor-overlay'),
      expect.objectContaining({ level: 'modal' }),
    )
    expect(bindDismissible).toHaveBeenCalledWith(
      document.getElementById('project-package-wizard-overlay'),
      expect.objectContaining({ level: 'modal' }),
    )
    expectProjectPressablesBound([
      '.project-workspace-row',
      '.project-explorer-tab',
      '.project-explorer-actions .btn',
    ])

    document.querySelector('[data-project-action="edit-target"]').click()
    await tick()
    expect(document.getElementById('project-target-editor-overlay').classList.contains('open')).toBe(true)
    expect(document.getElementById('project-target-editor-title').textContent).toBe('EDIT TARGET')
    document.getElementById('project-target-value').value = 'darklab.io'
    document.getElementById('project-target-label').value = 'Updated target'
    document.getElementById('project-target-notes').value = 'Retest scope'
    document.getElementById('project-target-create-form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await tick()
    await tick()
    await tick()
    expect(apiFetch).toHaveBeenCalledWith('/projects/project-1/targets/target-1', expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({
        type: 'domain',
        value: 'darklab.io',
        label: 'Updated target',
        notes: 'Retest scope',
      }),
    }))
    expect(document.querySelector('.project-target-row')?.textContent).toContain('darklab.io')
    expect(document.getElementById('project-workspace-message').textContent).toContain('Target updated.')

    document.querySelector('[data-project-tab="findings"]').click()
    await tick()
    await tick()
    expect(document.getElementById('project-workspace-message').classList.contains('u-hidden')).toBe(true)
    expect(document.getElementById('project-explorer-body').textContent).toContain('old-label')
    expect(document.getElementById('project-explorer-body').textContent).toContain('note')
    document.querySelector('[data-project-action="edit-finding-metadata"][data-finding-id="finding-1"]').click()
    await tick()
    expect(document.getElementById('project-entity-editor-overlay').classList.contains('open')).toBe(true)
    expect(document.getElementById('project-entity-editor-title').textContent).toBe('EDIT FINDING')
    expect(document.getElementById('project-entity-editor-subtitle').textContent).toContain('missing security header')
    expect(document.getElementById('project-entity-labels').value).toBe('old-label')
    expect(document.getElementById('project-entity-note').value).toBe('Old finding note')
    document.getElementById('project-entity-labels').value = 'important, retest, Important'
    document.getElementById('project-entity-note').value = 'Needs retest'
    document.getElementById('project-entity-editor-form')
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await tick()
    await tick()
    await tick()
    await tick()
    expect(apiFetch).toHaveBeenCalledWith('/entities/finding/finding-1/labels', expect.objectContaining({
      method: 'DELETE',
      body: JSON.stringify({ label: 'old-label' }),
    }))
    expect(apiFetch).toHaveBeenCalledWith('/entities/finding/finding-1/labels', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ label: 'important' }),
    }))
    expect(apiFetch).toHaveBeenCalledWith('/entities/finding/finding-1/labels', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ label: 'retest' }),
    }))
    expect(apiFetch).toHaveBeenCalledWith('/entities/finding/finding-1/note', expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({ body: 'Needs retest' }),
    }))
    expect(document.getElementById('project-entity-editor-overlay').classList.contains('open')).toBe(false)
    expect(document.getElementById('project-explorer-body').textContent).toContain('retest')
    expect(document.getElementById('project-explorer-body').textContent).not.toContain('old-label')

    const importantFilter = document.querySelector('[data-project-finding-status-filter-option][value="important"]')
    expect(importantFilter).not.toBeNull()
    importantFilter.checked = true
    importantFilter.dispatchEvent(new Event('change', { bubbles: true }))
    await tick()
    expect(document.querySelector('.project-explorer-filter-chips .project-target-filter-chip')?.textContent).toContain('status: Important')
    expect(document.getElementById('project-explorer-body').textContent).toContain('web port responded')
    expect(document.getElementById('project-explorer-body').textContent).not.toContain('missing security header')
    expect(document.getElementById('project-explorer-body').textContent).not.toContain('api host responded')
    expectProjectPressablesBound([
      '.project-explorer-group-toggle',
      '.project-explorer-item-click-target',
      '.project-target-filter-chip',
      '.project-target-filter-clear',
    ])

    const groupToggle = document.querySelector('[data-project-finding-group-toggle]')
    expect(groupToggle).not.toBeNull()
    expect(groupToggle.getAttribute('aria-expanded')).toBe('true')
    expect(groupToggle.textContent).toContain('1 finding')
    groupToggle.click()
    await tick()
    expect(document.querySelector('[data-project-finding-group-toggle]').getAttribute('aria-expanded')).toBe('false')
    expect(document.querySelector('.project-explorer-group-body').hidden).toBe(true)
    document.querySelector('[data-project-finding-group-toggle]').click()
    await tick()
    expect(document.querySelector('[data-project-finding-group-toggle]').getAttribute('aria-expanded')).toBe('true')
    expect(document.querySelector('.project-explorer-group-body').hidden).toBe(false)
    expect(document.getElementById('project-explorer-body').textContent).toContain('web port responded')

    document.querySelector('[data-project-finding-status-filter-clear="important"]').click()
    await tick()
    const apiTargetFilter = document.querySelector('[data-project-target-filter-option][value="target-2"]')
    expect(apiTargetFilter).not.toBeNull()
    apiTargetFilter.checked = true
    apiTargetFilter.dispatchEvent(new Event('change', { bubbles: true }))
    await tick()
    expect(document.querySelector('.project-target-filter-chip')?.textContent).toContain('target: host: api.darklab.sh')
    expect(document.getElementById('project-explorer-body').textContent).toContain('api host responded')
    expect(document.getElementById('project-explorer-body').textContent).not.toContain('missing security header')

    document.querySelector('[data-project-target-filter-clear="target-2"]').click()
    await tick()
    const portTargetFilter = document.querySelector('[data-project-target-filter-option][value="target-3"]')
    expect(portTargetFilter).not.toBeNull()
    portTargetFilter.checked = true
    portTargetFilter.dispatchEvent(new Event('change', { bubbles: true }))
    await tick()
    expect(document.querySelector('.project-target-filter-chip')?.textContent).toContain('target: port_set: 80,443')
    expect(document.getElementById('project-explorer-body').textContent).toContain('web port responded')
    expect(document.getElementById('project-explorer-body').textContent).not.toContain('api host responded')

    document.querySelector('[data-project-tab="artifacts"]').click()
    await tick()
    expect(document.getElementById('project-explorer-body').textContent).toContain('nuclei.json')
    expect(document.getElementById('project-explorer-body').textContent).not.toContain('httpx.json')

    document.querySelector('[data-project-tab="runs"]').click()
    await tick()
    expect(document.getElementById('project-explorer-body').textContent).toContain('baseline')
    expect(document.getElementById('project-explorer-body').textContent).toContain('note')
    expectProjectPressablesBound(['.project-run-compare-controls .btn'])
    document.querySelector('[data-project-action="edit-run-metadata"][data-run-id="run-1"]').click()
    await tick()
    expect(document.getElementById('project-entity-editor-overlay').classList.contains('open')).toBe(true)
    expect(document.getElementById('project-entity-editor-title').textContent).toBe('EDIT RUN')
    expect(document.getElementById('project-entity-editor-subtitle').textContent).toContain('nuclei https://darklab.sh')
    expect(document.getElementById('project-entity-labels').value).toBe('baseline')
    expect(document.getElementById('project-entity-note').value).toBe('Run note')
    document.getElementById('project-entity-labels').value = 'baseline, reviewed'
    document.getElementById('project-entity-note').value = 'Run triaged'
    document.getElementById('project-entity-editor-form')
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await tick()
    await tick()
    await tick()
    expect(apiFetch).toHaveBeenCalledWith('/entities/run/run-1/labels', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ label: 'reviewed' }),
    }))
    expect(apiFetch).toHaveBeenCalledWith('/entities/run/run-1/note', expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({ body: 'Run triaged' }),
    }))
    expect(document.getElementById('project-entity-editor-overlay').classList.contains('open')).toBe(false)
    expect(document.getElementById('project-explorer-body').textContent).toContain('reviewed')

    document.querySelector('[data-project-action="compare-runs"]').click()
    await tick()
    expect(fetchAndRenderHistoryComparison).toHaveBeenCalledWith(
      'run-1',
      'run-2',
      {
        url: '/projects/project-1/compare?left_run_id=run-1&right_run_id=run-2',
      },
    )
    expect(document.querySelector('[data-project-action="filter-run"][data-run-id="run-1"]')).not.toBeNull()
    expect(document.querySelector('[data-project-action="filter-run"][data-run-id="run-2"]')).toBeNull()

    document.querySelector('[data-project-target-filter-clear="target-3"]').click()
    await tick()
    document.querySelector('[data-project-tab="artifacts"]').click()
    await tick()
    expect(document.querySelector('.project-artifact-status.is-available')?.textContent).toBe('available')
    expect(document.querySelector('.project-artifact-status.is-missing')?.textContent).toBe('missing')
    expect(document.getElementById('project-explorer-body').textContent).toContain('workspace file is not available')
    expectProjectPressablesBound([
      '.project-explorer-group-toggle',
      '.project-artifact-action',
    ])
    document.querySelector('[data-project-action="edit-artifact-metadata"][data-artifact-id="artifact-1"]').click()
    await tick()
    expect(document.getElementById('project-entity-editor-overlay').classList.contains('open')).toBe(true)
    expect(document.getElementById('project-entity-editor-title').textContent).toBe('EDIT ARTIFACT')
    expect(document.getElementById('project-entity-editor-subtitle').textContent).toContain('nuclei.json')
    document.getElementById('project-entity-labels').value = 'evidence'
    document.getElementById('project-entity-note').value = 'Raw output reviewed'
    document.getElementById('project-entity-editor-form')
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await tick()
    await tick()
    await tick()
    expect(apiFetch).toHaveBeenCalledWith('/entities/run_file_artifact/artifact-1/labels', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ label: 'evidence' }),
    }))
    expect(apiFetch).toHaveBeenCalledWith('/entities/run_file_artifact/artifact-1/note', expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({ body: 'Raw output reviewed' }),
    }))
    expect(document.getElementById('project-entity-editor-overlay').classList.contains('open')).toBe(false)
    expect(document.getElementById('project-explorer-body').textContent).toContain('evidence')

    document.querySelector('[data-project-action="artifact-preview"][data-artifact-id="artifact-1"]').click()
    await tick()
    expect(apiFetch).toHaveBeenCalledWith(
      '/projects/project-1/artifacts/artifact-1/preview',
      { cache: 'no-store' },
    )
    expect(showWorkspaceViewer).toHaveBeenCalledWith(
      'reports/nuclei.json',
      '{"template":"ok"}\n',
      { size: 2048, elevated: true },
    )
    document.querySelector('[data-project-action="artifact-download"][data-artifact-id="artifact-1"]').click()
    await tick()
    await tick()
    expect(apiFetch).toHaveBeenCalledWith(
      '/projects/project-1/artifacts/artifact-1/download',
      { cache: 'no-store' },
    )
    expect(globalThis.URL.createObjectURL).toHaveBeenCalled()
    expect(document.querySelector('[data-project-action="artifact-preview"][data-artifact-id="artifact-2"]').disabled)
      .toBe(true)
    globalThis.URL.createObjectURL.mockClear()

    document.querySelector('[data-project-tab="packages"]').click()
    await tick()
    expect(document.getElementById('project-explorer-body').textContent).toContain('Darklab evidence')
    expect(document.getElementById('project-explorer-body').textContent).toContain('evidence · raw · ~32 KB')
    expect(document.getElementById('project-explorer-body').textContent).toContain('2 runs · 3 findings · 2 artifacts')
    expect(document.querySelector('[data-project-action="package-manifest"][data-package-id="pkg-1"]')).not.toBeNull()
    expectProjectPressablesBound(['.project-package-action'])
    document.querySelector('[data-project-action="package-manifest"][data-package-id="pkg-1"]').click()
    await tick()
    expect(apiFetch).toHaveBeenCalledWith(
      '/projects/project-1/packages/pkg-1',
      expect.objectContaining({ cache: 'no-store' }),
    )
    expect(document.getElementById('project-package-manifest-overlay').classList.contains('open')).toBe(true)
    expect(document.getElementById('project-package-manifest-json').textContent).toContain('"package_format_version": 1')
    document.querySelector('.project-package-manifest-close').click()
    await tick()
    expect(document.getElementById('project-package-manifest-overlay').classList.contains('open')).toBe(false)

    const packageDownloadButton = document.querySelector('[data-project-action="package-download"][data-package-id="pkg-1"]')
    packageDownloadButton.click()
    await tick()
    await tick()
    expect(apiFetch).toHaveBeenCalledWith(
      '/projects/project-1/packages/pkg-1/download',
      { cache: 'no-store' },
    )
    expect(packageDownloadButton.disabled).toBe(true)
    expect(packageDownloadButton.classList.contains('is-preparing')).toBe(true)
    expect(packageDownloadButton.getAttribute('aria-busy')).toBe('true')
    expect(packageDownloadButton.textContent).toBe('Preparing...')
    expect(globalThis.URL.createObjectURL).not.toHaveBeenCalled()
    resolvePackageDownloadBlob(new Blob(['package zip'], { type: 'application/zip' }))
    await tick()
    await tick()
    expect(globalThis.URL.createObjectURL).toHaveBeenCalled()
    expect(packageDownloadButton.disabled).toBe(false)
    expect(packageDownloadButton.classList.contains('is-preparing')).toBe(false)
    expect(packageDownloadButton.getAttribute('aria-busy')).toBeNull()
    expect(packageDownloadButton.textContent).toBe('Download')
    expect(globalThis.URL.revokeObjectURL).not.toHaveBeenCalled()
    window.dispatchEvent(new Event('pagehide'))
    expect(globalThis.URL.revokeObjectURL).toHaveBeenCalledWith('blob:project-artifact')

    document.querySelector('[data-project-action="package-repackage"][data-package-id="pkg-1"]').click()
    await tick()
    await tick()
    expect(apiFetch).toHaveBeenCalledWith(
      '/projects/project-1/packages/pkg-1',
      expect.objectContaining({ cache: 'no-store' }),
    )
    expect(document.querySelector('.project-package-step.is-active')?.textContent).toContain('Include')
    expect(document.querySelector('[data-project-package-selection="run"][value="run-1"]').checked).toBe(true)
    expect(document.querySelector('[data-project-package-selection="run"][value="run-2"]').checked).toBe(false)
    expect(document.querySelector('[data-project-package-selection="transcript"][value="run-1"]').checked).toBe(true)
    expect(document.querySelector('[data-project-package-selection="transcript"][value="run-2"]').disabled).toBe(true)
    expect(document.getElementById('project-package-wizard-overlay').textContent).toContain('run-missing is no longer linked')
    expect(document.querySelector('[data-project-package-selection="artifact"][value="artifact-1"]').checked).toBe(true)
    expect(document.querySelector('[data-project-package-selection="artifact"][value="artifact-2"]').checked).toBe(false)
    document.querySelector('[data-project-action="package-wizard-next"]').click()
    await tick()
    expect(document.querySelector('[data-project-package-field="name"]').value).toBe('Darklab evidence')
    expect(document.querySelector('[data-project-package-field="redaction_mode"]').value).toBe('raw')
    document.querySelector('[data-project-action="package-wizard-next"]').click()
    await tick()
    expect(document.querySelector('.project-package-step.is-active')?.textContent).toContain('Preview')
    document.querySelector('[data-project-action="package-wizard-next"]').click()
    await tick()
    expect(document.querySelector('.project-package-step.is-active')?.textContent).toContain('Include')
    expect(document.getElementById('project-workspace-message').textContent).toContain(
      '2 unavailable items removed; review your selection before continuing.',
    )
    document.querySelector('[data-project-message-dismiss]').click()
    await tick()
    expect(document.getElementById('project-workspace-message').classList.contains('u-hidden')).toBe(true)
    expect(document.getElementById('project-package-wizard-overlay').textContent).not.toContain('run-missing is no longer linked')
    document.querySelector('[data-project-action="package-wizard-cancel"]').click()
    await tick()
    expect(document.getElementById('project-package-wizard-overlay').classList.contains('open')).toBe(false)

    document.querySelector('[data-project-action="package-delete"][data-package-id="pkg-1"]').click()
    await tick()
    await tick()
    await tick()
    expect(showConfirm).toHaveBeenCalledWith(expect.objectContaining({
      body: 'Delete package: Darklab evidence?',
      tone: 'danger',
    }))
    expect(apiFetch).toHaveBeenCalledWith('/projects/project-1/packages/pkg-1', expect.objectContaining({
      method: 'DELETE',
    }))
    expect(document.getElementById('project-explorer-body').textContent).toContain('No evidence packages yet.')

    document.querySelector('[data-project-action="package-wizard-open"]').click()
    await tick()
    expect(document.getElementById('project-package-wizard-overlay').classList.contains('open')).toBe(true)
    expect(document.querySelector('.project-package-step.is-active')?.textContent).toContain('Preset')
    expect(document.getElementById('project-package-wizard-overlay').textContent).toContain('Evidence')
    document.querySelector('[data-project-action="package-wizard-next"]').click()
    await tick()
    expect(document.querySelector('.project-package-step.is-active')?.textContent).toContain('Include')
    expect(document.getElementById('project-package-wizard-overlay').textContent).toContain('Findings (2)')
    expect(document.getElementById('project-package-wizard-overlay').textContent).toContain('Artifacts (1)')
    expectProjectPressablesBound(['.project-package-run-toggle'])
    let run2Group = document.querySelector('[data-project-package-selection="run"][value="run-2"]')
      .closest('.project-package-run-selection')
    let run2Toggle = run2Group.querySelector('[data-project-package-run-toggle]')
    expect(run2Group.querySelector('.project-package-run-body').hidden).toBe(false)
    run2Toggle.click()
    await tick()
    run2Group = document.querySelector('[data-project-package-selection="run"][value="run-2"]')
      .closest('.project-package-run-selection')
    run2Toggle = run2Group.querySelector('[data-project-package-run-toggle]')
    expect(run2Group.classList.contains('is-collapsed')).toBe(true)
    expect(run2Group.querySelector('.project-package-run-body').hidden).toBe(true)
    run2Toggle.click()
    await tick()
    run2Group = document.querySelector('[data-project-package-selection="run"][value="run-2"]')
      .closest('.project-package-run-selection')
    expect(run2Group.classList.contains('is-collapsed')).toBe(false)
    expect(run2Group.querySelector('.project-package-run-body').hidden).toBe(false)
    const run2Selection = document.querySelector('[data-project-package-selection="run"][value="run-2"]')
    run2Selection.checked = true
    run2Selection.dispatchEvent(new Event('change', { bubbles: true }))
    await tick()
    expect(document.querySelector('[data-project-package-selection="transcript"][value="run-2"]').checked).toBe(true)
    expect(document.querySelector('[data-project-package-selection="transcript"][value="run-2"]').disabled).toBe(false)
    expect(document.querySelector('[data-project-package-selection="finding"][value="finding-2"]').checked).toBe(true)
    expect(document.querySelector('[data-project-package-selection="artifact"][value="artifact-2"]').checked).toBe(true)
    document.querySelector('[data-project-package-selection="run"][value="run-2"]').checked = false
    document.querySelector('[data-project-package-selection="run"][value="run-2"]')
      .dispatchEvent(new Event('change', { bubbles: true }))
    await tick()
    expect(document.querySelector('[data-project-package-selection="transcript"][value="run-2"]').checked).toBe(false)
    expect(document.querySelector('[data-project-package-selection="transcript"][value="run-2"]').disabled).toBe(true)
    expect(document.querySelector('[data-project-package-selection="finding"][value="finding-2"]').checked).toBe(false)
    expect(document.querySelector('[data-project-package-selection="artifact"][value="artifact-2"]').checked).toBe(false)
    const oldArtifactSelection = document.querySelector('[data-project-package-selection="artifact"][value="artifact-2"]')
    expect(oldArtifactSelection).not.toBeNull()
    oldArtifactSelection.checked = false
    oldArtifactSelection.dispatchEvent(new Event('change', { bubbles: true }))
    await tick()
    document.querySelector('[data-project-action="package-wizard-next"]').click()
    await tick()
    expect(document.querySelector('.project-package-step.is-active')?.textContent).toContain('Metadata')
    const packageName = document.querySelector('[data-project-package-field="name"]')
    packageName.value = 'Scoped evidence'
    packageName.dispatchEvent(new Event('input', { bubbles: true }))
    document.querySelector('[data-project-action="package-wizard-next"]').click()
    await tick()
    expect(document.querySelector('.project-package-step.is-active')?.textContent).toContain('Preview')
    expect(document.querySelector('.project-package-preview-json')?.textContent).toContain('"artifacts": 1')
    expect(document.querySelector('.project-package-preview-json')?.textContent).toContain('"estimated_archive"')
    expect(document.querySelector('.project-package-preview-json')?.textContent).toContain('"transcript_run_ids"')
    expect(document.getElementById('project-package-wizard-overlay').textContent).toContain('Estimated package size before compression')
    document.querySelector('[data-project-action="package-wizard-next"]').click()
    await tick()
    await tick()
    const packageCreateCall = apiFetch.mock.calls.find(([url, options]) => (
      url === '/projects/project-1/packages' && options?.method === 'POST'
    ))
    expect(packageCreateCall).toBeTruthy()
    const packagePayload = JSON.parse(packageCreateCall[1].body)
    expect(packagePayload.name).toBe('Scoped evidence')
    expect(packagePayload.preset).toBe('evidence')
    expect(packagePayload.redaction_mode).toBe('raw')
    expect(packagePayload.include_artifacts).toBe(true)
    expect(packagePayload.options.index_html).toBe(true)
    expect(packagePayload.options.transcripts_html).toBe(true)
    expect(packagePayload.selection.run_ids).toEqual(['run-1'])
    expect(packagePayload.selection.transcript_run_ids).toEqual(['run-1'])
    expect(packagePayload.selection.artifact_ids).toEqual(['artifact-1'])
    expect(document.getElementById('project-explorer-body').textContent).toContain('Scoped evidence')

    document.querySelector('[data-project-tab="runs"]').click()
    await tick()
    expect(document.querySelector('[data-project-action="filter-run"][data-run-id="run-1"]')).not.toBeNull()
    expect(document.querySelector('[data-project-action="filter-run-findings"][data-run-id="run-1"]')?.textContent).toBe('2 findings')
    expect(document.querySelector('[data-project-action="filter-run-artifacts"][data-run-id="run-1"]')?.textContent).toBe('1 artifact')

    document.querySelector('[data-project-tab="runs"]').click()
    await tick()
    document.querySelector('[data-project-action="filter-run-findings"][data-run-id="run-1"]').click()
    await tick()
    expect(document.querySelector('[data-project-tab="findings"]').classList.contains('is-active')).toBe(true)
    expect(document.querySelector('[data-project-run-filter-clear="run-1"]')?.textContent).toContain('run: nuclei https:/ ...')
    expect(document.getElementById('project-explorer-body').textContent).toContain('missing security header')
    expect(document.getElementById('project-explorer-body').textContent).not.toContain('api host responded')

    document.querySelector('[data-project-tab="runs"]').click()
    await tick()
    document.querySelector('[data-project-run-filter-clear="run-1"]')?.click()
    await tick()
    document.querySelector('[data-project-action="filter-run-artifacts"][data-run-id="run-1"]').click()
    await tick()
    expect(document.querySelector('[data-project-tab="artifacts"]').classList.contains('is-active')).toBe(true)
    expect(document.getElementById('project-explorer-body').textContent).toContain('nuclei.json')
    expect(document.getElementById('project-explorer-body').textContent).not.toContain('httpx.json')

    document.querySelector('[data-project-tab="runs"]').click()
    await tick()
    document.querySelector('[data-project-run-filter-clear="run-1"]')?.click()
    await tick()
    document.querySelector('[data-project-action="filter-run"][data-run-id="run-1"]').click()
    await tick()
    expect(restoreHistoryRunIntoTab).not.toHaveBeenCalled()
    expect(document.querySelector('[data-project-run-filter-clear="run-1"]')?.textContent).toContain('run: nuclei https:/ ...')
    expect(document.querySelector('[data-project-action="filter-run"][data-run-id="run-2"]')).toBeNull()

    document.querySelector('[data-project-action="open-run"][data-run-id="run-1"]').click()
    await tick()
    expect(restoreHistoryRunIntoTab).toHaveBeenCalledWith(
      {
        id: 'run-1',
        command: 'nuclei https://darklab.sh',
        full_output_available: true,
      },
      {
        hidePanelOnSuccess: false,
      },
    )
    expect(document.getElementById('project-workspace-overlay').classList.contains('open')).toBe(false)
    restoreHistoryRunIntoTab.mockClear()

    await shell.openProjectWorkspace()
    document.querySelector('[data-project-tab="runs"]').click()
    await tick()
    document.querySelector('[data-project-run-filter-clear="run-1"]')?.click()
    await tick()
    const unlinkRun = document.querySelector('[data-project-action="unlink-run"][data-run-id="run-2"]')
    expect(unlinkRun?.dataset.projectId).toBe('project-1')
    unlinkRun.click()
    await tick()
    await tick()
    await tick()
    expect(showConfirm).toHaveBeenCalledWith(expect.objectContaining({
      body: 'Remove run from project: httpx https://darklab.sh?',
      tone: 'danger',
    }))
    expect(apiFetch).toHaveBeenCalledWith('/projects/project-1/links', expect.objectContaining({
      method: 'DELETE',
      body: JSON.stringify({ entity_type: 'run', entity_id: 'run-2' }),
    }))
    expect(document.querySelector('[data-project-action="open-run"][data-run-id="run-2"]')).toBeNull()

    restoreHistoryRunIntoTab.mockClear()
    document.querySelector('[data-project-tab="artifacts"]').click()
    await tick()
    const artifactGroupToggle = document.querySelector('[data-project-artifact-group-toggle]')
    expect(artifactGroupToggle?.textContent).toContain('nuclei https://darklab.sh (run-1)')
    expect(artifactGroupToggle?.textContent).toContain('1 artifact')
    expect(artifactGroupToggle.getAttribute('aria-expanded')).toBe('true')
    expect(document.querySelector('.project-explorer-item')?.textContent).toContain('nuclei.json')
    expect(document.querySelector('.project-artifact-status.is-available')?.textContent).toBe('available')
    artifactGroupToggle.click()
    await tick()
    expect(document.querySelector('[data-project-artifact-group-toggle]').getAttribute('aria-expanded')).toBe('false')
    expect(document.querySelector('.project-explorer-group-body').hidden).toBe(true)
    expect(restoreHistoryRunIntoTab).not.toHaveBeenCalled()
    document.querySelector('[data-project-artifact-group-toggle]').click()
    await tick()
    expect(document.querySelector('[data-project-artifact-group-toggle]').getAttribute('aria-expanded')).toBe('true')
    expect(document.querySelector('.project-explorer-group-body').hidden).toBe(false)

    await shell.openProjectWorkspace()
    document.querySelector('[data-project-tab="findings"]').click()
    await tick()
    await tick()
    expect(document.querySelector('.project-explorer-item-meta')?.textContent)
      .toBe('http · target domain: darklab.io · line 42')

    const reviewControl = document.querySelector('.project-finding-review')
    expect(reviewControl.classList.contains('form-select')).toBe(true)
    expect(reviewControl.classList.contains('form-control-compact')).toBe(true)
    expect(shell.enhanceAppSelects).toHaveBeenCalledWith(reviewControl.closest('.project-explorer-tab-panel'))
    expect(reviewControl.value).toBe('new')
    reviewControl.value = 'important'
    reviewControl.dispatchEvent(new Event('change', { bubbles: true }))
    await tick()
    expect(apiFetch).toHaveBeenCalledWith('/findings/finding-1/review', expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({ review_state: 'important' }),
    }))
    expect(restoreHistoryRunIntoTab).not.toHaveBeenCalled()
    expect(document.querySelector('.project-finding-review')?.value).toBe('important')

    document.querySelector('[data-project-action="open-finding"]').click()
    await tick()

    expect(restoreHistoryRunIntoTab).toHaveBeenCalledWith(
      {
        id: 'run-1',
        command: 'nuclei https://darklab.sh',
        full_output_available: true,
      },
      {
        hidePanelOnSuccess: false,
        highlightLineIndex: 42,
      },
    )
    expect(document.getElementById('project-workspace-overlay').classList.contains('open')).toBe(false)

    await shell.openProjectWorkspace()
    document.querySelector('[data-project-tab="details"]').click()
    await tick()
    document.querySelector('[data-project-action="delete-target"]').click()
    await tick()
    await tick()
    await tick()

    expect(showConfirm).toHaveBeenCalledWith(expect.objectContaining({
      body: 'Remove target darklab.io?',
      tone: 'danger',
    }))
    expect(apiFetch).toHaveBeenCalledWith('/projects/project-1/targets/target-1', expect.objectContaining({
      method: 'DELETE',
    }))
    expect(document.querySelector('[data-project-action="edit-target"][data-target-id="target-1"]')).toBeNull()
    expect(document.querySelector('.project-target-row')?.textContent).toContain('api.darklab.sh')
  })
})
