import { vi } from 'vitest'
import { fromDomScripts } from './helpers/extract.js'
import { bindFocusTrap } from '../../../app/static/js/ui/ui_focus_trap.js'

function loadTourModal({
  mobile = false,
  config = null,
  recordTourOpened = vi.fn(() => Promise.resolve(true)),
  setComposerValue = vi.fn(),
  actions = {},
} = {}) {
  document.body.innerHTML = '<input id="cmd" />'
  window.APP_CONFIG = config || {
    tour_enabled: true,
    tour_version: 1,
    tour_chapters: [
      {
        id: 'running_commands',
        title: 'Running commands',
        summary: 'Run a command.\nWatch output stream.',
        sample: 'dig darklab.sh A',
        illustration: 'terminal_stream',
      },
      {
        id: 'history',
        title: 'History',
        summary: 'Find saved runs.',
        sample: 'history',
        illustration: 'history_rows',
      },
    ],
  }
  window.useMobileTerminalViewportMode = () => mobile
  window._recordTourOpenedOnceThisSession = recordTourOpened
  const refocusComposerAfterAction = vi.fn()
  window.refocusComposerAfterAction = refocusComposerAfterAction
  window.setComposerValue = setComposerValue
  window.cmdInput = document.getElementById('cmd')
  Object.entries(actions).forEach(([key, value]) => {
    window[key] = value
  })

  return {
    ...fromDomScripts(
      ['app/static/js/tour_modal.js'],
      {
        document,
        window,
        getAppConfig: () => window.APP_CONFIG,
        refocusComposerAfterAction,
        bindFocusTrap,
        setComposerValue,
        setTimeout: (fn) => {
          fn()
          return 0
        },
        requestAnimationFrame: (fn) => fn(),
        Event,
      },
      `{
        openTourModal: exportedOpenTourModal,
        closeTourModal: exportedCloseTourModal,
        closeTopmostDismissible: window.closeTopmostDismissible,
        _renderTourIllustration: exportedRenderTourIllustration,
        _visibleTourModalChapters: exportedVisibleTourModalChapters,
      }`,
      'window.refocusComposerAfterAction = refocusComposerAfterAction; window.bindFocusTrap = bindFocusTrap; window.setComposerValue = setComposerValue;',
    ),
    recordTourOpened,
    refocusComposerAfterAction,
    setComposerValue,
    actions,
  }
}

