import { vi } from 'vitest'
import { fromDomScripts } from './helpers/extract.js'

function loadTourModal({
  mobile = false,
  config = null,
  recordTourOpened = vi.fn(() => Promise.resolve(true)),
  setComposerValue = vi.fn(),
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

  return {
    ...fromDomScripts(
      ['app/static/js/tour_modal.js'],
      {
        document,
        window,
        refocusComposerAfterAction,
        setComposerValue,
        setTimeout: (fn) => {
          fn()
          return 0
        },
        requestAnimationFrame: (fn) => fn(),
        Event,
      },
      `{
        openTourModal: window.openTourModal,
        closeTourModal: window.closeTourModal,
        closeTopmostDismissible: window.closeTopmostDismissible,
        _renderTourIllustration: window._renderTourIllustration,
        _visibleTourModalChapters: window._visibleTourModalChapters,
      }`,
      'window.refocusComposerAfterAction = refocusComposerAfterAction; window.setComposerValue = setComposerValue;',
    ),
    recordTourOpened,
    refocusComposerAfterAction,
    setComposerValue,
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

  it('loads sample chips into the composer without running them', () => {
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
      'files_panel',
      'pty_terminal',
      'session_token',
      'next_steps',
    ].forEach((key) => {
      const node = _renderTourIllustration(key)
      expect(node.classList.contains(`tour-visual-${key}`)).toBe(true)
      expect(node.textContent.trim().length).toBeGreaterThan(0)
    })
    expect(_renderTourIllustration('unknown').classList.contains('tour-visual-terminal_stream')).toBe(true)
  })
})
