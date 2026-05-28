import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../../..')
const ENTITY_METADATA_SRC = readFileSync(resolve(REPO_ROOT, 'app/static/js/ui/ui_entity_metadata.js'), 'utf8')
const UI_ACTION_SHEET_SRC = readFileSync(resolve(REPO_ROOT, 'app/static/js/ui/ui_action_sheet.js'), 'utf8')
const ATLAS_ENTITY_ROW_SRC = readFileSync(resolve(REPO_ROOT, 'app/static/js/features/atlas/atlas_entity_row.js'), 'utf8')
const PROJECT_TARGET_VALIDATION_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/projects/project_target_validation.js'),
  'utf8',
)
const PROJECTS_CSS = readFileSync(resolve(REPO_ROOT, 'app/static/css/features/projects.css'), 'utf8')
const PROJECT_ACTIVE_CONTEXT_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/projects/project_active_context.js'),
  'utf8',
)
const PROJECT_WORKSPACE_CONSTANTS_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/projects/project_workspace_constants.js'),
  'utf8',
)
const PROJECT_WORKSPACE_STATE_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/projects/project_workspace_state.js'),
  'utf8',
)
const PROJECT_SHARED_UI_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/projects/project_shared_ui.js'),
  'utf8',
)
const PROJECT_DETAILS_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/projects/project_details.js'),
  'utf8',
)
const PROJECT_LIST_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/projects/project_list.js'),
  'utf8',
)
const PROJECT_NAVIGATION_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/projects/project_navigation.js'),
  'utf8',
)
const PROJECT_ENTITY_EDITOR_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/projects/project_entity_editor.js'),
  'utf8',
)
const PROJECT_WORKSPACE_ACTIONS_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/projects/project_workspace_actions.js'),
  'utf8',
)
const PROJECT_WORKSPACE_SHELL_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/projects/project_workspace_shell.js'),
  'utf8',
)
const PROJECT_WORKSPACE_LIFECYCLE_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/projects/project_workspace_lifecycle.js'),
  'utf8',
)
const PROJECT_WORKSPACE_RENDERER_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/projects/project_workspace_renderer.js'),
  'utf8',
)
const PROJECT_WORKSPACE_BOOTSTRAP_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/projects/project_workspace_bootstrap.js'),
  'utf8',
)
const PROJECT_NESTED_SHEETS_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/projects/project_nested_sheets.js'),
  'utf8',
)
const PROJECT_WORKSPACE_EVENTS_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/projects/project_workspace_events.js'),
  'utf8',
)
const PROJECT_TARGETS_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/projects/project_targets.js'),
  'utf8',
)
const PROJECT_RUNS_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/projects/project_runs.js'),
  'utf8',
)
const PROJECT_MOBILE_COMPARE_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/projects/project_mobile_compare.js'),
  'utf8',
)
const PROJECT_MOBILE_SHELL_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/projects/project_mobile_shell.js'),
  'utf8',
)
const PROJECT_MOBILE_DETAIL_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/projects/project_mobile_detail.js'),
  'utf8',
)
const PROJECT_FINDINGS_DATA_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/projects/project_findings_data.js'),
  'utf8',
)
const PROJECT_FILTERS_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/projects/project_filters.js'),
  'utf8',
)
const PROJECT_ENTITIES_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/projects/project_entities.js'),
  'utf8',
)
const PROJECT_FINDINGS_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/projects/project_findings.js'),
  'utf8',
)
const PROJECT_FINDINGS_BOARD_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/projects/project_findings_board.js'),
  'utf8',
)
const FINDINGS_BOARD_MODAL_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/findings/findings_board_modal.js'),
  'utf8',
)
const PROJECT_ARTIFACTS_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/projects/project_artifacts.js'),
  'utf8',
)
const PROJECT_PACKAGES_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/projects/project_packages.js'),
  'utf8',
)
const SHELL_CHROME_SRC = readFileSync(resolve(REPO_ROOT, 'app/static/js/shell_chrome.js'), 'utf8')

function tick() {
  return new Promise(resolve => setTimeout(resolve, 0))
}

