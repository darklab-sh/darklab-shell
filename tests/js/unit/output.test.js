import { fromDomScripts } from './helpers/extract.js'

function loadOutputFns({ appConfig = {}, extraGlobals = {} } = {}) {
  class FakeAnsiUp {
    constructor() {
      this.use_classes = false
    }

    ansi_to_html(s) {
      return '<em>' + s + '</em>'
    }
  }

  return fromDomScripts(
    ['app/static/js/output_core.js', 'app/static/js/output.js'],
    {
      document,
      AnsiUp: FakeAnsiUp,
      activeTabId: 'tab-1',
      tabs: [{ id: 'tab-1', rawLines: [], runStart: 1000 }],
      APP_CONFIG: { max_output_lines: 2, ...appConfig },
      getOutput: () => document.getElementById('out'),
      shellPromptWrap: document.getElementById('shell-prompt-wrap'),
      ...extraGlobals,
    },
    `{
    appendLine,
    appendLines,
    _restoreOutputTailAfterLayout,
    _setTsMode,
    _setLnMode,
    buildPromptLabel,
    currentPromptWorkspacePath,
    _getTabs: () => tabs,
  }`,
    'setTabs(tabs); setActiveTabId(activeTabId);',
  )
}

describe('appendLine', () => {
  beforeEach(() => {
    document.body.className = ''
    document.body.innerHTML = `
      <div id="out" class="output">
        <div id="shell-prompt-wrap" class="prompt-wrap shell-prompt-wrap">
          <span class="prompt-prefix">anon@darklab:~$</span>
          <div class="shell-prompt-line" id="shell-prompt-line" aria-hidden="true">
            <span class="shell-prompt-text" id="shell-prompt-text"></span>
          </div>
        </div>
      </div>
    `
  })

  it('renders notice lines with textContent (not HTML)', () => {
    const { appendLine } = loadOutputFns()

    appendLine('<img src=x onerror=alert(1)>', 'notice', 'tab-1')

    const line = document.querySelector('.line.notice')
    expect(line).not.toBeNull()
    expect(line.innerHTML).not.toContain('<img')
    expect(line.textContent).toContain('<img src=x onerror=alert(1)>')
  })

  it('renders non-plain classes through ansi_to_html', () => {
    const { appendLine } = loadOutputFns()

    appendLine('hello', '', 'tab-1')

    const line = document.querySelector('.line')
    expect(line.innerHTML).toContain('<em>hello</em>')
  })

  it('renders shell as a normal workspace folder in the prompt', () => {
    const { buildPromptLabel, currentPromptWorkspacePath } = loadOutputFns({
      appConfig: { workspace_enabled: true, prompt_prefix: 'anon@darklab:~$' },
      extraGlobals: {
        _workspaceCwd: () => 'shell',
        workspaceDisplayPath: path => {
          const normalized = String(path || '').split('/').filter(Boolean).join('/')
          return normalized ? `/${normalized}` : '/'
        },
      },
    })

    expect(currentPromptWorkspacePath()).toBe('/shell')
    expect(buildPromptLabel()).toBe('anon@darklab:/shell $')
  })

  it('falls back to plain-text rendering when AnsiUp is unavailable', () => {
    const { appendLine } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/output_core.js', 'app/static/js/output.js'],
      {
        document,
        activeTabId: 'tab-1',
        tabs: [{ id: 'tab-1', rawLines: [], runStart: 1000 }],
        APP_CONFIG: { max_output_lines: 2 },
        getOutput: () => document.getElementById('out'),
        shellPromptWrap: document.getElementById('shell-prompt-wrap'),
      },
      `{
      appendLine,
    }`,
      'setTabs(tabs); setActiveTabId(activeTabId);',
    )

    appendLine('plain <b>text</b>', '', 'tab-1')

    const line = document.querySelector('.line')
    expect(line.innerHTML).toContain('plain &lt;b&gt;text&lt;/b&gt;')
  })

  it('wraps output content in a line-content container so prefix mode does not reshape the line flow', () => {
    const { appendLine } = loadOutputFns()

    appendLine('hello', '', 'tab-1')

    const line = document.querySelector('.line')
    expect(line.querySelector('.line-content')).not.toBeNull()
    expect(line.firstElementChild?.classList.contains('line-content')).toBe(true)
    expect(line.querySelector('.line-content').innerHTML).toContain('<em>hello</em>')
  })

  it('trims old lines and keeps rawLines in sync', () => {
    const { appendLine, _getTabs } = loadOutputFns()

    appendLine('one', '', 'tab-1')
    appendLine('two', '', 'tab-1')
    appendLine('three', '', 'tab-1')

    const lines = document.querySelectorAll('.line')
    expect(lines).toHaveLength(2)
    expect(lines[0].textContent).toContain('two')
    expect(lines[1].textContent).toContain('three')

    const tab = _getTabs()[0]
    expect(tab.rawLines).toHaveLength(2)
    expect(tab.rawLines[0].text).toBe('two')
    expect(tab.rawLines[1].text).toBe('three')
  })

  it('avoids full output scans while trimming in default prefix mode', () => {
    const { appendLine } = loadOutputFns()
    const out = document.getElementById('out')
    out.querySelectorAll = () => {
      throw new Error('appendLine should not full-scan output rows when prefixes are inactive')
    }

    appendLine('one', '', 'tab-1')
    appendLine('two', '', 'tab-1')
    appendLine('three', '', 'tab-1')

    const lines = out.getElementsByClassName('line')
    expect(lines).toHaveLength(2)
    expect(lines[0].textContent).toContain('two')
    expect(lines[1].textContent).toContain('three')
  })

  it('keeps absolute line numbers after max-line trimming', () => {
    const { appendLine, _setLnMode } = loadOutputFns()
    const out = document.getElementById('out')

    _setLnMode('on')
    out.querySelectorAll = () => {
      throw new Error('appendLine should not full-scan output rows when line numbers are active')
    }

    appendLine('one', '', 'tab-1')
    appendLine('two', '', 'tab-1')
    appendLine('three', '', 'tab-1')

    const lines = out.getElementsByClassName('line')
    expect(lines).toHaveLength(2)
    expect(lines[0].dataset.lineNumber).toBe('2')
    expect(lines[1].dataset.lineNumber).toBe('3')
    expect(document.getElementById('shell-prompt-wrap')?.dataset.lineNumber).toBe('4')
  })

  it('preserves absolute line numbers when line-number mode is enabled later', () => {
    const { appendLine, _setLnMode } = loadOutputFns()

    appendLine('one', '', 'tab-1')
    appendLine('two', '', 'tab-1')
    appendLine('three', '', 'tab-1')
    _setLnMode('on')

    const lines = document.getElementById('out').getElementsByClassName('line')
    expect(lines).toHaveLength(2)
    expect(lines[0].textContent).toContain('two')
    expect(lines[0].dataset.lineNumber).toBe('2')
    expect(lines[1].dataset.lineNumber).toBe('3')
    expect(document.getElementById('shell-prompt-wrap')?.dataset.lineNumber).toBe('4')
  })

  it('adds timestamp dataset fields', () => {
    const { appendLine } = loadOutputFns()

    appendLine('timed line', '', 'tab-1')

    const line = document.querySelector('.line')
    expect(line.dataset.tsC).toMatch(/^\d{2}:\d{2}:\d{2}$/)
    expect(line.dataset.tsE).toMatch(/^\+\d+\.\d+s$/)
  })

  it('stores server-provided signal metadata on DOM lines and rawLines', () => {
    const { appendLine, _getTabs } = loadOutputFns()

    appendLine('443/tcp open https', '', 'tab-1', {
      signals: ['findings'],
      line_index: 7,
      line_number: 1,
      command_root: 'nmap',
      target: 'ip.darklab.sh',
    })

    const line = document.querySelector('.line')
    expect(line?.dataset.signals).toBe('findings')
    expect(line?.dataset.lineIndex).toBe('7')
    expect(line?.dataset.commandRoot).toBe('nmap')
    expect(line?.dataset.signalTarget).toBe('ip.darklab.sh')

    expect(_getTabs()[0].rawLines[0]).toMatchObject({
      text: '443/tcp open https',
      signals: ['findings'],
      line_index: 7,
      line_number: 1,
      command_root: 'nmap',
      target: 'ip.darklab.sh',
    })
    expect(_getTabs()[0]._outputSignalCounts).toEqual({
      findings: 1,
      warnings: 0,
      errors: 0,
      summaries: 0,
    })
    expect(_getTabs()[0]._outputSignalCountsValid).toBe(true)
  })

  it('keeps cached signal counts in sync when old lines are trimmed', () => {
    const { appendLine, _getTabs } = loadOutputFns({ appConfig: { max_output_lines: 2 } })

    appendLine('old finding', '', 'tab-1', { signals: ['findings'], command_root: 'nmap' })
    appendLine('warning', 'notice', 'tab-1', { signals: ['warnings'], command_root: 'nmap' })
    appendLine('plain', '', 'tab-1')

    expect(_getTabs()[0]._outputSignalCounts).toEqual({
      findings: 0,
      warnings: 1,
      errors: 0,
      summaries: 0,
    })
  })

  it('uses +0.0s for lines without a true elapsed runtime', () => {
    const { appendLine } = loadOutputFns({
      extraGlobals: {
        tabs: [{ id: 'tab-1', rawLines: [], runStart: 0 }],
      },
    })

    appendLine('synthetic line', 'fake-plain', 'tab-1')

    const line = document.querySelector('.line.fake-plain')
    expect(line?.dataset.tsE).toBe('+0.0s')
  })

  it('toggles the line-number body class and button labels', () => {
    document.body.innerHTML = `
      <button id="ln-btn"></button>
      <button id="ts-btn"></button>
      <div id="out"></div>
    `
    const { _setLnMode } = loadOutputFns()

    _setLnMode('on')
    expect(document.body.classList.contains('ln-on')).toBe(true)
    expect(document.getElementById('ln-btn').textContent).toBe('line numbers: on')

    _setLnMode('off')
    expect(document.body.classList.contains('ln-on')).toBe(false)
    expect(document.getElementById('ln-btn').textContent).toBe('line numbers: off')
  })

  it('numbers the prompt line after the current output rows', () => {
    const { appendLine, _setLnMode } = loadOutputFns()

    _setLnMode('on')
    appendLine('hello', '', 'tab-1')

    expect(document.querySelector('.line')?.dataset.prefix).toBe('')
    expect(document.getElementById('shell-prompt-wrap')?.dataset.prefix).toBe('')
    expect(document.getElementById('out').style.getPropertyValue('--output-prefix-width')).toBe('1ch')
  })

  it('does not assign prefixes to welcome animation lines', () => {
    const { appendLine, _setLnMode } = loadOutputFns()

    _setLnMode('on')
    appendLine('loading /', 'welcome-status-line', 'tab-1')
    appendLine('hello', '', 'tab-1')

    expect(document.querySelector('.line.welcome-status-line')?.dataset.prefix).toBe('')
    expect(document.querySelector('.line:not(.welcome-status-line)')?.dataset.prefix).toBe('')
    expect(document.getElementById('shell-prompt-wrap')?.dataset.prefix).toBe('')
    expect(document.getElementById('out').style.getPropertyValue('--output-prefix-width')).toBe('1ch')
  })

  it('does not assign prefixes to synthetic summary lines', () => {
    const { appendLine, _setLnMode, _setTsMode } = loadOutputFns()

    _setLnMode('on')
    _setTsMode('elapsed')
    appendLine('Command Findings:', 'fake-signal-summary-header', 'tab-1')
    appendLine('findings (2)', 'fake-signal-summary-section', 'tab-1')
    appendLine('- 443/tcp open https', 'fake-signal-summary-row', 'tab-1')

    const lines = document.querySelectorAll('.line')
    expect(lines[0]?.dataset.prefix || '').toBe('')
    expect(lines[1]?.dataset.prefix || '').toBe('')
    expect(lines[2]?.dataset.prefix || '').toBe('')
    expect(document.getElementById('shell-prompt-wrap')?.dataset.prefix).toBe('+0.0s')
  })

  it('combines line numbers and timestamps into a compact shared prefix', () => {
    const { appendLine, _setLnMode, _setTsMode } = loadOutputFns()

    _setLnMode('on')
    _setTsMode('elapsed')

    appendLine('timed line', '', 'tab-1')

    expect(document.querySelector('.line')?.dataset.prefix).toMatch(/^\+\d+\.\ds$/)
    expect(document.getElementById('shell-prompt-wrap')?.dataset.prefix).toBe('+0.0s')
    expect(document.getElementById('out').style.getPropertyValue('--output-prefix-width')).toBe('10ch')
  })

  it('shows +0.0s for the active prompt in elapsed mode', () => {
    const { _setTsMode } = loadOutputFns()

    _setTsMode('elapsed')

    expect(document.getElementById('shell-prompt-wrap')?.dataset.prefix).toBe('+0.0s')
  })

  it('does nothing when there is no output container for the target tab', () => {
    document.body.innerHTML = ''
    const { appendLine, _getTabs } = loadOutputFns()

    appendLine('orphan line', '', 'missing-tab')

    expect(document.querySelector('.line')).toBeNull()
    expect(_getTabs()[0].rawLines).toHaveLength(0)
  })

  it('re-sticks restored output to the tail after delayed layout growth', () => {
    const timers = []
    const { _restoreOutputTailAfterLayout, _getTabs } = loadOutputFns({
      appConfig: { max_output_lines: 100 },
      extraGlobals: {
        setTimeout: (fn, delay) => {
          timers.push({ fn, delay })
          return timers.length
        },
      },
    })
    timers.length = 0
    const out = document.getElementById('out')
    const tab = _getTabs()[0]
    let scrollTop = 0
    let scrollHeight = 900

    Object.defineProperty(out, 'clientHeight', { configurable: true, get: () => 300 })
    Object.defineProperty(out, 'scrollHeight', { configurable: true, get: () => scrollHeight })
    Object.defineProperty(out, 'scrollTop', {
      configurable: true,
      get: () => scrollTop,
      set: (value) => {
        scrollTop = value
      },
    })

    _restoreOutputTailAfterLayout(out, tab)

    expect(timers.map(timer => timer.delay)).toEqual([0, 16, 64, 160, 320])
    expect(scrollTop).toBe(900)
    expect(tab.followOutput).toBe(true)
    expect(tab.suppressOutputScrollTracking).toBe(true)

    scrollHeight = 1400
    timers.filter(timer => timer.delay <= 64).forEach(timer => timer.fn())
    expect(scrollTop).toBe(1400)

    scrollHeight = 1800
    timers.filter(timer => timer.delay > 64).forEach(timer => timer.fn())
    expect(scrollTop).toBe(1800)
    expect(tab.suppressOutputScrollTracking).toBe(false)
  })

  it('batches large bursts of output and finishes rendering on the next tick', async () => {
    const { appendLine } = loadOutputFns({ appConfig: { max_output_lines: 100 } })

    for (let i = 1; i <= 65; i++) {
      appendLine(`line ${i}`, '', 'tab-1')
    }

    expect(document.querySelectorAll('.line')).toHaveLength(60)

    await new Promise((resolve) => setTimeout(resolve, 25))

    const lines = document.querySelectorAll('.line')
    expect(lines).toHaveLength(65)
    expect(lines[0].textContent).toContain('line 1')
    expect(lines[64].textContent).toContain('line 65')
  })

  it('queues multi-line appends in chunks and updates raw lines once flushed', async () => {
    const { appendLines, _getTabs } = loadOutputFns({ appConfig: { max_output_lines: 100 } })

    await appendLines(Array.from({ length: 65 }, (_, index) => ({
      text: `line ${index + 1}`,
      cls: '',
    })), 'tab-1')

    expect(document.querySelectorAll('.line')).toHaveLength(0)

    await new Promise((resolve) => setTimeout(resolve, 25))

    const lines = document.querySelectorAll('.line')
    expect(lines).toHaveLength(65)
    expect(lines[0].textContent).toContain('line 1')
    expect(lines[64].textContent).toContain('line 65')
    expect(_getTabs()[0].rawLines).toHaveLength(65)
  })

  it('uses delayed tail restore for large mobile output bursts', () => {
    document.body.classList.add('mobile-terminal-mode')
    const timers = []
    const { appendLine, _getTabs } = loadOutputFns({
      appConfig: { max_output_lines: 100 },
      extraGlobals: {
        setTimeout: (fn, delay) => {
          timers.push({ fn, delay })
          return timers.length
        },
      },
    })
    const out = document.getElementById('out')
    const tab = _getTabs()[0]
    let scrollTop = 0
    let scrollHeight = 900

    Object.defineProperty(out, 'clientHeight', { configurable: true, get: () => 300 })
    Object.defineProperty(out, 'scrollHeight', { configurable: true, get: () => scrollHeight })
    Object.defineProperty(out, 'scrollTop', {
      configurable: true,
      get: () => scrollTop,
      set: (value) => {
        scrollTop = value
      },
    })

    for (let i = 1; i <= 60; i++) {
      appendLine(`line ${i}`, '', 'tab-1')
    }
    timers.length = 0

    appendLine('line 61', '', 'tab-1')

    expect(timers.map(timer => timer.delay)).toEqual([16])
    timers[0].fn()
    expect(timers.map(timer => timer.delay)).toEqual([16, 0, 16, 64, 160, 320])
    expect(scrollTop).toBe(900)
    expect(tab.followOutput).toBe(true)
    expect(tab.suppressOutputScrollTracking).toBe(true)

    scrollHeight = 1600
    timers.slice(1).forEach(timer => timer.fn())
    expect(scrollTop).toBe(1600)
    expect(tab.suppressOutputScrollTracking).toBe(false)
  })
})