describe('tour modal renderer', () => {
  it('opens the desktop visual tour, records the version, and binds the focus trap', () => {
    const { openTourModal, recordTourOpened } = loadTourModal()

    expect(openTourModal()).toBe(true)

    const overlay = document.getElementById('tour-overlay')
    expect(overlay?.classList.contains('open')).toBe(true)
    expect(document.getElementById('tour-modal')?.dataset.focusTrapBound).toBe('1')
    expect(document.getElementById('tour-chapter-title')?.textContent).toBe('Running commands')
    expect([...document.querySelectorAll('#tour-chapter-summary p')].map(p => p.textContent)).toEqual([
      'Run a command. Watch output stream.',
    ])
    expect(recordTourOpened).toHaveBeenCalledTimes(1)
  })

  it('navigates chapters with the shared pressable controls', () => {
    const { openTourModal } = loadTourModal()
    openTourModal()

    document.getElementById('tour-next-btn')?.click()
    expect(document.getElementById('tour-chapter-title')?.textContent).toBe('History')
    expect(document.querySelector('.tour-step-dot[aria-current="step"]')?.dataset.tourStep).toBe('1')

    document.getElementById('tour-prev-btn')?.click()
    expect(document.getElementById('tour-chapter-title')?.textContent).toBe('Running commands')
  })

  it('runs the visual tour Try this actions and closes the carousel', () => {
    const setComposerValue = vi.fn()
    const { openTourModal } = loadTourModal({ setComposerValue })
    openTourModal()

    const chip = document.querySelector('.tour-sample-chip')
    expect(chip).not.toBeNull()
    expect(chip?.dataset.pressableBound).toBe('1')
    chip?.dispatchEvent(new window.Event('click', { bubbles: true }))

    expect(window.refocusComposerAfterAction).toHaveBeenCalled()
    expect(setComposerValue).toHaveBeenCalledWith(
      'dig darklab.sh A',
      'dig darklab.sh A'.length,
      'dig darklab.sh A'.length,
      { dispatch: false },
    )
    expect(window.refocusComposerAfterAction).toHaveBeenCalled()
    expect(document.getElementById('tour-overlay')?.classList.contains('open')).toBe(false)

    const openHistory = vi.fn()
    const openWorkflows = vi.fn()
    const openProjects = vi.fn()
    const openOptions = vi.fn()
    const activateOptionsTab = vi.fn()
    const openAtlas = vi.fn()
    const openFiles = vi.fn()
    const openFaq = vi.fn()
    const modalConfig = {
      tour_enabled: true,
      tour_version: 1,
      tour_chapters: [
        { id: 'autocomplete', title: 'Autocomplete', sample: 'nmap -sV darklab.sh', illustration: 'tab_complete' },
        { id: 'history', title: 'History', sample: 'history', illustration: 'history_rows' },
        { id: 'workflows', title: 'Guided Workflows', sample: 'workflow list', illustration: 'workflow_steps' },
        { id: 'projects', title: 'Projects', sample: 'project help', illustration: 'project_summary' },
        { id: 'team_mode', title: 'Team-Mode', sample: 'team help', illustration: 'team_scope' },
        {
          id: 'atlas',
          title: 'Atlas',
          summary: 'Atlas keeps entities together.\nIntel and project links stay nearby.',
          sample: 'intel domain darklab.sh',
          illustration: 'atlas_entities',
        },
        { id: 'session_files', title: 'Files', sample: 'file list', illustration: 'files_panel' },
        { id: 'session_tokens', title: 'Tokens', sample: 'session-token', illustration: 'session_token' },
        { id: 'closer', title: 'Next', sample: 'help', illustration: 'next_steps' },
      ],
    }
    const secondComposer = vi.fn()
    const { openTourModal: openSecondTour } = loadTourModal({
      config: modalConfig,
      setComposerValue: secondComposer,
      actions: {
        toggleHistoryPanelSurface: openHistory,
        openWorkflows,
        openProjectWorkspace: openProjects,
        openOptions,
        activateOptionsTab,
        openAtlas,
        openWorkspace: openFiles,
        openFaq,
      },
    })
    openSecondTour({ chapterId: 'autocomplete' })
    expect(document.querySelector('.tour-sample-chip')?.textContent).toBe('nmap -sV -')
    document.querySelector('.tour-sample-chip')?.dispatchEvent(new window.Event('click', { bubbles: true }))
    expect(secondComposer).toHaveBeenCalledWith('nmap -sV -', 'nmap -sV -'.length, 'nmap -sV -'.length, { dispatch: false })
    expect(document.getElementById('tour-overlay')?.classList.contains('open')).toBe(false)

    ;[
      ['history', openHistory, [true]],
      ['workflows', openWorkflows, []],
      ['projects', openProjects, []],
      ['team_mode', openOptions, []],
      ['atlas', openAtlas, [{ source: 'tour' }]],
      ['session_files', openFiles, []],
      ['session_tokens', openOptions, []],
      ['closer', openFaq, []],
    ].forEach(([chapterId, spy, args]) => {
      openSecondTour({ chapterId })
      if (chapterId === 'atlas') {
        expect([...document.querySelectorAll('#tour-chapter-summary p')].map(p => p.textContent)).toEqual([
          'Atlas keeps entities together. Intel and project links stay nearby.',
        ])
      }
      document.querySelector('.tour-sample-chip')?.dispatchEvent(new window.Event('click', { bubbles: true }))
      expect(spy).toHaveBeenLastCalledWith(...args)
      if (chapterId === 'team_mode') {
        expect(activateOptionsTab).toHaveBeenLastCalledWith('teams', { persist: false, focus: true })
      }
      expect(document.getElementById('tour-overlay')?.classList.contains('open')).toBe(false)
    })
  })

  it('closes through the shared dismissible dispatcher and backdrop', () => {
    const { openTourModal, closeTopmostDismissible } = loadTourModal()
    const returnFocus = document.createElement('button')
    returnFocus.focus = vi.fn()
    document.body.appendChild(returnFocus)
    openTourModal({ returnFocus })

    expect(closeTopmostDismissible()).toBe(true)
    expect(document.getElementById('tour-overlay')?.classList.contains('open')).toBe(false)
    expect(returnFocus.focus).toHaveBeenCalledWith({ preventScroll: true })

    openTourModal()
    const overlay = document.getElementById('tour-overlay')
    overlay?.dispatchEvent(new window.MouseEvent('click', { bubbles: true }))
    expect(overlay?.classList.contains('open')).toBe(false)
  })

  it('stays unavailable when the tour is disabled, empty, or on mobile', () => {
    expect(loadTourModal({ mobile: true }).openTourModal()).toBe(false)
    expect(loadTourModal({ config: { tour_enabled: false, tour_chapters: [{ title: 'Hidden' }] } }).openTourModal()).toBe(false)
    expect(loadTourModal({ config: { tour_enabled: true, tour_chapters: [] } }).openTourModal()).toBe(false)
  })

  it('renders each configured illustration key with a themed mini card fallback', () => {
    const { _renderTourIllustration } = loadTourModal()
    ;[
      'terminal_stream',
      'tab_complete',
      'history_rows',
      'compare_runs',
      'workflow_steps',
      'project_summary',
      'team_scope',
      'atlas_entities',
      'files_panel',
      'pty_terminal',
      'session_token',
      'next_steps',
    ].forEach((key) => {
      const node = _renderTourIllustration(key)
      expect(node.classList.contains(`tour-visual-${key}`)).toBe(true)
      expect(node.textContent.trim().length).toBeGreaterThan(0)
    })
    const historyNode = _renderTourIllustration('history_rows')
    expect(historyNode.querySelectorAll('.tour-history-entry')).toHaveLength(2)
    expect(historyNode.querySelector('.tour-history-kind')?.textContent).toBe('RUN')
    expect(historyNode.querySelector('.tour-history-exit')?.textContent).toBe('exit 0')
    const compareNode = _renderTourIllustration('compare_runs')
    expect(compareNode.querySelectorAll('.tour-compare-run-card')).toHaveLength(2)
    expect(compareNode.querySelectorAll('.tour-compare-pane')).toHaveLength(2)
    expect(compareNode.querySelector('.tour-compare-findings-title')?.textContent).toContain('Added findings')
    const atlasNode = _renderTourIllustration('atlas_entities')
    expect(atlasNode.querySelectorAll('.tour-atlas-tab')).toHaveLength(3)
    expect(atlasNode.querySelector('.tour-atlas-tab.is-active')?.textContent).toContain('Hosts/IPs')
    expect(atlasNode.querySelector('.tour-atlas-value')?.textContent).toBe('104.21.4.35')
    const teamNode = _renderTourIllustration('team_scope')
    expect(teamNode.querySelector('.tour-atlas-value')?.textContent).toBe('Red Team')
    expect(teamNode.textContent).toContain('operator')
    expect(_renderTourIllustration('unknown').classList.contains('tour-visual-terminal_stream')).toBe(true)
  })

  it('renders the running command exit row like terminal success output', () => {
    const { _renderTourIllustration } = loadTourModal()
    const node = _renderTourIllustration('terminal_stream')
    const exitLine = node.querySelector('.tour-mini-line.is-exit-ok')

    expect(exitLine?.textContent).toBe('[exit 0 · 2 lines · 0.2s]')
  })
})