const PRESSABLE_PRIMITIVE_CLASSES = new Set([
  'btn',
  'nav-item',
  'tab-strip-item',
  'close-btn',
  'toggle-btn',
  'kb-key',
  'chip',
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
  showToast = vi.fn(),
  appConfig = { workspace_enabled: true },
  fetchAndRenderHistoryComparison = vi.fn(),
  bindDismissible = null,
  bindMobileSheet = null,
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
  getProjectAutoLinkRunEntitiesPreference = () => preferences.pref_project_auto_link_run_entities || 'on',
  applyProjectAutoLinkRunEntitiesPreference = (mode) => { preferences.pref_project_auto_link_run_entities = mode },
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
      <nav id="rail-nav">
        <button id="rail-more-btn" class="rail-nav-item nav-item" data-action="rail-more" type="button" aria-expanded="false" aria-controls="rail-more-menu"></button>
        <div id="rail-more-menu" class="u-hidden">
          <button class="rail-nav-item nav-item" data-action="status-monitor" type="button"></button>
          <button class="rail-nav-item nav-item" data-action="findings-board" type="button"></button>
        </div>
        <button class="rail-nav-item nav-item" data-action="projects" type="button"><span class="rail-nav-glyph">◇</span></button>
      </nav>
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
        <section id="project-mobile-root" class="project-mobile-root">
          <div id="project-mobile-list-view" class="project-mobile-list-view">
            <span id="project-mobile-summary"></span>
            <button id="project-mobile-new-btn" type="button" data-project-mobile-action="new-project"></button>
            <div id="project-mobile-body"></div>
          </div>
          <form id="project-mobile-create-form" class="u-hidden">
            <input id="project-mobile-name" maxlength="120">
          </form>
          <div id="project-mobile-detail-view" class="u-hidden">
            <div id="project-mobile-detail-topbar"></div>
            <div class="project-mobile-tabs-wrap">
              <div id="project-mobile-tabs"></div>
            </div>
            <div id="project-mobile-detail-body"></div>
          </div>
        </section>
        <form id="project-workspace-create-form">
          <input id="project-workspace-name">
        </form>
        <form id="project-notes-form">
          <textarea id="project-notes-input"></textarea>
        </form>
        <form id="project-labels-form">
          <input id="project-labels-input">
          <button id="project-labels-save-btn" type="submit"></button>
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
              <option value="url">url</option>
              <option value="host">host</option>
              <option value="ip">ip</option>
            </select>
            <input id="project-target-value">
            <small id="project-target-value-help"></small>
            <div id="project-target-value-error" class="u-hidden"></div>
            <input id="project-target-label">
            <textarea id="project-target-notes" maxlength="20000"></textarea>
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
    <div id="findings-board-overlay" class="u-hidden" aria-hidden="true">
      <div id="findings-board-modal">
        <span id="findings-board-title"></span>
        <div id="findings-board-subtitle"></div>
        <button id="findings-board-refresh-btn" type="button"></button>
        <button class="findings-board-close" type="button"></button>
        <div id="findings-board-message" class="u-hidden"></div>
        <div id="findings-board-body"></div>
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
    showToast,
    fetchAndRenderHistoryComparison,
    bindDismissible,
    bindMobileSheet,
    enhanceAppSelects,
    syncAppSelect,
  }
  const downloadBlobAsAttachment = (blob, filename) => {
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename || 'download'
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    let revoked = false
    const revoke = () => {
      if (revoked) return
      revoked = true
      URL.revokeObjectURL(url)
    }
    window.setTimeout(revoke, 2000)
    window.addEventListener('pagehide', revoke, { once: true })
  }
  global.APP_CONFIG = appConfig

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
    'showToast',
    'getProjectAutoLinkExternalRunsPreference',
    'applyProjectAutoLinkExternalRunsPreference',
    'getProjectAutoLinkRunEntitiesPreference',
    'applyProjectAutoLinkRunEntitiesPreference',
    'downloadBlobAsAttachment',
    `
      const globalThis = global;
      const APP_CONFIG = global.APP_CONFIG || {};
      window.bindPressable = bindPressable;
      window.bindDismissible = global.bindDismissible;
      window.bindMobileSheet = global.bindMobileSheet;
      window.enhanceAppSelects = global.enhanceAppSelects;
      ${ENTITY_METADATA_SRC}
      ${UI_ACTION_SHEET_SRC}
      ${ATLAS_ENTITY_ROW_SRC}
      global.openActionSheet = window.openActionSheet;
      global.closeActionSheet = window.closeActionSheet;
      ${PROJECT_TARGET_VALIDATION_SRC}
      ${PROJECT_WORKSPACE_CONSTANTS_SRC}
      ${PROJECT_WORKSPACE_STATE_SRC}
      ${PROJECT_ACTIVE_CONTEXT_SRC}
      ${PROJECT_SHARED_UI_SRC}
      ${PROJECT_DETAILS_SRC}
      ${PROJECT_LIST_SRC}
      ${PROJECT_NAVIGATION_SRC}
      ${PROJECT_ENTITY_EDITOR_SRC}
      ${PROJECT_WORKSPACE_ACTIONS_SRC}
      ${PROJECT_WORKSPACE_SHELL_SRC}
      ${PROJECT_WORKSPACE_LIFECYCLE_SRC}
      ${PROJECT_WORKSPACE_RENDERER_SRC}
      ${PROJECT_WORKSPACE_BOOTSTRAP_SRC}
      ${PROJECT_NESTED_SHEETS_SRC}
      ${PROJECT_WORKSPACE_EVENTS_SRC}
      ${PROJECT_TARGETS_SRC}
      ${PROJECT_RUNS_SRC}
      ${PROJECT_MOBILE_COMPARE_SRC}
      ${PROJECT_MOBILE_SHELL_SRC}
      ${PROJECT_MOBILE_DETAIL_SRC}
      ${PROJECT_FINDINGS_DATA_SRC}
      ${PROJECT_FILTERS_SRC}
      ${PROJECT_ENTITIES_SRC}
      ${PROJECT_FINDINGS_SRC}
      ${PROJECT_FINDINGS_BOARD_SRC}
      ${FINDINGS_BOARD_MODAL_SRC}
      ${PROJECT_ARTIFACTS_SRC}
      ${PROJECT_PACKAGES_SRC}
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
    showToast,
    getProjectAutoLinkExternalRunsPreference,
    applyProjectAutoLinkExternalRunsPreference,
    getProjectAutoLinkRunEntitiesPreference,
    applyProjectAutoLinkRunEntitiesPreference,
    downloadBlobAsAttachment,
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
    showToast,
    bindDismissible,
    bindMobileSheet,
    projectFindingsData: global.DarklabProjectFindingsData,
    openProjectWorkspace: global.openProjectWorkspace,
    refreshProjectWorkspace: global.refreshProjectWorkspace,
    enhanceAppSelects,
    syncAppSelect,
  }
}

describe('shell chrome rail sections', () => {
  it('opens Status Monitor and Findings Board from the desktop rail nav item', async () => {
    const openStatusMonitor = vi.fn(() => Promise.resolve(true))
    const apiFetch = vi.fn((url) => {
      if (String(url).startsWith('/atlas/findings')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            findings: [{
              id: 'finding-rail',
              title: 'Rail finding',
              raw_line: '443/tcp open https',
              review_state: 'new',
              run_id: 'run-rail',
              run_command: 'nmap rail.example',
            }],
            total: 1,
            has_more: false,
          }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const bindDismissible = vi.fn((_el, options) => {
      const keyHandler = (event) => {
        if (event.key === 'Escape' && options.isOpen()) {
          event.preventDefault()
          options.onClose()
        }
      }
      document.addEventListener('keydown', keyHandler)
      return {
        dispose: vi.fn(() => {
          document.removeEventListener('keydown', keyHandler)
        }),
      }
    })
    const shell = loadShellChrome({ apiFetch, openStatusMonitor, bindDismissible })
    const nav = document.getElementById('rail-nav')
    const rail = document.getElementById('rail')
    const trigger = document.getElementById('rail-more-btn')
    const menu = document.getElementById('rail-more-menu')

    rail.classList.add('rail-collapsed')
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 360 })
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 240 })
    Object.defineProperty(trigger, 'getBoundingClientRect', {
      configurable: true,
      value: () => ({ top: 4, right: 44, height: 34, width: 44, bottom: 38, left: 0 }),
    })
    Object.defineProperty(menu, 'offsetWidth', { configurable: true, value: 220 })
    Object.defineProperty(menu, 'offsetHeight', { configurable: true, value: 360 })

    trigger.click()
    expect(menu.classList.contains('u-hidden')).toBe(false)
    expect(menu.style.position).toBe('fixed')
    expect(menu.style.top).toBe('8px')
    expect(menu.style.left).toBe('52px')
    expect(menu.style.maxHeight).toBe('224px')
    expect(menu.style.overflowY).toBe('auto')
    expect(menu.style.getPropertyValue('--rail-more-arrow-y')).toBe('18px')
    nav.querySelector('[data-action="status-monitor"]').click()

    expect(shell.openStatusMonitor).toHaveBeenCalledWith({ source: 'rail' })
    expect(nav.querySelector('#rail-more-menu').classList.contains('u-hidden')).toBe(true)

    trigger.click()
    nav.querySelector('[data-action="findings-board"]').click()
    await tick()
    await tick()
    expect(document.getElementById('findings-board-overlay').classList.contains('open')).toBe(true)
    expect(bindDismissible).toHaveBeenCalledWith(
      document.getElementById('findings-board-overlay'),
      expect.objectContaining({ level: 'modal' }),
    )
    expect(apiFetch).toHaveBeenCalledWith(expect.stringMatching(/^\/atlas\/findings\?/), { cache: 'no-store' })
    expect(document.getElementById('findings-board-body').textContent).toContain('Rail finding')
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await tick()
    expect(document.getElementById('findings-board-overlay').classList.contains('open')).toBe(false)
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
  it('keeps inactive project list pagination visually hidden', () => {
    expect(PROJECTS_CSS).toMatch(/\.project-workspace-pagination\.u-hidden\s*\{\s*display:\s*none;/)
  })

  it('labels only the current active project in the project list', async () => {
    let activeProjectId = 'project-1'
    const projects = [
      { id: 'project-3', name: 'zulu.test', status: 'active' },
      { id: 'project-2', name: 'example.net', status: 'active' },
      {
        id: 'project-1',
        name: 'darklab.sh',
        status: 'active',
        counts: { runs: 0, findings: 3, artifacts: 0, packages: 0, targets: 0, notes: 0 },
        finding_summary: { review_states: { new: 2 }, severities: { high: 1, info: 2 } },
      },
      {
        id: 'project-4',
        name: 'alpha.test',
        status: 'active',
        counts: { runs: 2, entities: 99, findings: 3, artifacts: 4, packages: 5 },
      },
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
      if (String(url).startsWith('/projects?include_archived=1')) {
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
            counts: { runs: 0, findings: 3, artifacts: 0, packages: 0, targets: 0, notes: 0 },
            finding_summary: {
              review_states: { new: 2 },
              severities: { high: 1, info: 2 },
            },
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
    expect(rowText('project-4')).toContain('2 runs')
    expect(rowText('project-4')).toContain('3 findings')
    expect(rowText('project-4')).toContain('4 artifacts')
    expect(rowText('project-4')).toContain('5 packages')
    expect(rowText('project-4')).not.toContain('99 entities')
    expect(document.querySelector('[data-project-tab="findings"]')?.textContent).toBe('Findings (3 · 2 new · 1 high)')
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

  it('pages and filters the project Details targets browser', async () => {
    const projects = [{ id: 'project-1', name: 'Target Browser', status: 'active' }]
    const targetPages = {
      'type=domain': {
        targets: [{ id: 'target-1', type: 'domain', value: 'darklab.sh', review_state: 'confirmed' }],
        total: 2,
        limit: 1,
        offset: 0,
        counts_by_type: { domain: 2, ip: 1, url: 1 },
      },
      'type=domain&offset=1': {
        targets: [{ id: 'target-2', type: 'domain', value: 'api.darklab.sh', review_state: 'confirmed' }],
        total: 2,
        limit: 1,
        offset: 1,
        counts_by_type: { domain: 2, ip: 1, url: 1 },
      },
      'q=login': {
        targets: [{ id: 'target-3', type: 'url', value: 'https://darklab.sh/login', review_state: 'confirmed' }],
        total: 1,
        limit: 50,
        offset: 0,
        counts_by_type: { url: 1 },
      },
      auto: {
        targets: [{ id: 'target-4', type: 'ip', value: '192.0.2.10', review_state: 'pending' }],
        total: 1,
        limit: 50,
        offset: 0,
        counts_by_type: { ip: 1 },
      },
    }
    let projectListFetches = 0
    const apiFetch = vi.fn((url, options = {}) => {
      if (url === '/projects/active') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ project: projects[0] }) })
      }
      if (String(url).startsWith('/projects?include_archived=1')) {
        projectListFetches += 1
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ projects }) })
      }
      if (url === '/projects/project-1/summary') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            project: projects[0],
            counts: { runs: 0, entities: 4, findings: 0, artifacts: 0, packages: 0, targets: 4, notes: 0 },
            entity_counts: { domain: 40, ip: 30, url: 20 },
            runs: [],
            targets: [],
            artifacts: [],
            packages: [],
          }),
        })
      }
      if (String(url).startsWith('/projects/project-1/targets?')) {
        const params = new URL(url, 'http://localhost').searchParams
        let page = {
          targets: [
            { id: 'target-1', type: 'domain', value: 'darklab.sh', review_state: 'confirmed' },
            { id: 'target-4', type: 'ip', value: '192.0.2.10', review_state: 'pending' },
          ],
          total: 4,
          limit: Number(params.get('limit') || 50),
          offset: Number(params.get('offset') || 0),
          counts_by_type: { domain: 2, ip: 1, url: 1 },
        }
        if (params.get('auto_discovered') === '1') page = targetPages.auto
        else if (params.get('type') === 'domain' && params.get('offset') === '1') page = targetPages['type=domain&offset=1']
        else if (params.get('type') === 'domain') page = targetPages['type=domain']
        else if (params.get('q') === 'login') page = targetPages['q=login']
        return Promise.resolve({ ok: true, json: () => Promise.resolve(page) })
      }
      if (url === '/projects/project-1/targets/target-4') {
        if (options?.method === 'DELETE') {
          targetPages.auto = {
            targets: [],
            total: 0,
            limit: 50,
            offset: 0,
            counts_by_type: {},
          }
          return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) })
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            target: { id: 'target-4', type: 'ip', value: '192.0.2.10', review_state: 'confirmed' },
          }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const showConfirm = vi.fn(() => Promise.resolve('remove'))
    const shell = loadShellChrome({ apiFetch, showConfirm })

    await shell.openProjectWorkspace()
    document.querySelector('[data-project-tab="details"]')?.click()
    await tick()
    await tick()
    expect(apiFetch).toHaveBeenCalledWith('/projects/project-1/targets?limit=50&offset=0', { cache: 'no-store' })
    expect(document.querySelector('.project-target-row')?.textContent).toContain('darklab.sh')
    const targetAllCount = () => (
      document.querySelector('.project-target-type-tab[data-project-target-type=""] .project-target-type-tab-count')?.textContent
    )
    document.querySelector('[data-project-tab="runs"]').click()
    await tick()
    await tick()
    document.querySelector('[data-project-tab="details"]').click()
    await tick()
    expect(targetAllCount()).toBe('4')

    const projectListFetchesBeforeTargetPage = projectListFetches
    document.querySelector('[data-project-target-type="domain"]').click()
    expect(targetAllCount()).toBe('4')
    await tick()
    expect(apiFetch).toHaveBeenCalledWith('/projects/project-1/targets?limit=50&offset=0&type=domain', { cache: 'no-store' })
    expect(document.querySelector('.project-target-pagination.project-workspace-pagination')?.textContent).toContain('1-1 of 2 targets')
    expect(document.querySelectorAll('.project-target-pagination.project-workspace-pagination')).toHaveLength(2)
    document.querySelector('.project-target-pagination .btn:last-child').click()
    await tick()
    expect(apiFetch).toHaveBeenCalledWith('/projects/project-1/targets?limit=50&offset=1&type=domain', { cache: 'no-store' })
    expect(projectListFetches).toBe(projectListFetchesBeforeTargetPage)
    expect(document.querySelector('.project-target-row')?.textContent).toContain('api.darklab.sh')

    const search = document.querySelector('.project-target-search')
    search.value = 'login'
    search.dispatchEvent(new Event('input', { bubbles: true }))
    await new Promise(resolve => setTimeout(resolve, 300))
    await tick()
    expect(apiFetch).toHaveBeenCalledWith('/projects/project-1/targets?limit=50&offset=0&type=domain&q=login', { cache: 'no-store' })

    document.querySelector('[data-project-target-type=""]').click()
    await tick()
    document.querySelector('.project-target-auto-toggle input').click()
    await tick()
    expect(apiFetch).toHaveBeenCalledWith('/projects/project-1/targets?limit=50&offset=0&q=login&auto_discovered=1', { cache: 'no-store' })
    const projectListFetchesBeforeConfirm = projectListFetches
    document.querySelector('[data-project-action="confirm-target"][data-target-id="target-4"]').click()
    await tick()
    await tick()
    expect(projectListFetches).toBe(projectListFetchesBeforeConfirm)
    expect(document.querySelector('.project-target-row')?.textContent).toContain('192.0.2.10')
    expect(document.querySelector('[data-project-action="confirm-target"][data-target-id="target-4"]')).toBeNull()

    const projectListFetchesBeforeDelete = projectListFetches
    document.querySelector('[data-project-action="delete-target"][data-target-id="target-4"]').click()
    await tick()
    await tick()
    expect(apiFetch).toHaveBeenCalledWith('/projects/project-1/targets/target-4', expect.objectContaining({ method: 'DELETE' }))
    expect(projectListFetches).toBe(projectListFetchesBeforeDelete)
  })

  it('renders the mobile project list with active-first rows and collapsed archived projects', async () => {
    document.body.classList.add('mobile-terminal-mode')
    const inertDescriptor = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'inert')
    if (!('inert' in HTMLElement.prototype)) {
      Object.defineProperty(HTMLElement.prototype, 'inert', {
        configurable: true,
        get() { return this.__testInert === true },
        set(value) { this.__testInert = value === true },
      })
    }
    const projects = [
      {
        id: 'project-3',
        name: 'zulu.test',
        status: 'archived',
        labels: [{ label: 'old' }],
      },
      {
        id: 'project-1',
        name: 'alpha.test',
        status: 'active',
        labels: [{ label: 'web' }, { label: 'prod' }, { label: 'retest' }, { label: 'handoff' }],
      },
      {
        id: 'project-2',
        name: 'darklab.sh',
        status: 'active',
        labels: [{ label: 'current' }],
      },
    ]
    const apiFetch = vi.fn((url) => {
      if (url === '/projects/active') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ project: projects[2] }),
        })
      }
      if (String(url).startsWith('/projects?include_archived=1')) {
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
            counts: { runs: projectId === 'project-1' ? 2 : 0, findings: 1, artifacts: 0, packages: 0, targets: 1, notes: 0 },
            runs: [],
            targets: [],
            artifacts: [],
            packages: [],
          }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })

    try {
      const shell = loadShellChrome({ apiFetch })
      await shell.openProjectWorkspace()
      await tick()
      await tick()

      const mobileRows = [...document.querySelectorAll('.project-mobile-row')]
      expect(mobileRows.map(row => row.dataset.projectId)).toEqual(['project-2', 'project-1'])
      expect(mobileRows.every(row => row.classList.contains('panel-row'))).toBe(true)
      expect(mobileRows.every(row => !row.hasAttribute('role'))).toBe(true)
      expect(mobileRows.every(row => row.tabIndex < 0)).toBe(true)
      expect(mobileRows.every(row => !row.dataset.projectMobileAction)).toBe(true)
      const firstProjectTarget = mobileRows[0].querySelector('.project-mobile-row-main')
      expect(firstProjectTarget.tagName).toBe('BUTTON')
      expect(firstProjectTarget.classList.contains('control-row')).toBe(true)
      expect(firstProjectTarget.dataset.projectMobileAction).toBe('open-project')
      expect(firstProjectTarget.dataset.pressableBound).toBe('1')
      expect(document.getElementById('project-mobile-body').textContent).toContain('Archived (1)')
      expect(document.getElementById('project-mobile-body').textContent).not.toContain('zulu.test')
      expect(document.querySelector('[data-project-id="project-1"]').closest('.project-mobile-row').textContent).toContain('+1')
      expect(document.querySelector('[data-project-mobile-action="project-menu"][data-project-id="project-1"]').textContent).toBe('☰')

      document
        .querySelector('.project-mobile-row[data-project-id="project-1"]')
        .dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await tick()
      expect(document.getElementById('project-mobile-list-view').classList.contains('u-hidden')).toBe(true)
      expect(document.getElementById('project-mobile-detail-view').classList.contains('u-hidden')).toBe(false)
      document.querySelector('[data-project-mobile-action="back-to-list"]').click()
      await tick()
      expect(document.getElementById('project-mobile-list-view').classList.contains('u-hidden')).toBe(false)

      const findingsChip = document.querySelector('[data-project-id="project-1"][data-project-mobile-tab="findings"]')
      findingsChip.click()
      await tick()

      expect(document.querySelector('.project-mobile-row.is-selected .project-mobile-name').textContent).toBe('alpha.test')

      document.querySelector('[data-project-mobile-action="toggle-archived"]').click()
      await tick()
      expect(document.getElementById('project-mobile-body').textContent).toContain('zulu.test')

      document.querySelector('[data-project-mobile-action="project-menu"][data-project-id="project-1"]').click()
      await tick()
      const actionSheet = document.getElementById('action-sheet-overlay')
      expect(actionSheet.classList.contains('open')).toBe(true)
      expect(actionSheet.textContent).toContain('Edit metadata')
      const actionSheetItems = actionSheet.querySelector('.action-sheet-items')
      expect(actionSheetItems.classList.contains('bottom-sheet-body')).toBe(true)
      expect(actionSheetItems.classList.contains('nice-scroll')).toBe(true)
      actionSheet.querySelector('[data-project-action="edit-project-metadata"]').click()
      await tick()
      expect(document.getElementById('project-entity-editor-overlay').classList.contains('open')).toBe(true)
      expect(document.getElementById('project-workspace-modal').inert).toBe(true)
      expect(document.getElementById('project-workspace-modal').getAttribute('aria-hidden')).toBe('true')
      document.querySelector('.project-entity-editor-cancel').click()
      await tick()
      expect(document.getElementById('project-workspace-modal').inert).toBe(false)
      expect(document.getElementById('project-workspace-modal').getAttribute('aria-hidden')).toBe('false')

      document.querySelector('.project-mobile-row[data-project-id="project-2"] .project-mobile-row-main').click()
      await tick()
      expect(document.getElementById('project-mobile-detail-view').classList.contains('u-hidden')).toBe(false)
      expect(document.getElementById('project-mobile-detail-topbar').textContent).toContain('darklab.sh')
      const summaryMenu = document.querySelector('.project-mobile-summary-menu-btn')
      expect(summaryMenu.dataset.projectId).toBe('project-2')
      expect(summaryMenu.textContent).toBe('☰')
    } finally {
      document.body.classList.remove('mobile-terminal-mode')
      if (inertDescriptor) {
        Object.defineProperty(HTMLElement.prototype, 'inert', inertDescriptor)
      } else {
        delete HTMLElement.prototype.inert
      }
    }
  })

  it('creates projects from the mobile create sheet', async () => {
    document.body.classList.add('mobile-terminal-mode')
    let activeProjectId = ''
    const projects = []
    const apiFetch = vi.fn((url, options = {}) => {
      if (url === '/projects' && options.method === 'POST') {
        const project = { id: 'project-mobile', name: JSON.parse(options.body).name, status: 'active' }
        projects.push(project)
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ project }) })
      }
      if (url === '/projects/active' && options.method === 'POST') {
        activeProjectId = JSON.parse(options.body).project_id
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ ok: true }) })
      }
      if (url === '/projects/active') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ project: projects.find(project => project.id === activeProjectId) || null }),
        })
      }
      if (String(url).startsWith('/projects?include_archived=1')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ projects }) })
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

    try {
      const shell = loadShellChrome({ apiFetch })
      await shell.openProjectWorkspace()
      await tick()

      document.querySelector('[data-project-mobile-action="new-project"]').click()
      await tick()
      expect(document.getElementById('project-mobile-create-form').classList.contains('u-hidden')).toBe(false)

      document.getElementById('project-mobile-name').value = 'Mobile Project'
      document.getElementById('project-mobile-create-form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
      await tick()
      await tick()

      expect(activeProjectId).toBe('project-mobile')
      expect(document.getElementById('project-mobile-create-form').classList.contains('u-hidden')).toBe(true)
      expect(document.getElementById('project-mobile-body').textContent).toContain('Mobile Project')
    } finally {
      document.body.classList.remove('mobile-terminal-mode')
    }
  })

  it('drills into mobile project detail tabs and returns to the list', async () => {
    document.body.classList.add('mobile-terminal-mode')
    const projects = [{ id: 'project-1', name: 'darklab.sh', status: 'active' }]
    const apiFetch = vi.fn((url) => {
      if (url === '/projects/active') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ project: projects[0] }),
        })
      }
      if (String(url).startsWith('/projects?include_archived=1')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ projects }) })
      }
      if (url === '/projects/project-1/summary') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            project: projects[0],
            counts: { runs: 1001, findings: 5, artifacts: 9, packages: 2, targets: 1, notes: 0 },
            runs: [],
            targets: [],
            artifacts: [],
            packages: [],
          }),
        })
      }
      if (String(url).startsWith('/projects/project-1/targets?')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            targets: targetStates.map(target => ({
              ...target,
              labels: labelObjects('target', target.id),
              note: noteObject('target', target.id),
            })),
            total: targetStates.length,
            limit: 50,
            offset: 0,
            counts_by_type: { domain: 2, ip: 1 },
          }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })

    try {
      const shell = loadShellChrome({ apiFetch, appConfig: { workspace_enabled: false } })
      await shell.openProjectWorkspace()
      await tick()
      await tick()

      document.querySelector('[data-project-mobile-action="open-project"][data-project-id="project-1"]').click()
      await tick()

      expect(document.getElementById('project-mobile-list-view').classList.contains('u-hidden')).toBe(true)
      expect(document.getElementById('project-mobile-detail-view').classList.contains('u-hidden')).toBe(false)
      expect(document.getElementById('project-mobile-detail-topbar').textContent).toContain('darklab.sh')
      expect(document.querySelector('.project-mobile-summary-menu-btn')?.dataset.projectId).toBe('project-1')
      expect(document.getElementById('project-mobile-tabs').textContent).toContain('999+')
      expect(document.getElementById('project-mobile-tabs').textContent).not.toContain('Artifacts')

      document.querySelector('[data-project-mobile-detail-tab="packages"]').click()
      await tick()
      expect(document.getElementById('project-mobile-detail-body').textContent).toContain('No evidence packages yet')
      expect(document.getElementById('project-mobile-detail-body').querySelector('[data-project-action="package-wizard-open"]')).not.toBeNull()

      document.querySelector('[data-project-mobile-action="back-to-list"]').click()
      await tick()
      expect(document.getElementById('project-mobile-list-view').classList.contains('u-hidden')).toBe(false)
      expect(document.getElementById('project-mobile-detail-view').classList.contains('u-hidden')).toBe(true)
    } finally {
      document.body.classList.remove('mobile-terminal-mode')
    }
  })

  it('renders mobile project tab content with mobile row actions', async () => {
    document.body.classList.add('mobile-terminal-mode')
    const projectNote = 'Project note from mobile test with extra handoff context, timeline notes, owner follow-up, and validation details.'
    const project = {
      id: 'project-1',
      name: 'darklab.sh',
      status: 'active',
      labels: [{ label: 'client' }, { label: 'handoff' }],
      note: { body: projectNote },
    }
    const summary = {
      project,
      counts: { runs: 1, findings: 1, artifacts: 2, packages: 1, targets: 1, notes: 4 },
      runs: [{
        id: 'run-1',
        command: 'nmap darklab.sh',
        started: '2026-05-09T12:00:00Z',
        created: '2026-05-09T12:01:00Z',
        exit_code: 0,
        output_line_count: 8,
        labels: [{ label: 'reviewed' }],
        note: { body: 'Run note' },
      }],
      targets: [{
        id: 'target-1',
        type: 'domain',
        value: 'darklab.sh',
        review_state: 'confirmed',
        labels: [{ label: 'prod' }],
        note: { body: 'Target note' },
      }],
      artifacts: [{
        id: 'artifact-1',
        run_id: 'run-1',
        workspace_path: 'reports/run.txt',
        display_name: 'run.txt',
        kind: 'output',
        content_type: 'text/plain',
        byte_size: 24,
        created: '2026-05-09T12:02:00Z',
        file_status: 'available',
        file_available: true,
        labels: [{ label: 'evidence' }],
        note: { body: 'Artifact note' },
      }, {
        id: 'artifact-2',
        run_id: 'run-1',
        workspace_path: 'reports/missing.txt',
        display_name: 'missing.txt',
        kind: 'output',
        content_type: 'text/plain',
        byte_size: 12,
        created: '2026-05-09T12:03:00Z',
        file_status: 'missing',
        file_available: false,
        file_status_detail: 'workspace file is missing',
      }],
      packages: [{
        id: 'package-1',
        name: 'Evidence Package',
        description: 'Ready for handoff',
        redaction_mode: 'raw',
        include_artifacts: true,
        updated: '2026-05-09T12:04:00Z',
        labels: [{ label: 'handoff' }],
        note: { body: 'Package note' },
        manifest: {
          preset: 'evidence',
          counts: { runs: 1, findings: 1, artifacts: 1, targets: 1 },
          estimated_archive: { estimated_uncompressed_bytes: 24 },
        },
      }],
    }
    const apiFetch = vi.fn((url) => {
      if (url === '/projects/active') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ project }) })
      }
      if (String(url).startsWith('/projects?include_archived=1')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ projects: [project] }) })
      }
      if (url === '/projects/project-1/summary') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(summary) })
      }
      if (String(url).startsWith('/projects/project-1/findings')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            total: 1,
            limit: 50,
            offset: 0,
            has_more: false,
            findings: [{
              id: 'finding-1',
              run_id: 'run-1',
              run_command: 'nmap darklab.sh',
              title: '443 open',
              raw_line: '443/tcp open https',
              line_number: 4,
              scope: 'finding',
              review_state: 'triaged',
              labels: [{ label: 'important' }],
              note: { body: 'Finding note' },
            }],
          }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })

    try {
      const shell = loadShellChrome({ apiFetch })
      await shell.openProjectWorkspace()
      await tick()
      await tick()

      document.querySelector('[data-project-mobile-action="open-project"][data-project-id="project-1"]').click()
      await tick()
      await tick()

      const detailBody = document.getElementById('project-mobile-detail-body')
      const summaryPanel = detailBody.querySelector('.project-mobile-detail-panel')
      const summaryMenu = summaryPanel.querySelector('.project-mobile-summary-menu-btn')
      expect(summaryMenu.dataset.projectId).toBe('project-1')
      expect(summaryMenu.textContent).toBe('☰')
      const summaryNote = summaryPanel.querySelector('.project-mobile-note-preview')
      const summaryNoteToggle = summaryPanel.querySelector('[data-project-mobile-note-toggle]')
      expect(summaryNote.textContent).toContain(`${projectNote.slice(0, 100).trimEnd()}...`)
      expect(summaryNote.textContent).not.toContain('validation details')
      expect(summaryNoteToggle.textContent).toBe('Expand')
      expect(summaryNoteToggle.getAttribute('aria-expanded')).toBe('false')
      summaryNoteToggle.click()
      expect(summaryNote.textContent).toContain(projectNote)
      expect(summaryNoteToggle.textContent).toBe('Collapse')
      expect(summaryNoteToggle.getAttribute('aria-expanded')).toBe('true')
      summaryNoteToggle.click()
      expect(summaryNote.textContent).not.toContain('validation details')
      const detailPanelHeadings = [...detailBody.querySelectorAll('.project-mobile-detail-panel > h3')]
        .map(item => item.textContent)
      expect(detailPanelHeadings).not.toContain('Labels')
      expect(detailPanelHeadings).not.toContain('Notes')
      expect(detailBody.querySelectorAll('.project-mobile-note-preview')).toHaveLength(1)
      expect(detailBody.textContent).toContain('darklab.sh')
      expect(detailBody.querySelector('[data-project-action="new-target"]')).not.toBeNull()

      document.querySelector('[data-project-mobile-detail-tab="runs"]').click()
      await tick()
      expect(detailBody.textContent).toContain('nmap darklab.sh')
      expect(detailBody.textContent).toContain('1 finding')
      expect(detailBody.textContent).toContain('2 artifacts')
      const runDetailLines = [...detailBody.querySelectorAll('.project-mobile-run-row .project-mobile-content-detail')]
        .map(item => item.textContent)
      expect(runDetailLines).toContain('exit 0 · 8 output lines')
      expect(runDetailLines).toContain('1 finding · 2 artifacts')
      const runMenu = detailBody.querySelector('.project-mobile-row-menu-trigger')
      expect(runMenu.textContent).toBe('☰')
      runMenu.click()
      await tick()
      const actionSheet = document.getElementById('action-sheet-overlay')
      expect(actionSheet.classList.contains('open')).toBe(true)
      expect(actionSheet.querySelector('[data-project-action="edit-run-metadata"]')).not.toBeNull()
      expect(actionSheet.querySelector('[data-project-action="open-run"]')).not.toBeNull()
      expect(actionSheet.querySelector('[data-project-action="unlink-run"]')).not.toBeNull()
      actionSheet.click()
      await tick()
      expect(actionSheet.classList.contains('open')).toBe(false)
      expect(shell.restoreHistoryRunIntoTab).not.toHaveBeenCalled()

      document.querySelector('[data-project-mobile-detail-tab="findings"]').click()
      await tick()
      await tick()
      expect(detailBody.textContent).toContain('443 open')
      expect(detailBody.textContent).toContain('443/tcp open https')
      expect(detailBody.querySelector('[data-project-action="open-finding"]')).not.toBeNull()
      detailBody.querySelector('.project-mobile-row-menu-trigger').click()
      await tick()
      const reviewSelect = actionSheet.querySelector('[data-project-review-state]')
      expect(reviewSelect).not.toBeNull()
      const actionSheetItems = actionSheet.querySelector('.action-sheet-items')
      expect(actionSheetItems.classList.contains('bottom-sheet-body')).toBe(true)
      expect(actionSheetItems.classList.contains('nice-scroll')).toBe(true)
      expect(shell.enhanceAppSelects).toHaveBeenCalledWith(actionSheetItems)
      expect(detailBody.querySelector('.project-mobile-row-badge')?.textContent).toBe('triaged')
      reviewSelect.value = 'reviewed'
      reviewSelect.dispatchEvent(new Event('change', { bubbles: true }))
      await tick()
      await tick()
      expect(apiFetch).toHaveBeenCalledWith('/findings/finding-1/review', expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ review_state: 'reviewed' }),
      }))
      expect(detailBody.querySelector('.project-mobile-row-badge')?.textContent).toBe('reviewed')
      actionSheet.click()
      await tick()
      expect(shell.enhanceAppSelects).toHaveBeenCalledWith(detailBody)
      expect(detailBody.querySelector('[data-project-finding-group-toggle]')).toBeNull()
      expect(detailBody.textContent).toContain('nmap darklab.sh')
      shell.restoreHistoryRunIntoTab.mockClear()
      detailBody.querySelector('[data-project-action="open-finding"]').click()
      await tick()
      expect(shell.restoreHistoryRunIntoTab).toHaveBeenCalledWith(
        {
          id: 'run-1',
          command: 'nmap darklab.sh',
          full_output_available: true,
        },
        {
          hidePanelOnSuccess: false,
          highlightLineIndex: 4,
        },
      )
      expect(document.getElementById('project-workspace-overlay').classList.contains('open')).toBe(false)

      await shell.openProjectWorkspace()
      document.querySelector('[data-project-mobile-action="open-project"][data-project-id="project-1"]').click()
      await tick()
      await tick()
      document.querySelector('[data-project-mobile-detail-tab="artifacts"]').click()
      await tick()

      expect(detailBody.textContent).toContain('run.txt')
      expect(detailBody.textContent).toContain('available')
      expect(detailBody.textContent).toContain('missing')
      expect(detailBody.querySelector('.project-mobile-row-badge.is-missing')?.textContent).toBe('missing')
      const artifactDetailLines = [...detailBody.querySelectorAll('.project-mobile-content-detail')]
        .map(item => item.textContent)
      expect(artifactDetailLines).toContain('output · text/plain')
      expect(artifactDetailLines).toContain('workspace file is missing')
      detailBody.querySelector('.project-mobile-row-menu-trigger').click()
      await tick()
      expect(actionSheet.querySelector('[data-project-action="artifact-preview"]')).not.toBeNull()
      actionSheet.click()
      await tick()
      detailBody.querySelector('[data-project-artifact-group-toggle]').click()
      await tick()
      expect(detailBody.querySelector('.project-artifacts-group .project-mobile-group-body').hidden).toBe(true)

      document.querySelector('[data-project-mobile-detail-tab="packages"]').click()
      await tick()
      expect(detailBody.textContent).toContain('Evidence Package')
      expect(detailBody.textContent).toContain('1 run')
      const packageDetailLines = [...detailBody.querySelectorAll('.project-mobile-content-detail')]
        .map(item => item.textContent)
      expect(packageDetailLines).toContain('Ready for handoff · 1 run · 1 finding · 1 artifact · 1 target')
      expect(packageDetailLines.some(text => text.startsWith('Updated '))).toBe(true)
      expect(packageDetailLines.some(text => text.includes('· Updated '))).toBe(false)
      expect(detailBody.querySelector('[data-project-action="package-wizard-open"]')).not.toBeNull()
      detailBody.querySelector('.project-mobile-row-menu-trigger').click()
      await tick()
      expect(actionSheet.querySelector('[data-project-action="package-manifest"]')).not.toBeNull()
    } finally {
      document.body.classList.remove('mobile-terminal-mode')
    }
  })

  it('opens the mobile project compare stepper and runs a baseline label comparison', async () => {
    document.body.classList.add('mobile-terminal-mode')
    const fetchAndRenderHistoryComparison = vi.fn()
    const project = { id: 'project-1', name: 'darklab.sh', status: 'active' }
    const summary = {
      project,
      counts: { runs: 2, findings: 0, artifacts: 0, packages: 0, targets: 0 },
      runs: [{
        id: 'run-left',
        command: 'nmap darklab.sh',
        started: '2026-05-09T12:00:00Z',
        created: '2026-05-09T12:01:00Z',
        exit_code: 0,
        output_line_count: 8,
      }, {
        id: 'run-base',
        command: 'nmap darklab.sh --top-ports 100',
        started: '2026-05-09T12:03:00Z',
        created: '2026-05-09T12:04:00Z',
        exit_code: 0,
        output_line_count: 6,
        labels: [{ label: 'baseline' }],
      }],
    }
    const apiFetch = vi.fn((url) => {
      if (url === '/projects/active') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ project }) })
      }
      if (String(url).startsWith('/projects?include_archived=1')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ projects: [project] }) })
      }
      if (url === '/projects/project-1/summary') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(summary) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })

    try {
      const shell = loadShellChrome({ apiFetch, fetchAndRenderHistoryComparison })
      await shell.openProjectWorkspace()
      await tick()
      await tick()

      document.querySelector('[data-project-mobile-action="open-project"][data-project-id="project-1"]').click()
      await tick()
      await tick()
      document.querySelector('[data-project-mobile-detail-tab="runs"]').click()
      await tick()

      document.querySelector('[data-project-action="mobile-compare-runs"]').click()
      await tick()
      const overlay = document.getElementById('project-mobile-compare-overlay')
      expect(overlay.classList.contains('open')).toBe(true)
      expect(overlay.textContent).toContain('Left run')
      expect(overlay.querySelector('.project-mobile-compare-option.is-active')?.textContent).toContain('nmap darklab.sh')
      overlay.querySelector('.project-mobile-compare-footer .btn-primary').click()
      await tick()
      expect(overlay.textContent).toContain('Compare against')
      expect(overlay.querySelector('.project-mobile-compare-option.is-active')?.textContent).toBe('Against run')
      Array.from(overlay.querySelectorAll('.project-mobile-compare-option'))
        .find(btn => btn.textContent === 'Against label')
        .click()
      await tick()
      expect(overlay.querySelector('.project-mobile-compare-option.is-active')?.textContent).toBe('Against label')
      overlay.querySelector('.project-mobile-compare-footer .btn-primary').click()
      await tick()
      expect(overlay.textContent).toContain('Choose a baseline label')
      expect(overlay.querySelector('.project-mobile-compare-option.is-active')?.textContent).toBe('baseline')
      overlay.querySelector('.project-mobile-compare-footer .btn-primary').click()
      await tick()

      expect(fetchAndRenderHistoryComparison).toHaveBeenCalledWith('run-left', 'baseline:baseline', {
        url: '/history/compare?left=run-left&project_id=project-1&baseline_label=baseline',
      })
      expect(overlay.classList.contains('open')).toBe(false)
    } finally {
      document.body.classList.remove('mobile-terminal-mode')
    }
  })

  it('opens projects from the active project HUD chip', async () => {
    const apiFetch = vi.fn((url) => {
      if (url === '/projects/active') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ project: { id: 'project-1', name: 'darklab.sh', status: 'active' } }),
        })
      }
      if (String(url).startsWith('/projects?include_archived=1')) {
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
    expect(apiFetch).toHaveBeenCalledWith(
      expect.stringContaining('/projects?include_archived=1'),
      { cache: 'no-store' },
    )
  })

  it('hides project detail inputs when no projects exist', async () => {
    const apiFetch = vi.fn((url) => {
      if (url === '/projects/active') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ project: null }) })
      }
      if (String(url).startsWith('/projects?include_archived=1')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ projects: [] }) })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const shell = loadShellChrome({ apiFetch })

    await shell.openProjectWorkspace()
    await tick()
    await tick()

    expect(document.getElementById('project-workspace-body').textContent).toContain('No projects yet')
    expect(document.getElementById('project-explorer-body').textContent).toContain('Create or select a project')
    expect(document.getElementById('project-notes-form').classList.contains('u-hidden')).toBe(true)
    expect(document.getElementById('project-labels-form').classList.contains('u-hidden')).toBe(true)
    expect(document.getElementById('project-labels-input').value).toBe('')
    expect(document.getElementById('project-notes-input').value).toBe('')
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
      if (String(url).startsWith('/projects?include_archived=1')) {
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
      if (String(url).startsWith('/projects?include_archived=1')) {
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
    expect(shell.showToast).toHaveBeenCalledWith('Project unarchived.', 'success')
    expect(document.getElementById('project-workspace-message').classList.contains('u-hidden')).toBe(true)
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
      if (String(url).startsWith('/projects?include_archived=1')) {
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
    expect(shell.showToast).toHaveBeenCalledWith('Project deleted.', 'success')
    expect(document.getElementById('project-workspace-message').classList.contains('u-hidden')).toBe(true)
  })

  it('toggles the active project external run capture preference', async () => {
    const apiFetch = vi.fn((url) => {
      if (url === '/projects/active') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ project: { id: 'project-1', name: 'darklab.sh' } }),
        })
      }
      if (String(url).startsWith('/projects?include_archived=1')) {
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
      if (String(url).startsWith('/projects?include_archived=1')) {
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
    typeSelect.value = 'url'
    typeSelect.dispatchEvent(new Event('change', { bubbles: true }))
    expect(valueInput.placeholder).toBe('https://target.example.com/path')
    expect(valueHelp.textContent).toContain('https://darklab.sh')
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
      if (String(url).startsWith('/projects?include_archived=1')) {
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
    expect(notesInput.maxLength).toBe(20000)

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

    typeSelect.value = 'ip'
    typeSelect.dispatchEvent(new Event('change', { bubbles: true }))
    valueInput.value = '999.0.0.1'
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await tick()
    expect(valueError.textContent).toContain('Use a single IPv4 or IPv6 address')
    expect(apiFetch.mock.calls.some(([url, options]) => url === '/projects/project-1/targets' && options?.method === 'POST')).toBe(false)

    valueInput.value = '192.0.2.10'
    notesInput.value = 'Scope notes'
    notesInput.dispatchEvent(new Event('input', { bubbles: true }))
    expect(notesInput.getAttribute('aria-invalid')).toBe('false')
    expect(valueError.classList.contains('u-hidden')).toBe(true)

    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await tick()
    expect(apiFetch).toHaveBeenCalledWith('/projects/project-1/targets', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({
        type: 'ip',
        value: '192.0.2.10',
      }),
    }))
    expect(apiFetch).toHaveBeenCalledWith('/entities/target/target-1/note', expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({ body: 'Scope notes' }),
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
      if (String(url).startsWith('/projects?include_archived=1')) {
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
      if (String(url).startsWith('/projects/project-1/findings')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            findings: projectFindings,
            total: projectFindings.length,
            limit: 50,
            offset: 0,
            has_more: false,
            group_counts: {
              'nuclei old.example': 1,
              'httpx new.example': 200,
            },
          }),
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
          json: () => Promise.resolve({
            project: {
              id: 'project-1',
              name: 'darklab.sh',
              note: { body: 'Initial notes' },
            },
          }),
        })
      }
      if (String(url).startsWith('/projects?include_archived=1')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            projects: [{
              id: 'project-1',
              name: 'darklab.sh',
              status: 'active',
              note: { body: 'Initial notes' },
            }],
          }),
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
            project: {
              id: 'project-1',
              name: 'darklab.sh',
              status: 'active',
              note: { body: JSON.parse(options.body).notes },
            },
          }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const shell = loadShellChrome({ apiFetch })

    await shell.openProjectWorkspace()
    const input = document.getElementById('project-notes-input')
    expect(input.value).toBe('Initial notes')

    vi.useFakeTimers()
    try {
      const flushNotesSave = async () => {
        for (let index = 0; index < 20; index += 1) {
          await Promise.resolve()
        }
      }
      input.value = 'Updated notes'
      input.dispatchEvent(new Event('input', { bubbles: true }))
      await vi.advanceTimersByTimeAsync(450)
      await flushNotesSave()
      await vi.waitFor(() => expect(apiFetch).toHaveBeenCalledWith('/projects/project-1', expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ notes: 'Updated notes' }),
      })))
      await vi.waitFor(() => expect(shell.showToast).toHaveBeenCalledWith('Project notes saved.', 'success'))
    } finally {
      vi.useRealTimers()
    }

    expect(apiFetch).toHaveBeenCalledWith('/projects/project-1', expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({ notes: 'Updated notes' }),
    }))
  })

  it('edits project labels from the details tab', async () => {
    const apiFetch = vi.fn((url, options = {}) => {
      if (url === '/projects/active') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            project: {
              id: 'project-1',
              name: 'darklab.sh',
              notes: '',
              labels: [{ label: 'old-label' }],
            },
          }),
        })
      }
      if (String(url).startsWith('/projects?include_archived=1')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            projects: [{
              id: 'project-1',
              name: 'darklab.sh',
              status: 'active',
              notes: '',
              labels: [{ label: 'old-label' }],
            }, {
              id: 'project-2',
              name: 'Other project',
              status: 'active',
              notes: '',
              labels: [],
            }],
          }),
        })
      }
      if (url === '/projects/project-1/summary') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            project: {
              id: 'project-1',
              name: 'darklab.sh',
              status: 'active',
              notes: '',
              labels: [{ label: 'old-label' }],
            },
            counts: { runs: 0, findings: 0, artifacts: 0, packages: 0, targets: 0, notes: 0 },
            runs: [],
            targets: [],
            artifacts: [],
            packages: [],
          }),
        })
      }
      if (url === '/projects/project-2/summary') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            project: {
              id: 'project-2',
              name: 'Other project',
              status: 'active',
              notes: '',
              labels: [],
            },
            counts: { runs: 0, findings: 0, artifacts: 0, packages: 0, targets: 0, notes: 0 },
            runs: [],
            targets: [],
            artifacts: [],
            packages: [],
          }),
        })
      }
      if (url === '/entities/project/project-1/labels' && !options.method) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ labels: [{ label: 'old-label' }] }),
        })
      }
      if (url === '/entities/project/project-1/labels' && options.method === 'DELETE') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ deleted: true }) })
      }
      if (url === '/entities/project/project-1/labels' && options.method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ label: { label: JSON.parse(options.body).label } }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const shell = loadShellChrome({ apiFetch })

    await shell.openProjectWorkspace()
    await tick()
    const flushLabelsSave = async () => {
      for (let index = 0; index < 20; index += 1) {
        await Promise.resolve()
      }
    }
    const input = document.getElementById('project-labels-input')

    expect(input.value).toBe('old-label')
    expect(document.querySelector('.project-label-chips')?.textContent).toContain('old-label')

    vi.useFakeTimers()
    try {
      input.value = 'important, retest, important'
      document.getElementById('project-labels-form')
        .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
      await flushLabelsSave()

      expect(apiFetch).toHaveBeenCalledWith('/entities/project/project-1/labels', expect.objectContaining({
        method: 'DELETE',
        body: JSON.stringify({ label: 'old-label' }),
      }))
      expect(apiFetch).toHaveBeenCalledWith('/entities/project/project-1/labels', expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ label: 'important' }),
      }))
      expect(apiFetch).toHaveBeenCalledWith('/entities/project/project-1/labels', expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ label: 'retest' }),
      }))
      expect(input.value).toBe('important, retest')
      expect(shell.showToast).toHaveBeenCalledWith('Project labels saved.', 'success')
      expect(document.querySelector('.project-label-chips')?.textContent).toContain('important')
      expect(document.querySelector('.project-workspace-label-chips')?.textContent).toContain('retest')

      input.value = 'triage'
      document.getElementById('project-labels-form')
        .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
      await flushLabelsSave()
      expect(shell.showToast).toHaveBeenCalledWith('Project labels saved.', 'success')

      document.querySelector('[data-project-id="project-2"][data-project-action="select"]')
        .dispatchEvent(new Event('click', { bubbles: true, cancelable: true }))
      await flushLabelsSave()
    } finally {
      vi.useRealTimers()
    }
  })

  it('hides project artifacts and raw package artifact inclusion when Files are disabled', async () => {
    const project = { id: 'project-1', name: 'darklab.sh', status: 'active' }
    const apiFetch = vi.fn((url) => {
      if (url === '/projects/active') {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ project }) })
      }
      if (String(url).startsWith('/projects?include_archived=1')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ projects: [project] }) })
      }
      if (url === '/projects/project-1/summary') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            project,
            counts: { runs: 1, findings: 0, artifacts: 1, packages: 0, targets: 0, notes: 0 },
            runs: [{ id: 'run-1', command: 'nuclei https://darklab.sh', output_line_count: 1 }],
            targets: [],
            artifacts: [{
              id: 'artifact-1',
              run_id: 'run-1',
              workspace_path: 'reports/nuclei.json',
              display_name: 'nuclei.json',
              kind: 'output_file',
              byte_size: 2048,
              file_status: 'disabled',
              file_available: false,
              file_status_detail: 'Files are disabled on this instance',
            }],
            packages: [],
          }),
        })
      }
      if (String(url).startsWith('/projects/project-1/findings')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ findings: [], total: 0, limit: 50, offset: 0, has_more: false }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const shell = loadShellChrome({ apiFetch, appConfig: { workspace_enabled: false } })

    await shell.openProjectWorkspace()
    await tick()

    expect(document.querySelector('[data-project-tab="artifacts"]')).toBeNull()
    document.querySelector('[data-project-tab="runs"]').click()
    await tick()
    expect(document.querySelector('[data-project-action="filter-run-artifacts"]')).toBeNull()

    document.querySelector('[data-project-tab="packages"]').click()
    await tick()
    document.querySelector('[data-project-action="package-wizard-open"]').click()
    await tick()
    document.querySelector('[data-project-action="package-wizard-next"]').click()
    await tick()
    document.querySelector('[data-project-action="package-wizard-next"]').click()
    await tick()

    const rawArtifactsInput = document.querySelector('[data-project-package-include-artifacts]')
    expect(rawArtifactsInput.checked).toBe(false)
    expect(rawArtifactsInput.disabled).toBe(true)
    expect(document.getElementById('project-package-wizard-overlay').textContent)
      .toContain('Raw artifact files are unavailable because Files are disabled on this instance.')
  })

  it('opens a finding source run at the recorded line', async () => {
    const restoreHistoryRunIntoTab = vi.fn(() => Promise.resolve('tab-restored'))
    const showConfirm = vi.fn((options = {}) => {
      const bodyText = typeof options.body === 'object' ? String(options.body.text || '') : String(options.body || '')
      return bodyText.startsWith('Delete package:')
        ? Promise.resolve('delete')
        : bodyText.startsWith('Unlink')
          ? Promise.resolve('unlink')
          : Promise.resolve('remove')
    })
    const dismissibles = []
    const bindDismissible = vi.fn((el, options) => {
      dismissibles.push({ el, options })
      const closeButtons = Array.isArray(options.closeButtons) ? options.closeButtons : [options.closeButtons]
      closeButtons.filter(Boolean).forEach((btn) => {
        btn.addEventListener('click', () => {
          if (options.isOpen()) options.onClose()
        })
      })
      return { dispose: vi.fn() }
    })
    let targetStates = [
      {
        id: 'target-1',
        type: 'domain',
        value: 'darklab.sh',
      },
      {
        id: 'target-2',
        type: 'host',
        value: 'api.darklab.sh',
      },
      {
        id: 'target-3',
        type: 'ip',
        value: '107.178.109.44',
      },
    ]
    let projectEntities = [
      {
        id: 'entity-ip',
        type: 'ip',
        canonical_value: '107.178.109.44',
        value: '107.178.109.44',
        occurrence_count: 1,
        run_count: 1,
        intel_provider_count: 2,
        intel_providers: ['Shodan', 'Censys'],
        intel_last_refreshed: '2026-05-07T00:03:00Z',
      },
      {
        id: 'entity-cve',
        type: 'cve',
        canonical_value: 'CVE-2025-49113',
        value: 'CVE-2025-49113',
        occurrence_count: 1,
        run_count: 1,
        intel_provider_count: 1,
        intel_providers: ['NVD'],
        intel_last_refreshed: '2026-05-07T00:04:00Z',
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
      ['target:target-1', ['Primary domain']],
      ['target:target-2', ['API host']],
      ['target:target-3', ['Web ports']],
      ['run_file_artifact:artifact-1', []],
      ['package:pkg-1', ['handoff']],
    ])
    const entityNotes = new Map([
      ['run:run-1', 'Run note'],
      ['finding:finding-1', 'Old finding note'],
      ['target:target-1', 'Scope approved'],
      ['target:target-2', 'Secondary scope'],
      ['target:target-3', 'Common web exposure'],
      ['package:pkg-1', 'Initial package note'],
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
      if (String(url).startsWith('/projects?include_archived=1')) {
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
              entities: projectEntities.length,
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
            targets: targetStates.map(target => ({
              ...target,
              labels: labelObjects('target', target.id),
              note: noteObject('target', target.id),
            })),
            entities: projectEntities.map(entity => ({
              ...entity,
              labels: labelObjects('atlas_entity', entity.id),
              note: noteObject('atlas_entity', entity.id),
            })),
            artifacts: projectArtifacts.map(artifact => ({
              ...artifact,
              labels: labelObjects('run_file_artifact', artifact.id),
              note: noteObject('run_file_artifact', artifact.id),
            })),
            packages: projectPackages.map(pkg => ({
              ...pkg,
              labels: labelObjects('package', pkg.id),
              note: noteObject('package', pkg.id),
            })),
          }),
        })
      }
      if (String(url).startsWith('/projects/project-1/targets?')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            targets: targetStates.map(target => ({
              ...target,
              labels: labelObjects('target', target.id),
              note: noteObject('target', target.id),
            })),
            total: targetStates.length,
            limit: 50,
            offset: 0,
            counts_by_type: { domain: 1, host: 1, ip: 1 },
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
        if (payload.entity_type === 'atlas_entity') {
          const entityIds = new Set(payload.entity_ids || [payload.entity_id])
          projectEntities = projectEntities.filter(entity => !entityIds.has(entity.id))
        } else {
          projectRuns = projectRuns.filter(run => run.id !== payload.entity_id)
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ ok: true }),
        })
      }
      if (String(url).startsWith('/projects/project-1/entities')) {
        const params = new URL(`https://example.test${url}`).searchParams
        const entityRuns = new Map([
          ['entity-ip', ['run-1']],
          ['entity-cve', ['run-1']],
        ])
        const entityTargets = new Map([
          ['entity-ip', ['target-1']],
          ['entity-cve', ['target-1']],
        ])
        const matchesAny = (itemValues, values) => {
          if (!values.length) return true
          return itemValues.some(itemValue => values.includes(String(itemValue || '')))
        }
        const filtered = projectEntities
          .filter(entity => !params.get('type') || String(entity.type || '') === params.get('type'))
          .filter(entity => matchesAny(entityRuns.get(entity.id) || [], params.getAll('run_id')))
          .filter(entity => matchesAny(entityTargets.get(entity.id) || [], params.getAll('target_id')))
        const countSource = projectEntities
          .filter(entity => matchesAny(entityRuns.get(entity.id) || [], params.getAll('run_id')))
          .filter(entity => matchesAny(entityTargets.get(entity.id) || [], params.getAll('target_id')))
        const countsByType = countSource.reduce((counts, entity) => {
          const type = String(entity.type || '')
          counts[type] = Number(counts[type] || 0) + 1
          return counts
        }, {})
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            entities: filtered,
            total: filtered.length,
            limit: Number(params.get('limit') || 50),
            offset: Number(params.get('offset') || 0),
            has_more: false,
            counts_by_type: countsByType,
          }),
        })
      }
      if (url === '/projects/project-1/findings/review' && options.method === 'POST') {
        const payload = JSON.parse(options.body)
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            ok: true,
            review_state: payload.review_state,
            counts: { updated: payload.finding_ids.length, not_found: 0 },
            results: payload.finding_ids.map(findingId => ({ finding_id: findingId, status: 'updated' })),
          }),
        })
      }
      if (String(url).startsWith('/projects/project-1/findings')) {
        const params = new URL(`https://example.test${url}`).searchParams
        const matchesAny = (itemValue, values) => !values.length || values.includes(String(itemValue || ''))
        const groupCounts = (items) => items.reduce((counts, finding) => {
          const key = String(finding.run_command || finding.run_id || '')
          counts[key] = Number(counts[key] || 0) + 1
          return counts
        }, {})
        const matchesLabels = (finding, labels) => {
          if (!labels.length) return true
          const findingLabels = entityLabels.get(`finding:${finding.id}`) || []
          return findingLabels.some(label => labels.includes(label))
        }
        const matchesNoteState = (finding, noteState) => {
          if (!noteState) return true
          const noted = !!(entityNotes.get(`finding:${finding.id}`) || '')
          return noteState === 'noted' ? noted : !noted
        }
        const commandRoot = command => String(command || '').trim().split(/\s+/, 1)[0].toLowerCase()
        return Promise.resolve({
          ok: true,
          json: () => {
            const filtered = [
              {
                id: 'finding-1',
                run_id: 'run-1',
                run_command: 'nuclei https://darklab.sh',
                scope: 'http',
                title: 'missing security header',
                raw_line: '[http-missing-security-headers] https://darklab.sh',
                line_number: 42,
                target_id: 'target-1',
                severity: 'high',
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
                severity: 'medium',
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
                severity: 'info',
                review_state: 'important',
              },
            ].filter(finding => matchesAny(finding.run_id, params.getAll('run_id')))
              .filter(finding => matchesAny(commandRoot(finding.run_command), params.getAll('command_root')))
              .filter(finding => matchesAny(finding.severity, params.getAll('severity')))
              .filter(finding => matchesAny(finding.scope, params.getAll('scope')))
              .filter(finding => matchesAny(finding.review_state, params.getAll('review_state')))
              .filter((finding) => {
                const targetIds = [finding.target_id, ...(finding.target_ids || [])].filter(Boolean).map(String)
                const filters = params.getAll('target_id')
                return !filters.length || targetIds.some(targetId => filters.includes(targetId))
              })
              .filter(finding => matchesLabels(finding, params.getAll('label')))
              .filter(finding => matchesNoteState(finding, params.get('note_state')))
            const collapsedGroups = params.getAll('collapsed_group')
            const collapsedGroupCounts = params.get('include_collapsed_group_counts') === '0'
              ? {}
              : Object.fromEntries(
                Object.entries(groupCounts(filtered)).filter(([key]) => collapsedGroups.includes(key)),
              )
            const orderedGroups = []
            filtered.forEach((finding) => {
              const groupLabel = String(finding.run_command || finding.run_id || '')
              if (groupLabel && !orderedGroups.includes(groupLabel)) orderedGroups.push(groupLabel)
            })
            const visible = filtered
              .filter(finding => !collapsedGroups.includes(String(finding.run_command || finding.run_id || '')))
              .map(finding => ({
                ...finding,
                labels: labelObjects('finding', finding.id),
                note: noteObject('finding', finding.id),
              }))
            return Promise.resolve({
              findings: visible,
              total: visible.length,
              limit: Number(params.get('limit') || 50),
              offset: Number(params.get('offset') || 0),
              has_more: false,
              group_counts: groupCounts(visible),
              collapsed_group_counts: collapsedGroupCounts,
              group_order: orderedGroups.filter((groupLabel) => {
                return collapsedGroups.includes(groupLabel)
                  || visible.some(finding => String(finding.run_command || finding.run_id || '') === groupLabel)
              }),
            })
          },
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
          json: () => Promise.resolve({
            package: {
              ...projectPackages[0],
              labels: labelObjects('package', projectPackages[0].id),
              note: noteObject('package', projectPackages[0].id),
            },
          }),
        })
      }
      if (url === '/projects/project-1/packages/pkg-1/download-jobs' && options.method === 'POST') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            ok: true,
            job: {
              id: 'epj_1234567890abcdef12345678',
              status: 'complete',
              message: 'Archive ready',
            },
          }),
        })
      }
      if (url === '/projects/project-1/packages/pkg-1/download-jobs/epj_1234567890abcdef12345678/download') {
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
        entityLabels.set('package:pkg-2', payload.labels || [])
        entityNotes.set('package:pkg-2', payload.notes || '')
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            ok: true,
            package: {
              ...projectPackages[0],
              labels: labelObjects('package', 'pkg-2'),
              note: noteObject('package', 'pkg-2'),
            },
          }),
        })
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({}),
      })
    })
    const showWorkspaceViewer = vi.fn()
    const fetchAndRenderHistoryComparison = vi.fn()
    const bindMobileSheet = vi.fn()
    let objectUrlCount = 0
    globalThis.URL.createObjectURL = vi.fn(() => `blob:project-${objectUrlCount += 1}`)
    globalThis.URL.revokeObjectURL = vi.fn()
    const delayedRevokes = []
    const originalSetTimeout = window.setTimeout.bind(window)
    const setTimeoutSpy = vi.spyOn(window, 'setTimeout').mockImplementation((callback, delay, ...args) => {
      if (delay === 2000) {
        delayedRevokes.push(() => callback(...args))
        return delayedRevokes.length
      }
      return originalSetTimeout(callback, delay, ...args)
    })
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const shell = loadShellChrome({
      apiFetch,
      restoreHistoryRunIntoTab,
      showWorkspaceViewer,
      showConfirm,
      fetchAndRenderHistoryComparison,
      bindDismissible,
      bindMobileSheet,
    })

    document.dispatchEvent(new CustomEvent('app:project-target-discovered', { detail: { project_id: 'project-1', count: 2 } }))
    expect(document.querySelector('[data-action="projects"]')?.classList.contains('has-project-target-discovery')).toBe(true)
    await shell.openProjectWorkspace()
    await tick()
    await tick()
    expect(document.querySelector('.project-target-row')?.textContent).toContain('Primary domain')
    expect(document.querySelector('.project-explorer-meta-row')?.classList.contains('panel-row')).toBe(true)
    expect(Array.from(document.querySelectorAll('.project-explorer-section-heading'))
      .some(heading => heading.textContent.includes('New'))).toBe(true)
    expect(bindDismissible).toHaveBeenCalledWith(
      document.getElementById('project-target-editor-overlay'),
      expect.objectContaining({ level: 'modal' }),
    )
    expect(bindDismissible).toHaveBeenCalledWith(
      document.getElementById('project-package-wizard-overlay'),
      expect.objectContaining({ level: 'modal' }),
    )
    expect(bindDismissible).toHaveBeenCalledWith(
      document.getElementById('project-package-manifest-overlay'),
      expect.objectContaining({
        level: 'modal',
        closeButtons: [document.querySelector('.project-package-manifest-close')],
      }),
    )
    ;[
      'project-target-editor-modal',
      'project-package-wizard-modal',
      'project-package-manifest-modal',
      'project-entity-editor-modal',
    ].forEach((id) => {
      const modal = document.getElementById(id)
      expect(bindMobileSheet).toHaveBeenCalledWith(modal, expect.objectContaining({ onClose: expect.any(Function) }))
    })
    expectProjectPressablesBound([
      '.project-workspace-row',
      '.project-explorer-tab',
      '.project-explorer-actions .btn',
    ])
    shell.showToast.mockClear()

    document.querySelector('[data-project-tab="runs"]').click()
    await tick()
    const runTabSecondRunFilter = document.querySelector('[data-project-run-filter-option][value="run-2"]')
    expect(runTabSecondRunFilter).not.toBeNull()
    runTabSecondRunFilter.checked = true
    runTabSecondRunFilter.dispatchEvent(new Event('change', { bubbles: true }))
    await tick()
    await tick()
    expect(document.querySelector('[data-project-tab="entities"]')?.textContent).toBe('Entities (0/2)')
    const runTabSecondRunFilterActive = document.querySelector('[data-project-run-filter-option][value="run-2"]')
    expect(runTabSecondRunFilterActive).not.toBeNull()
    runTabSecondRunFilterActive.checked = false
    runTabSecondRunFilterActive.dispatchEvent(new Event('change', { bubbles: true }))
    await tick()

    document.querySelector('[data-project-tab="entities"]').click()
    await tick()
    expect(document.querySelector('.project-entity-type-tab.is-active .project-entity-type-tab-label')?.textContent).toBe('Hosts/IPs')
    expect(document.querySelector('.project-entity-type-tab.is-active .project-entity-type-tab-count')?.textContent).toBe('1')
    expect(document.getElementById('project-explorer-body').textContent).toContain('107.178.109.44')
    expect(document.getElementById('project-explorer-body').textContent).toContain('Shodan')
    expect(document.querySelector('[data-project-action="refresh-project-entity-intel"]')).toBeNull()
    const entityRunFilter = document.querySelector('[data-project-run-filter-option][value="run-1"]')
    expect(entityRunFilter).not.toBeNull()
    entityRunFilter.checked = true
    entityRunFilter.dispatchEvent(new Event('change', { bubbles: true }))
    await tick()
    await tick()
    expect(apiFetch.mock.calls.some(([url]) => (
      String(url).startsWith('/projects/project-1/entities?')
      && String(url).includes('run_id=run-1')
    ))).toBe(true)
    expect(document.querySelector('[data-project-tab="entities"]')?.textContent).toBe('Entities (2/2)')
    expect(document.querySelector('.project-entity-type-tab.is-active .project-entity-type-tab-count')?.textContent).toBe('1/1')

    const activeEntityRunFilter = document.querySelector('[data-project-run-filter-option][value="run-1"]')
    const secondEntityRunFilter = document.querySelector('[data-project-run-filter-option][value="run-2"]')
    expect(activeEntityRunFilter).not.toBeNull()
    expect(secondEntityRunFilter).not.toBeNull()
    activeEntityRunFilter.checked = false
    activeEntityRunFilter.dispatchEvent(new Event('change', { bubbles: true }))
    await tick()
    const onlySecondEntityRunFilter = document.querySelector('[data-project-run-filter-option][value="run-2"]')
    expect(onlySecondEntityRunFilter).not.toBeNull()
    onlySecondEntityRunFilter.checked = true
    onlySecondEntityRunFilter.dispatchEvent(new Event('change', { bubbles: true }))
    document.querySelector('[data-project-entity-tab="domain"]').click()
    await tick()
    await tick()
    expect(document.querySelector('.project-entity-type-tab.is-active .project-entity-type-tab-label')?.textContent).toBe('Domains')
    expect(document.querySelector('.project-entity-type-tab.is-active .project-entity-type-tab-count')?.textContent).toBe('0/0')
    expect(document.querySelector('.project-entity-pagination')).toBeNull()

    const emptyEntityRunFilter = document.querySelector('[data-project-run-filter-option][value="run-2"]')
    const restoredEntityRunFilter = document.querySelector('[data-project-run-filter-option][value="run-1"]')
    expect(emptyEntityRunFilter).not.toBeNull()
    expect(restoredEntityRunFilter).not.toBeNull()
    emptyEntityRunFilter.checked = false
    emptyEntityRunFilter.dispatchEvent(new Event('change', { bubbles: true }))
    await tick()
    const freshRestoredEntityRunFilter = document.querySelector('[data-project-run-filter-option][value="run-1"]')
    expect(freshRestoredEntityRunFilter).not.toBeNull()
    freshRestoredEntityRunFilter.checked = true
    freshRestoredEntityRunFilter.dispatchEvent(new Event('change', { bubbles: true }))
    document.querySelector('[data-project-entity-tab="cve"]').click()
    await tick()
    await tick()
    expect(document.querySelector('.project-entity-type-tab.is-active .project-entity-type-tab-label')?.textContent).toBe('CVEs')
    expect(document.querySelector('.project-entity-type-tab.is-active .project-entity-type-tab-count')?.textContent).toBe('1/1')
    expect(document.getElementById('project-explorer-body').textContent).toContain('CVE-2025-49113')
    expect(document.getElementById('project-explorer-body').textContent).toContain('intel: NVD')
    document.querySelector('[data-project-action="toggle-project-entity-select"]').click()
    await tick()
    document.querySelector('[data-project-action="select-all-project-entities"]').click()
    await tick()
    expect(document.querySelector('.project-entity-selection-count')?.textContent).toBe('1 selected')
    document.querySelector('[data-project-action="bulk-unlink-project-entities"]').click()
    await tick()
    await tick()
    expect(apiFetch).toHaveBeenCalledWith('/projects/project-1/links', expect.objectContaining({
      method: 'DELETE',
      body: JSON.stringify({ entity_type: 'atlas_entity', entity_ids: ['entity-cve'] }),
    }))
    expect(document.getElementById('project-explorer-body').textContent).not.toContain('CVE-2025-49113')

    document.querySelector('[data-project-tab="details"]').click()
    await tick()
    document.querySelector('[data-project-action="edit-target"]').click()
    await tick()
    expect(document.getElementById('project-target-editor-overlay').classList.contains('open')).toBe(true)
    expect(document.getElementById('project-target-editor-title').textContent).toBe('EDIT TARGET')
    document.getElementById('project-target-value').value = 'darklab.io'
    document.getElementById('project-target-label').value = 'Updated target'
    document.getElementById('project-target-notes').value = 'Retest scope'
    const projectFetchesBeforeTargetEdit = apiFetch.mock.calls
      .filter(([url]) => String(url).startsWith('/projects?include_archived=1')).length
    document.getElementById('project-target-create-form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await tick()
    await tick()
    await tick()
    expect(apiFetch).toHaveBeenCalledWith('/projects/project-1/targets/target-1', expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({
        type: 'domain',
        value: 'darklab.io',
      }),
    }))
    expect(apiFetch).toHaveBeenCalledWith('/entities/target/target-1/labels', expect.objectContaining({
      method: 'DELETE',
      body: JSON.stringify({ label: 'Primary domain' }),
    }))
    expect(apiFetch).toHaveBeenCalledWith('/entities/target/target-1/labels', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ label: 'Updated target' }),
    }))
    expect(apiFetch).toHaveBeenCalledWith('/entities/target/target-1/note', expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({ body: 'Retest scope' }),
    }))
    expect(apiFetch.mock.calls
      .filter(([url]) => String(url).startsWith('/projects?include_archived=1')).length).toBe(projectFetchesBeforeTargetEdit)
    expect(document.querySelector('.project-target-row')?.textContent).toContain('darklab.io')
    expect(shell.showToast).toHaveBeenCalledWith('Target updated.', 'success')
    expect(document.getElementById('project-workspace-message').classList.contains('u-hidden')).toBe(true)

    document.querySelector('[data-project-tab="findings"]').click()
    await tick()
    await tick()
    expect(document.getElementById('project-workspace-message').classList.contains('u-hidden')).toBe(true)
    expect(document.getElementById('project-explorer-body').textContent).toContain('old-label')
    expect(document.getElementById('project-explorer-body').textContent).toContain('note')
    expect(document.querySelector('.project-explorer-metadata-chip')?.classList.contains('badge')).toBe(true)
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

    const sharedFilterMenu = document.querySelector('.project-shared-filter-menu')
    expect(sharedFilterMenu?.tagName).toBe('DIV')
    expect(sharedFilterMenu.querySelector('summary')).toBeNull()
    const filterTrigger = sharedFilterMenu.querySelector('.project-target-filter-trigger')
    const filterSurface = sharedFilterMenu.querySelector('.project-target-filter-options')
    expect(filterTrigger?.dataset.pressableBound).toBe('1')
    expect(filterTrigger?.classList.contains('control-row')).toBe(true)
    expect(filterTrigger?.classList.contains('btn')).toBe(false)
    expect(filterTrigger?.getAttribute('aria-expanded')).toBe('false')
    expect(filterTrigger?.getAttribute('aria-haspopup')).toBe('menu')
    expect(filterSurface?.classList.contains('dropdown-surface')).toBe(true)
    expect(filterSurface?.getAttribute('role')).toBe('menu')
    expect(filterSurface?.hidden).toBe(true)
    filterTrigger.click()
    await tick()
    expect(sharedFilterMenu.classList.contains('is-open')).toBe(true)
    expect(filterTrigger.getAttribute('aria-expanded')).toBe('true')
    expect(filterSurface.hidden).toBe(false)
    expect(sharedFilterMenu.querySelector('.project-target-filter-option.dropdown-item.dropdown-item-compact')).not.toBeNull()
    document.body.click()
    await tick()
    expect(sharedFilterMenu.classList.contains('is-open')).toBe(false)
    expect(filterSurface.hidden).toBe(true)

    const retestFilter = document.querySelector('[data-project-finding-label-filter-option][value="retest"]')
    expect(retestFilter).not.toBeNull()
    retestFilter.checked = true
    retestFilter.dispatchEvent(new Event('change', { bubbles: true }))
    await tick()
    await tick()
    expect(apiFetch.mock.calls.some(([url]) => (
      String(url).startsWith('/projects/project-1/findings?')
      && String(url).includes('label=retest')
    ))).toBe(true)
    expect(document.querySelector('[data-project-tab="findings"]')?.textContent).toBe('Findings (1/3)')
    const retestChip = Array.from(document.querySelectorAll('.project-target-filter-chip'))
      .find(chip => chip.textContent.includes('label: retest'))
    expect(retestChip).toBeTruthy()
    expect(retestChip?.classList.contains('chip-removable')).toBe(true)
    expect(retestChip?.classList.contains('btn')).toBe(false)
    expect(document.querySelector('.project-explorer-item')?.classList.contains('panel-row')).toBe(true)
    expect(document.getElementById('project-explorer-body').textContent).toContain('missing security header')
    expect(document.getElementById('project-explorer-body').textContent).not.toContain('web port responded')

    const noteStateFilter = document.querySelector('[data-project-finding-note-state]')
    expect(noteStateFilter).not.toBeNull()
    noteStateFilter.value = 'noted'
    noteStateFilter.dispatchEvent(new Event('change', { bubbles: true }))
    await tick()
    await tick()
    expect(apiFetch.mock.calls.some(([url]) => (
      String(url).startsWith('/projects/project-1/findings?')
      && String(url).includes('label=retest')
      && String(url).includes('note_state=noted')
    ))).toBe(true)
    expect(document.querySelector('.project-explorer-filter-chips')?.textContent).toContain('notes: With notes')
    document.querySelector('[data-project-filter-clear-all]').click()
    await tick()
    expect(document.querySelector('[data-project-tab="findings"]')?.textContent).toBe('Findings (3)')

    const importantFilter = document.querySelector('[data-project-finding-status-filter-option][value="important"]')
    expect(importantFilter).not.toBeNull()
    importantFilter.checked = true
    importantFilter.dispatchEvent(new Event('change', { bubbles: true }))
    await tick()
    expect(document.querySelector('[data-project-tab="findings"]')?.textContent).toBe('Findings (1/3)')
    expect(document.querySelector('.project-explorer-filter-chips .project-target-filter-chip')?.textContent).toContain('status: Important')
    expect(document.getElementById('project-explorer-body').textContent).toContain('web port responded')
    expect(document.getElementById('project-explorer-body').textContent).not.toContain('missing security header')
    expect(document.getElementById('project-explorer-body').textContent).not.toContain('api host responded')
    expectProjectPressablesBound([
      '.project-target-filter-trigger',
      '.project-explorer-item-click-target',
      '.project-target-filter-chip',
      '.project-target-filter-clear',
    ])
    expect(document.querySelector('[data-project-finding-group-toggle]')).toBeNull()
    expect(document.getElementById('project-explorer-body').textContent).toContain('nuclei https://darklab.sh')
    expect(apiFetch.mock.calls.some(([url]) => (
      String(url).startsWith('/projects/project-1/findings?')
      && String(url).includes('include_group_counts=0')
    ))).toBe(true)

    document.querySelector('[data-project-finding-status-filter-clear="important"]').click()
    await tick()
    const httpxFilter = document.querySelector('[data-project-finding-command-filter-option][value="httpx"]')
    expect(httpxFilter).not.toBeNull()
    httpxFilter.checked = true
    httpxFilter.dispatchEvent(new Event('change', { bubbles: true }))
    await tick()
    await tick()
    expect(apiFetch.mock.calls.some(([url]) => (
      String(url).startsWith('/projects/project-1/findings?')
      && String(url).includes('command_root=httpx')
    ))).toBe(true)
    expect(document.querySelector('.project-explorer-filter-chips')?.textContent).toContain('command: httpx')
    expect(document.getElementById('project-explorer-body').textContent).toContain('api host responded')
    expect(document.getElementById('project-explorer-body').textContent).not.toContain('web port responded')

    const mediumFilter = document.querySelector('[data-project-finding-severity-filter-option][value="medium"]')
    expect(mediumFilter).not.toBeNull()
    mediumFilter.checked = true
    mediumFilter.dispatchEvent(new Event('change', { bubbles: true }))
    await tick()
    await tick()
    expect(apiFetch.mock.calls.some(([url]) => (
      String(url).startsWith('/projects/project-1/findings?')
      && String(url).includes('command_root=httpx')
      && String(url).includes('severity=medium')
    ))).toBe(true)
    expect(document.querySelector('.project-explorer-filter-chips')?.textContent).toContain('severity: Medium')

    const httpScopeFilter = document.querySelector('[data-project-finding-scope-filter-option][value="http"]')
    expect(httpScopeFilter).not.toBeNull()
    httpScopeFilter.checked = true
    httpScopeFilter.dispatchEvent(new Event('change', { bubbles: true }))
    await tick()
    await tick()
    expect(apiFetch.mock.calls.some(([url]) => (
      String(url).startsWith('/projects/project-1/findings?')
      && String(url).includes('command_root=httpx')
      && String(url).includes('severity=medium')
      && String(url).includes('scope=http')
    ))).toBe(true)
    expect(document.querySelector('.project-explorer-filter-chips')?.textContent).toContain('scope: HTTP')

    document.querySelector('[data-project-finding-command-filter-clear="httpx"]').click()
    await tick()
    document.querySelector('[data-project-finding-severity-filter-clear="medium"]').click()
    await tick()
    document.querySelector('[data-project-finding-scope-filter-clear="http"]').click()
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
    expect(document.querySelector('.project-target-filter-chip')?.textContent).toContain('target: ip: 107.178.109.44')
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
    expect(document.querySelector('[data-project-finding-label-filter-option][value="retest"]')).not.toBeNull()
    expect(document.querySelector('[data-project-finding-note-state]')).not.toBeNull()
    expect(document.querySelector('[data-project-finding-sort]')).toBeNull()
    expectProjectPressablesBound([
      '.project-runs-toolbar-actions .btn',
      '.project-run-compare-mode-button',
    ])
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

    expect(document.querySelector('[data-project-compare-mode]')?.value).toBe('run')
    expect(document.querySelector('[data-project-compare-mode-value="run"]')?.getAttribute('aria-pressed')).toBe('true')
    expect(document.querySelector('[data-project-compare-baseline-label]')).toBeNull()
    expect(document.querySelector('[data-project-compare-target]')?.value).toBe('run-2')
    expect(document.querySelector('.project-runs-toolbar-divider')).not.toBeNull()
    expect(document.querySelector('[data-project-action="compare-runs"]')?.title).toBe('Compare selected project runs.')
    document.querySelector('[data-project-action="compare-runs"]').click()
    await tick()
    expect(fetchAndRenderHistoryComparison).toHaveBeenCalledWith(
      'run-1',
      'run-2',
      {
        url: '/history/compare?left=run-1&project_id=project-1&right=run-2',
      },
    )
    fetchAndRenderHistoryComparison.mockClear()
    shell.syncAppSelect.mockClear()
    document.querySelector('[data-project-compare-mode-value="baseline"]').click()
    await tick()
    expect(document.querySelector('[data-project-compare-mode]')?.value).toBe('baseline')
    expect(document.querySelector('[data-project-compare-mode-value="baseline"]')?.getAttribute('aria-pressed')).toBe('true')
    expect(document.querySelector('[data-project-compare-run="left"]')?.value).toBe('run-2')
    expect(document.querySelector('[data-project-compare-target]')?.value).toBe('baseline')
    expect(shell.syncAppSelect).toHaveBeenCalledWith(document.querySelector('[data-project-compare-run="left"]'))
    expect(shell.syncAppSelect).toHaveBeenCalledWith(document.querySelector('[data-project-compare-target]'))
    expect([...document.querySelector('[data-project-compare-target]')?.options || []].map(option => option.value)).toEqual([
      'baseline',
      'reviewed',
    ])
    document.querySelector('[data-project-compare-run="left"]').value = 'run-1'
    document.querySelector('[data-project-compare-run="left"]').dispatchEvent(new Event('change', { bubbles: true }))
    await tick()
    expect(document.querySelector('[data-project-compare-run="left"]')?.value).toBe('run-2')
    document.querySelector('[data-project-action="compare-runs"]').click()
    await tick()
    expect(fetchAndRenderHistoryComparison).toHaveBeenCalledWith(
      'run-2',
      'baseline:baseline',
      {
        url: '/history/compare?left=run-2&project_id=project-1&baseline_label=baseline',
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
    expect(delayedRevokes).toHaveLength(1)
    delayedRevokes[0]()
    expect(globalThis.URL.revokeObjectURL).toHaveBeenCalledWith('blob:project-1')
    globalThis.URL.revokeObjectURL.mockClear()
    expect(document.querySelector('[data-project-action="artifact-preview"][data-artifact-id="artifact-2"]').disabled)
      .toBe(true)
    globalThis.URL.createObjectURL.mockClear()

    document.querySelector('[data-project-tab="packages"]').click()
    await tick()
    expect(document.getElementById('project-explorer-body').textContent).toContain('Darklab evidence')
    expect(document.getElementById('project-explorer-body').textContent).toContain('evidence · raw · ~32 KB')
    expect(document.getElementById('project-explorer-body').textContent).toContain('2 runs · 3 findings · 2 artifacts')
    expect(document.getElementById('project-explorer-body').textContent).toContain('handoff')
    expect(document.getElementById('project-explorer-body').textContent).toContain('note')
    const packageDeleteAction = document.querySelector('[data-project-action="package-delete"][data-package-id="pkg-1"]')
    expect(packageDeleteAction?.classList.contains('btn-secondary')).toBe(true)
    expect(packageDeleteAction?.classList.contains('btn-danger')).toBe(true)
    document.querySelector('[data-project-action="package-edit"][data-package-id="pkg-1"]').click()
    await tick()
    expect(document.getElementById('project-entity-editor-overlay').classList.contains('open')).toBe(true)
    expect(document.getElementById('project-entity-editor-title').textContent).toBe('EDIT PACKAGE')
    expect(document.getElementById('project-entity-editor-subtitle').textContent).toContain('Darklab evidence')
    expect(document.getElementById('project-entity-labels').value).toBe('handoff')
    expect(document.getElementById('project-entity-note').value).toBe('Initial package note')
    document.getElementById('project-entity-labels').value = 'handoff, approved'
    document.getElementById('project-entity-note').value = 'Ready for client handoff'
    document.getElementById('project-entity-editor-form')
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await tick()
    await tick()
    await tick()
    expect(apiFetch).toHaveBeenCalledWith('/entities/package/pkg-1/labels', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ label: 'approved' }),
    }))
    expect(apiFetch).toHaveBeenCalledWith('/entities/package/pkg-1/note', expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({ body: 'Ready for client handoff' }),
    }))
    expect(document.getElementById('project-entity-editor-overlay').classList.contains('open')).toBe(false)
    expect(document.getElementById('project-explorer-body').textContent).toContain('approved')
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
    const manifestDismissible = dismissibles.find(item => item.el === document.getElementById('project-package-manifest-overlay'))
    expect(manifestDismissible?.options.isOpen()).toBe(true)
    document.querySelector('.project-package-manifest-close').click()
    await tick()
    expect(document.getElementById('project-package-manifest-overlay').classList.contains('open')).toBe(false)
    expect(manifestDismissible.options.isOpen()).toBe(false)

    const packageDownloadButton = document.querySelector('[data-project-action="package-download"][data-package-id="pkg-1"]')
    packageDownloadButton.click()
    await tick()
    await tick()
    expect(apiFetch).toHaveBeenCalledWith(
      '/projects/project-1/packages/pkg-1/download-jobs',
      { method: 'POST', cache: 'no-store' },
    )
    expect(apiFetch).toHaveBeenCalledWith(
      '/projects/project-1/packages/pkg-1/download-jobs/epj_1234567890abcdef12345678/download',
      { cache: 'no-store' },
    )
    expect(packageDownloadButton.disabled).toBe(true)
    expect(packageDownloadButton.classList.contains('is-preparing')).toBe(true)
    expect(packageDownloadButton.getAttribute('aria-busy')).toBe('true')
    expect(packageDownloadButton.textContent).toBe('Preparing archive...')
    expect(document.getElementById('project-workspace-message').textContent).toContain(
      'Preparing package archive',
    )
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
    expect(delayedRevokes).toHaveLength(2)
    delayedRevokes[1]()
    expect(globalThis.URL.revokeObjectURL).toHaveBeenCalledWith('blob:project-2')
    globalThis.URL.revokeObjectURL.mockClear()
    window.dispatchEvent(new Event('pagehide'))
    expect(globalThis.URL.revokeObjectURL).not.toHaveBeenCalled()

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
    expect(shell.showToast).toHaveBeenCalledWith(
      '2 unavailable items removed; review your selection before continuing.',
      'success',
    )
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
    const fullPreset = document.querySelector('input[name="project-package-preset"][value="full"]')
    fullPreset.checked = true
    fullPreset.dispatchEvent(new Event('change', { bubbles: true }))
    await tick()
    document.querySelector('[data-project-action="package-wizard-next"]').click()
    await tick()
    expect(document.querySelector('[data-project-package-selection="transcript"][value="run-1"]').checked).toBe(true)
    expect(document.querySelector('[data-project-package-selection="transcript"][value="run-2"]').checked).toBe(true)
    document.querySelector(
      '[data-project-action="package-wizard-bulk-selection"][data-bulk-kind="transcript"][data-bulk-mode="clear"]',
    ).click()
    await tick()
    expect(document.querySelector('[data-project-package-selection="transcript"][value="run-1"]').checked).toBe(false)
    expect(document.querySelector('[data-project-package-selection="transcript"][value="run-2"]').checked).toBe(false)
    document.querySelector(
      '[data-project-action="package-wizard-bulk-selection"][data-bulk-kind="transcript"][data-bulk-mode="select"]',
    ).click()
    await tick()
    expect(document.querySelector('[data-project-package-selection="transcript"][value="run-1"]').checked).toBe(true)
    expect(document.querySelector('[data-project-package-selection="transcript"][value="run-2"]').checked).toBe(true)
    document.querySelector('[data-project-action="package-wizard-back"]').click()
    await tick()
    const evidencePreset = document.querySelector('input[name="project-package-preset"][value="evidence"]')
    evidencePreset.checked = true
    evidencePreset.dispatchEvent(new Event('change', { bubbles: true }))
    await tick()
    const packageLabels = document.querySelector('[data-project-package-field="labels"]')
    const packageNotes = document.querySelector('[data-project-package-field="notes"]')
    expect(packageLabels).not.toBeNull()
    expect(packageNotes).not.toBeNull()
    packageLabels.value = 'handoff, retest, Handoff'
    packageLabels.dispatchEvent(new Event('input', { bubbles: true }))
    packageNotes.value = 'Package notes for handoff'
    packageNotes.dispatchEvent(new Event('input', { bubbles: true }))
    document.querySelector('[data-project-action="package-wizard-next"]').click()
    await tick()
    expect(document.querySelector('.project-package-step.is-active')?.textContent).toContain('Include')
    expect(document.getElementById('project-package-wizard-overlay').textContent).toContain('Findings (2)')
    expect(document.getElementById('project-package-wizard-overlay').textContent).toContain('Artifacts (1)')
    expect(document.querySelectorAll('.project-package-bulk-menu')).toHaveLength(2)
    const firstBulkMenu = document.querySelector('.project-package-bulk-menu')
    firstBulkMenu.open = true
    firstBulkMenu.dispatchEvent(new FocusEvent('focusout', {
      bubbles: true,
      relatedTarget: document.querySelector('[data-project-action="package-wizard-next"]'),
    }))
    expect(firstBulkMenu.open).toBe(false)
    document.querySelector(
      '[data-project-action="package-wizard-bulk-selection"][data-bulk-kind="finding"][data-bulk-mode="clear"]',
    ).click()
    await tick()
    expect(document.querySelector('[data-project-package-selection="finding"][value="finding-1"]').checked).toBe(false)
    expect(document.querySelector('[data-project-package-selection="finding"][value="finding-2"]').checked).toBe(false)
    document.querySelector(
      '[data-project-action="package-wizard-bulk-selection"][data-bulk-kind="finding"][data-bulk-mode="select"]',
    ).click()
    await tick()
    expect(document.querySelector('[data-project-package-selection="finding"][value="finding-1"]').checked).toBe(true)
    expect(document.querySelector('[data-project-package-selection="finding"][value="finding-2"]').checked).toBe(true)
    document.querySelector(
      '[data-project-action="package-wizard-bulk-selection"][data-bulk-kind="target"][data-bulk-mode="clear"]',
    ).click()
    await tick()
    expect(document.querySelector('[data-project-package-selection="target"][value="target-1"]').checked).toBe(false)
    document.querySelector(
      '[data-project-action="package-wizard-bulk-selection"][data-bulk-kind="target"][data-bulk-mode="select"]',
    ).click()
    await tick()
    expect(document.querySelector('[data-project-package-selection="target"][value="target-1"]').checked).toBe(true)
    expectProjectPressablesBound(['.project-package-run-toggle'])
    expect(document.querySelector('[data-project-package-selection="artifact"][value="artifact-2"]').checked).toBe(false)
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
    expect(document.querySelector('[data-project-package-selection="artifact"][value="artifact-2"]').checked).toBe(false)
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
    expect(document.getElementById('project-package-wizard-overlay').textContent).toContain('Best-guess ZIP size')
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
    expect(packagePayload.labels).toEqual(['handoff', 'retest'])
    expect(packagePayload.notes).toBe('Package notes for handoff')
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
    expect(document.querySelector('[data-project-tab="runs"]')?.textContent).toBe('Runs (1/2)')
    expect(document.querySelector('[data-project-tab="findings"]')?.textContent).toBe('Findings (2/3)')
    expect(document.querySelector('[data-project-tab="artifacts"]')?.textContent).toBe('Artifacts (1/2)')
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
    const disabledCompare = document.querySelector('[data-project-action="compare-runs"]')
    expect(disabledCompare?.disabled).toBe(true)
    expect(disabledCompare?.title).toBe('Link two runs to compare.')
    expect(disabledCompare?.getAttribute('aria-disabled')).toBe('true')

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
      .toBe('nuclei https://darklab.sh · http · target domain: darklab.io · line 42')

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

    document.querySelector('[data-project-action="toggle-project-finding-select"]').click()
    await tick()
    const findingSelect = document.querySelector('[data-project-finding-select="finding-1"]')
    expect(findingSelect).not.toBeNull()
    expect(document.querySelector('.project-finding-selection-count')?.textContent).toBe('0 selected')
    findingSelect.checked = true
    findingSelect.dispatchEvent(new Event('click', { bubbles: true }))
    await tick()
    expect(document.querySelector('.project-finding-selection-count')?.textContent).toBe('1 selected')
    const bulkReview = document.querySelector('[data-project-finding-bulk-review]')
    expect(bulkReview).not.toBeNull()
    bulkReview.value = 'reviewed'
    bulkReview.dispatchEvent(new Event('change', { bubbles: true }))
    await tick()
    await tick()
    expect(apiFetch).toHaveBeenCalledWith('/projects/project-1/findings/review', expect.objectContaining({
      method: 'POST',
      body: JSON.stringify({ finding_ids: ['finding-1'], review_state: 'reviewed' }),
    }))
    expect(document.querySelector('.project-finding-bulk-review')).toBeNull()
    expect(document.querySelector('.project-finding-review')?.value).toBe('reviewed')

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
    const projectFetchesBeforeTargetDelete = apiFetch.mock.calls
      .filter(([url]) => String(url).startsWith('/projects?include_archived=1')).length
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
    expect(apiFetch.mock.calls
      .filter(([url]) => String(url).startsWith('/projects?include_archived=1')).length)
      .toBe(projectFetchesBeforeTargetDelete)
    expect(document.querySelector('[data-project-action="edit-target"][data-target-id="target-1"]')).toBeNull()
    expect(document.querySelector('.project-target-row')?.textContent).toContain('api.darklab.sh')
    setTimeoutSpy.mockRestore()
  }, 10000)

  it('reorders project findings when the sort control changes', async () => {
    const projectRuns = [
      { id: 'run-old', command: 'nuclei old.example', started: '2026-05-07T00:00:00Z' },
      { id: 'run-new', command: 'httpx new.example', started: '2026-05-07T01:00:00Z' },
    ]
    const projectTargets = [
      { id: 'target-api', type: 'domain', value: 'api.example', label: 'API' },
      { id: 'target-web', type: 'domain', value: 'web.example', label: 'Web' },
    ]
    const projectFindings = [
      {
        id: 'finding-low',
        run_id: 'run-old',
        run_command: 'nuclei old.example',
        title: 'Low issue',
        raw_line: 'low',
        line_number: 20,
        severity: 'low',
        review_state: 'reviewed',
        target_id: 'target-web',
      },
      {
        id: 'finding-high',
        run_id: 'run-new',
        run_command: 'httpx new.example',
        title: 'High issue',
        raw_line: 'high',
        line_number: 5,
        severity: 'high',
        review_state: 'new',
        target_id: 'target-api',
      },
      {
        id: 'finding-info',
        run_id: 'run-new',
        run_command: 'httpx new.example',
        title: 'Critical issue',
        raw_line: 'critical',
        line_number: 9,
        severity: 'critical',
        review_state: 'important',
        target_id: 'target-web',
      },
    ]
    const apiFetch = vi.fn((url) => {
      if (url === '/projects/active') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ project: { id: 'project-1', name: 'Sort Project' } }),
        })
      }
      if (String(url).startsWith('/projects?include_archived=1')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ projects: [{ id: 'project-1', name: 'Sort Project', status: 'active' }] }),
        })
      }
      if (url === '/projects/project-1/summary') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            project: { id: 'project-1', name: 'Sort Project', status: 'active' },
            counts: { runs: 2, findings: 3, artifacts: 0, packages: 0, targets: 2, notes: 0 },
            runs: projectRuns,
            targets: projectTargets,
            artifacts: [],
            packages: [],
          }),
        })
      }
      if (String(url).startsWith('/projects/project-1/findings')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            findings: projectFindings,
            total: projectFindings.length,
            limit: 50,
            offset: 0,
            has_more: false,
            group_counts: {
              'nuclei old.example': 1,
              'httpx new.example': 200,
            },
          }),
        })
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
    })
    const shell = loadShellChrome({ apiFetch })
    const projectFindingsData = shell.projectFindingsData
    const board = projectFindingsData.boardColumnsFromFindings([
      ...projectFindings,
      {
        id: 'finding-unknown',
        title: 'Unknown review state',
        review_state: 'triaged_elsewhere',
        target_ids: ['target-api', 'target-api'],
        labels: ['needs-owner'],
        note: 'check manually',
        source_run_exists: false,
      },
      { id: 'finding-extra-new', title: 'Another new issue', review_state: 'new' },
    ], { limit: 1 })
    const uncappedBoard = projectFindingsData.boardColumnsFromFindings([
      ...projectFindings,
      {
        id: 'finding-unknown',
        title: 'Unknown review state',
        review_state: 'triaged_elsewhere',
        target_ids: ['target-api', 'target-api'],
        labels: ['needs-owner'],
        note: 'check manually',
        source_run_exists: false,
      },
    ], { limit: 10 })
    const newColumn = board.columns.find(column => column.state === 'new')
    const reviewedColumn = board.columns.find(column => column.state === 'reviewed')
    const falsePositiveColumn = board.columns.find(column => column.state === 'false_positive')
    const followUpColumn = board.columns.find(column => column.state === 'needs_followup')

    expect(board.columns.map(column => column.state)).toEqual(['new', 'reviewed', 'false_positive', 'needs_followup'])
    expect(board.counts).toMatchObject({ new: 3, reviewed: 2, false_positive: 0, needs_followup: 0 })
    expect(board.total).toBe(5)
    expect(board.truncated).toBe(true)
    expect(newColumn).toMatchObject({ label: 'New', total: 3, truncated: true })
    expect(newColumn.cards[0]).toMatchObject({
      id: 'finding-high',
      workflow_state: 'new',
      review_state: 'new',
      important: false,
      target_ids: ['target-api'],
    })
    expect(reviewedColumn).toMatchObject({ label: 'Reviewed', total: 2, truncated: true })
    expect(reviewedColumn.cards[0]).toMatchObject({
      id: 'finding-low',
      workflow_state: 'reviewed',
      review_state: 'reviewed',
      important: false,
    })
    expect(uncappedBoard.columns.find(column => column.state === 'reviewed').cards.at(-1)).toMatchObject({
      id: 'finding-info',
      workflow_state: 'reviewed',
      review_state: 'important',
      important: true,
    })
    expect(uncappedBoard.columns.find(column => column.state === 'new').cards.at(-1)).toMatchObject({
      id: 'finding-unknown',
      workflow_state: 'new',
      review_state: 'triaged_elsewhere',
      labels: ['needs-owner'],
      note: 'check manually',
      orphan_source: true,
      target_ids: ['target-api'],
    })
    expect(projectFindingsData.boardWorkflowState({ review_state: 'important' })).toBe('reviewed')
    expect(projectFindingsData.boardWorkflowState('triaged_elsewhere')).toBe('new')
    expect(falsePositiveColumn).toMatchObject({ cards: [], total: 0, truncated: false })
    expect(followUpColumn).toMatchObject({ cards: [], total: 0, truncated: false })

    await shell.openProjectWorkspace()
    document.querySelector('[data-project-tab="findings"]').click()
    await tick()
    await tick()
    const titles = () => Array.from(document.querySelectorAll('.project-explorer-item-title'))
      .map(node => node.textContent.trim())

    expect(titles()).toEqual(['Low issue', 'High issue', 'Critical issue'])
    expect(document.querySelector('.project-explorer-group-count')).toBeNull()
    expect(document.querySelector('.project-finding-view-button[aria-pressed="true"]')?.textContent).toBe('List')

    let sortControl = document.querySelector('[data-project-finding-sort]')
    await tick()
    const sortWrap = sortControl.closest('.project-finding-source-order-control')
    expect(document.querySelector('.project-filter-sort-divider')).toBeNull()
    expect(sortWrap?.classList.contains('has-sort-divider')).toBe(true)
    expect(sortControl.closest('.project-explorer-filter-controls')?.lastElementChild).toBe(sortWrap)
    sortControl.value = 'severity'
    sortControl.dispatchEvent(new Event('change', { bubbles: true }))
    await tick()
    expect(titles()).toEqual(['Critical issue', 'High issue', 'Low issue'])

    sortControl = document.querySelector('[data-project-finding-sort]')
    sortControl.value = 'target'
    sortControl.dispatchEvent(new Event('change', { bubbles: true }))
    await tick()
    expect(titles()).toEqual(['High issue', 'Critical issue', 'Low issue'])

    sortControl = document.querySelector('[data-project-finding-sort]')
    sortControl.value = 'newest'
    sortControl.dispatchEvent(new Event('change', { bubbles: true }))
    await tick()
    expect(titles()).toEqual(['High issue', 'Critical issue', 'Low issue'])

    document.querySelector('[data-project-finding-view-mode="board"]').click()
    await tick()
    expect(document.querySelector('.project-finding-view-button[aria-pressed="true"]')?.textContent).toBe('Board')
    expect(document.querySelector('.project-finding-board')).not.toBeNull()
    expect(Array.from(document.querySelectorAll('.project-finding-board-column-header h3')).map(node => node.textContent))
      .toEqual(['New', 'Reviewed', 'False positive', 'Follow-up'])
    expect(Array.from(document.querySelectorAll('.project-finding-board-card-title')).map(node => node.textContent))
      .toEqual(['High issue', 'Critical issue', 'Low issue'])
    expect(document.querySelector('.project-finding-board-badge.is-important')?.textContent).toBe('important')
    expect(document.querySelector('.project-finding-bulk-toolbar')).toBeNull()

    document.querySelector('[data-project-finding-view-mode="list"]').click()
    await tick()
    expect(document.querySelector('.project-finding-board')).toBeNull()
    expect(document.querySelector('.project-finding-bulk-toolbar')).not.toBeNull()

    document.querySelector('[data-project-action="open-findings-board"]').click()
    await tick()
    await tick()
    expect(document.getElementById('project-workspace-overlay').classList.contains('open')).toBe(false)
    expect(document.getElementById('findings-board-overlay').classList.contains('open')).toBe(true)
    expect(document.getElementById('findings-board-subtitle').textContent).toContain('Project: Sort Project')
    expect(document.getElementById('findings-board-body').textContent).toContain('Critical issue')
    const boardReview = document.querySelector('#findings-board-body [data-findings-board-review]')
    boardReview.value = 'false_positive'
    boardReview.dispatchEvent(new Event('change', { bubbles: true }))
    await tick()
    expect(apiFetch).toHaveBeenCalledWith('/findings/finding-high/review', expect.objectContaining({
      method: 'PUT',
      body: JSON.stringify({ review_state: 'false_positive' }),
    }))
  })

  it('refreshes an open Projects modal after a cross-tab project broadcast', async () => {
    let refreshed = false
    const apiFetch = vi.fn((url) => {
      if (url === '/projects/active') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ project: { id: 'project-1', name: refreshed ? 'Updated Project' : 'Initial Project' } }),
        })
      }
      if (String(url).startsWith('/projects?include_archived=1')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ projects: [{ id: 'project-1', name: refreshed ? 'Updated Project' : 'Initial Project', status: 'active' }] }),
        })
      }
      if (url === '/projects/project-1/summary') {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            project: { id: 'project-1', name: refreshed ? 'Updated Project' : 'Initial Project', status: 'active' },
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
    expect(document.getElementById('project-workspace-body').textContent).toContain('Initial Project')

    vi.useFakeTimers()
    try {
      refreshed = true
      window.dispatchEvent(new StorageEvent('storage', {
        key: 'darklab_project_workspace_changed',
        newValue: JSON.stringify({ reason: 'updated', project_id: 'project-1', ts: Date.now() }),
      }))
      await vi.advanceTimersByTimeAsync(250)
      await Promise.resolve()
    } finally {
      vi.useRealTimers()
    }

    expect(apiFetch.mock.calls.filter(([url]) => String(url).startsWith('/projects?include_archived=1')).length).toBeGreaterThan(1)
    expect(document.getElementById('project-workspace-body').textContent).toContain('Updated Project')
  })
})
