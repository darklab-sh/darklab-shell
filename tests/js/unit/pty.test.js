import { fromScript } from './helpers/extract.js'

const {
  _createPtyTerminalSession,
  _xtermGlobalsAvailable,
  focusActiveInteractivePty,
  isInteractivePtyCommand,
} = fromScript(
  'app/static/js/pty.js',
  '_createPtyTerminalSession',
  '_xtermGlobalsAvailable',
  'focusActiveInteractivePty',
  'isInteractivePtyCommand',
)

describe('interactive PTY terminal', () => {
  beforeEach(() => {
    document.body.innerHTML = ''
    globalThis.tabs = []
    globalThis.activeTabId = null
    delete globalThis.Terminal
    delete globalThis.FitAddon
  })

  it('detects the reserved mtr interactive command form', () => {
    expect(isInteractivePtyCommand('mtr --interactive darklab.sh')).toBe(true)
    expect(isInteractivePtyCommand('mtr darklab.sh')).toBe(false)
    expect(isInteractivePtyCommand('ping --interactive darklab.sh')).toBe(false)
  })

  it('reports missing xterm globals before mounting a PTY terminal', () => {
    expect(_xtermGlobalsAvailable()).toBe(false)
    expect(() => _createPtyTerminalSession(document.createElement('div'))).toThrow(
      /terminal assets/i,
    )
  })

  it('creates an xterm terminal with the fit addon and opens it in the screen', () => {
    const opened = []
    const loadedAddons = []
    class FakeTerminal {
      constructor(options) {
        this.options = options
        this.rows = options.rows
        this.cols = options.cols
      }
      loadAddon(addon) {
        loadedAddons.push(addon)
      }
      open(screen) {
        opened.push(screen)
      }
    }
    class FakeFitAddon {
      fit() {}
    }
    globalThis.Terminal = FakeTerminal
    globalThis.FitAddon = { FitAddon: FakeFitAddon }

    const screen = document.createElement('div')
    const session = _createPtyTerminalSession(screen, 20, 90)

    expect(_xtermGlobalsAvailable()).toBe(true)
    expect(session.term).toBeInstanceOf(FakeTerminal)
    expect(session.fitAddon).toBeInstanceOf(FakeFitAddon)
    expect(session.term.options.rows).toBe(20)
    expect(session.term.options.cols).toBe(90)
    expect(session.term.options.lineHeight).toBeGreaterThanOrEqual(1.35)
    expect(opened).toEqual([screen])
    expect(loadedAddons).toHaveLength(1)
  })

  it('keeps focus on the active PTY terminal while the PTY tab is running', () => {
    const focus = vi.fn()
    document.body.innerHTML = `
      <div class="tab-panel active" data-id="tab-1">
        <div class="pty-screen" data-pty-active="1" data-tab-id="tab-1" tabindex="0"></div>
      </div>
    `
    globalThis.tabs = [{
      id: 'tab-1',
      st: 'running',
      interactivePtyActive: true,
      ptyTerminal: { focus },
    }]
    globalThis.activeTabId = 'tab-1'

    expect(focusActiveInteractivePty()).toBe(true)
    expect(focus).toHaveBeenCalledTimes(1)
  })
})
