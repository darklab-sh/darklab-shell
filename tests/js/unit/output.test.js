import { fromDomScripts } from './helpers/extract.js'

function loadOutputFns({ appConfig = {}, extraGlobals = {}, AnsiUpCtor = null } = {}) {
  class FakeAnsiUp {
    constructor() {
      this.use_classes = false
    }

    ansi_to_html(s) {
      return '<em>' + s + '</em>'
    }
  }

  return fromDomScripts(
    ['app/static/js/core/run_output_model.js', 'app/static/js/core/output_core.js', 'app/static/js/output.js'],
    {
      document,
      AnsiUp: AnsiUpCtor || FakeAnsiUp,
      activeTabId: 'tab-1',
      tabs: [{ id: 'tab-1', st: 'running', rawLines: [], runStart: 1000 }],
      APP_CONFIG: { max_output_lines: 2, ...appConfig },
      getOutput: () => document.getElementById('out'),
      shellPromptWrap: document.getElementById('shell-prompt-wrap'),
      ...extraGlobals,
    },
    `{
    appendLine,
    appendLines,
    appendHighVolumeOutputFinalSummary,
    disableHighVolumeOutputResumeControls,
    renderRestoredTabOutput,
    resetHighVolumeOutputState,
    _restoreOutputTailAfterLayout,
    _setTsMode,
    _setLnMode,
    buildPromptLabel,
    currentPromptWorkspacePath,
    _showOutputEntityMenu,
    _getTabs: () => tabs,
  }`,
    'setTabs(tabs); setActiveTabId(activeTabId);',
  )
}

describe('appendLine', () => {
  beforeEach(() => {
    delete document._darklabHighVolumeOutputBound
    delete document._darklabOutputEntityTokensBound
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

  it('renders typed notice events with textContent and legacy CSS class', () => {
    const { appendLine } = loadOutputFns()

    appendLine({
      text: '<strong>typed notice</strong>',
      kind: 'notice',
      role: 'body',
    }, 'tab-1')

    const line = document.querySelector('.line.notice')
    expect(line).not.toBeNull()
    expect(line.innerHTML).not.toContain('<strong>')
    expect(line.textContent).toContain('<strong>typed notice</strong>')
  })

  it('renders typed prompt roles like legacy prompt-echo lines', () => {
    const { appendLine, _getTabs } = loadOutputFns()

    appendLine({ text: 'nmap darklab.sh', kind: 'info', role: 'prompt-echo' }, 'tab-1')

    const line = document.querySelector('.line.prompt-echo')
    expect(line).not.toBeNull()
    expect(line.querySelector('.prompt-prefix')?.textContent).toContain('anon@darklab')
    expect(line.textContent).toContain('nmap darklab.sh')
    expect(_getTabs()[0].rawLines[0].cls).toBe('prompt-echo')
    expect(_getTabs()[0].rawLines[0].text).toContain('nmap darklab.sh')
  })

  it('round trips wire event input through fromWireLineEvent before rendering', () => {
    const { appendLine } = loadOutputFns()

    appendLine({
      text: 'still plain',
      cls: '',
      kind: 'notice',
      role: 'body',
    }, 'tab-1')

    const line = document.querySelector('.line.notice')
    expect(line).not.toBeNull()
    expect(line.textContent).toContain('still plain')
  })

  it('renders non-plain classes through ansi_to_html', () => {
    const { appendLine } = loadOutputFns()

    appendLine('hello', '', 'tab-1')

    const line = document.querySelector('.line')
    expect(line.innerHTML).toContain('<em>hello</em>')
  })

  it('isolates ANSI parser state between tabs', () => {
    class StatefulAnsiUp {
      constructor() {
        this.use_classes = false
        this.color = ''
      }

      ansi_to_html(text) {
        const raw = String(text || '')
        if (raw.includes('\x1b[31m')) this.color = 'red'
        if (raw.includes('\x1b[0m')) this.color = ''
        const clean = raw.replace(/\x1b\[[0-9;]*[A-Za-z]/g, '')
        return `<span class="${this.color || 'plain'}">${clean}</span>`
      }
    }
    const { appendLine } = loadOutputFns({
      AnsiUpCtor: StatefulAnsiUp,
      appConfig: { max_output_lines: 10 },
      extraGlobals: {
        tabs: [
          { id: 'tab-1', rawLines: [], runStart: 1000 },
          { id: 'tab-2', rawLines: [], runStart: 1000 },
        ],
      },
    })

    appendLine('\x1b[31mred opener without reset', '', 'tab-1')
    appendLine('plain output in another tab', '', 'tab-2')

    const lines = Array.from(document.querySelectorAll('.line .line-content'))
    expect(lines[0].innerHTML).toContain('class="red"')
    expect(lines[1].innerHTML).toContain('class="plain"')
  })

  it('resets ANSI parser state before replaying restored output', () => {
    class StatefulAnsiUp {
      constructor() {
        this.use_classes = false
        this.color = ''
      }

      ansi_to_html(text) {
        const raw = String(text || '')
        if (raw.includes('\x1b[31m')) this.color = 'red'
        if (raw.includes('\x1b[0m')) this.color = ''
        const clean = raw.replace(/\x1b\[[0-9;]*[A-Za-z]/g, '')
        return `<span class="${this.color || 'plain'}">${clean}</span>`
      }
    }
    const { appendLine, renderRestoredTabOutput } = loadOutputFns({
      AnsiUpCtor: StatefulAnsiUp,
      appConfig: { max_output_lines: 10 },
    })

    appendLine('\x1b[31mred opener without reset', '', 'tab-1')
    renderRestoredTabOutput('tab-1', [{ text: 'restored plain output', cls: '' }])

    const line = document.querySelector('.line .line-content')
    expect(document.querySelectorAll('.line')).toHaveLength(1)
    expect(line.innerHTML).toContain('class="plain"')
    expect(line.innerHTML).not.toContain('class="red"')
  })

  it('renders shell as a normal workspace folder in the prompt', () => {
    const { buildPromptLabel, currentPromptWorkspacePath } = loadOutputFns({
      appConfig: { workspace_enabled: true, prompt_username: 'anon', prompt_domain: 'darklab.sh' },
      extraGlobals: {
        _workspaceCwd: () => 'shell',
        workspaceDisplayPath: path => {
          const normalized = String(path || '').split('/').filter(Boolean).join('/')
          return normalized ? `/${normalized}` : '/'
        },
      },
    })

    expect(currentPromptWorkspacePath()).toBe('/shell')
    expect(buildPromptLabel()).toBe('anon@darklab.sh:/shell $')
  })

  it('falls back to plain-text rendering when AnsiUp is unavailable', () => {
    const { appendLine } = fromDomScripts(
      ['app/static/js/core/utils.js', 'app/static/js/core/output_core.js', 'app/static/js/output.js'],
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

    appendLine('scan ip.darklab.sh 443/tcp open https', '', 'tab-1', {
      signals: ['findings'],
      line_index: 7,
      line_number: 1,
      command_root: 'nmap',
      target: 'ip.darklab.sh',
      entities: [{
        type: 'domain',
        value: 'ip.darklab.sh',
        canonical_value: 'ip.darklab.sh',
        start: 5,
        end: 18,
      }],
    })

    const line = document.querySelector('.line')
    const token = line?.querySelector('.atlas-entity-token')
    expect(line?.dataset.signals).toBe('findings')
    expect(line?.dataset.lineIndex).toBe('7')
    expect(line?.dataset.commandRoot).toBe('nmap')
    expect(line?.dataset.signalTarget).toBe('ip.darklab.sh')
    expect(token?.dataset.atlasEntityType).toBe('domain')
    expect(token?.dataset.atlasEntityValue).toBe('ip.darklab.sh')
    expect(token?.classList.contains('chip')).toBe(true)
    expect(token?.classList.contains('chip-action')).toBe(true)

    expect(_getTabs()[0].rawLines[0]).toMatchObject({
      text: 'scan ip.darklab.sh 443/tcp open https',
      signals: ['findings'],
      line_index: 7,
      line_number: 1,
      command_root: 'nmap',
      target: 'ip.darklab.sh',
      entities: [{
        type: 'domain',
        canonical_value: 'ip.darklab.sh',
        start: 5,
        end: 18,
      }],
    })
    expect(_getTabs()[0]._outputSignalCounts).toEqual({
      findings: 1,
      warnings: 0,
      errors: 0,
      summaries: 0,
    })
    expect(_getTabs()[0]._outputSignalCountsValid).toBe(true)
  })

  it('falls back to value matching when ANSI makes entity offsets stale', () => {
    class StripAnsiUp {
      constructor() {
        this.use_classes = false
      }

      ansi_to_html(text) {
        return String(text || '').replace(/\x1b\[[0-9;]*[A-Za-z]/g, '')
      }
    }
    const { appendLine } = loadOutputFns({ AnsiUpCtor: StripAnsiUp })

    appendLine('\x1b[31mip.darklab.sh\x1b[0m 443/tcp open https', '', 'tab-1', {
      entities: [{
        type: 'domain',
        value: 'ip.darklab.sh',
        canonical_value: 'ip.darklab.sh',
        start: 0,
        end: 'ip.darklab.sh'.length,
      }],
    })

    const token = document.querySelector('.atlas-entity-token')
    expect(token?.dataset.atlasEntityValue).toBe('ip.darklab.sh')
    expect(token?.textContent).toBe('ip.darklab.sh')
    expect(token?.textContent).not.toContain('\x1b')
  })

  it('supports keyboard navigation and outside-click close in the entity context menu', () => {
    const { appendLine, _showOutputEntityMenu } = loadOutputFns()

    appendLine('scan ip.darklab.sh', '', 'tab-1', {
      entities: [{
        type: 'domain',
        value: 'ip.darklab.sh',
        canonical_value: 'ip.darklab.sh',
        start: 5,
        end: 18,
      }],
    })

    const token = document.querySelector('.atlas-entity-token')
    token?.focus()
    _showOutputEntityMenu(token, 32, 32)

    const menu = document.querySelector('.atlas-output-entity-menu')
    const items = Array.from(menu?.querySelectorAll('[data-output-entity-action]') || [])
    expect(menu).not.toBeNull()
    expect(items).toHaveLength(6)
    expect(document.activeElement?.dataset.outputEntityAction).toBe('open-atlas')

    items[0].dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }))
    expect(document.activeElement?.dataset.outputEntityAction).toBe('edit-metadata')

    items[1].dispatchEvent(new KeyboardEvent('keydown', { key: 'End', bubbles: true }))
    expect(document.activeElement?.dataset.outputEntityAction).toBe('see-run')

    items[5].dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(document.querySelector('.atlas-output-entity-menu')).toBeNull()
    expect(document.activeElement?.dataset.atlasEntityValue).toBe('ip.darklab.sh')

    _showOutputEntityMenu(token, 32, 32)
    expect(document.querySelector('.atlas-output-entity-menu')).not.toBeNull()

    document.body.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    expect(document.querySelector('.atlas-output-entity-menu')).toBeNull()
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

    appendLine('synthetic line', 'builtin-plain', 'tab-1')

    const line = document.querySelector('.line.builtin-plain')
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
    appendLine('Command Findings:', 'builtin-signal-summary-header', 'tab-1')
    appendLine('findings (2)', 'builtin-signal-summary-section', 'tab-1')
    appendLine('- 443/tcp open https', 'builtin-signal-summary-row', 'tab-1')

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

  it('pauses live rendering for high-volume brokered output while keeping raw lines', () => {
    const { appendLine, _getTabs } = loadOutputFns({
      appConfig: {
        high_volume_output_line_threshold: 3,
        high_volume_output_status_interval_lines: 2,
        max_output_lines: 20,
      },
    })

    appendLine('line 1', '', 'tab-1', { live_output: true })
    appendLine('line 2', '', 'tab-1', { live_output: true })
    appendLine('line 3', '', 'tab-1', { live_output: true })
    appendLine('line 4', '', 'tab-1', { live_output: true })

    const renderedText = Array.from(document.querySelectorAll('.line')).map(line => line.textContent)
    expect(renderedText.join('\n')).toContain('line 1')
    expect(renderedText.join('\n')).not.toContain('line 4')
    expect(renderedText.join('\n')).toContain('high-volume output mode: 4 lines received')
    expect(document.querySelector('[data-high-volume-resume-tab="tab-1"]')).not.toBeNull()

    const rawLines = _getTabs()[0].rawLines.map(line => line.text)
    expect(rawLines).toContain('line 4')
  })

  it('binds high-volume resume controls through the shared pressable helper', () => {
    const bindPressable = vi.fn((button, options = {}) => {
      button.dataset.pressableBound = '1'
      button.addEventListener('click', (event) => {
        event.preventDefault()
        options.onActivate?.()
      })
    })
    const { appendLine } = loadOutputFns({
      appConfig: {
        high_volume_output_line_threshold: 1,
        high_volume_output_status_interval_lines: 1,
        max_output_lines: 20,
      },
      extraGlobals: { bindPressable },
    })

    appendLine('line 1', '', 'tab-1', { live_output: true })
    appendLine('line 2', '', 'tab-1', { live_output: true })

    const button = document.querySelector('[data-high-volume-resume-tab="tab-1"]')
    expect(button.dataset.pressableBound).toBe('1')
    expect(bindPressable).toHaveBeenCalledWith(button, expect.objectContaining({ refocusComposer: false }))
  })

  it('resumes live rendering for new high-volume output when requested', () => {
    const { appendLine } = loadOutputFns({
      appConfig: {
        high_volume_output_line_threshold: 1,
        high_volume_output_status_interval_lines: 1,
        max_output_lines: 20,
      },
    })

    appendLine('line 1', '', 'tab-1', { live_output: true })
    appendLine('line 2', '', 'tab-1', { live_output: true })

    document.querySelector('[data-high-volume-resume-tab="tab-1"]').click()
    appendLine('line 3', '', 'tab-1', { live_output: true })

    const renderedText = Array.from(document.querySelectorAll('.line')).map(line => line.textContent).join('\n')
    expect(renderedText).not.toContain('line 2')
    expect(renderedText).toContain('live output rendering resumed after 1 skipped lines')
    expect(renderedText).toContain('line 3')
  })

  it('disables high-volume resume controls once the run is no longer active', () => {
    const { appendLine, disableHighVolumeOutputResumeControls, _getTabs } = loadOutputFns({
      appConfig: {
        high_volume_output_line_threshold: 1,
        high_volume_output_status_interval_lines: 1,
        max_output_lines: 20,
      },
    })

    appendLine('line 1', '', 'tab-1', { live_output: true })
    appendLine('line 2', '', 'tab-1', { live_output: true })
    const button = document.querySelector('[data-high-volume-resume-tab="tab-1"]')

    _getTabs()[0].st = 'ok'
    disableHighVolumeOutputResumeControls('tab-1')
    button.click()
    appendLine('line 3', '', 'tab-1', { live_output: true })

    const renderedText = Array.from(document.querySelectorAll('.line')).map(line => line.textContent).join('\n')
    expect(button.disabled).toBe(true)
    expect(renderedText).not.toContain('live output rendering resumed')
    expect(renderedText).toContain('line 3')
  })

  it('adds a final high-volume summary for skipped live-rendered lines', () => {
    const { appendLine, appendHighVolumeOutputFinalSummary } = loadOutputFns({
      appConfig: {
        high_volume_output_line_threshold: 1,
        high_volume_output_status_interval_lines: 1,
        max_output_lines: 20,
      },
    })

    appendLine('line 1', '', 'tab-1', { live_output: true })
    appendLine('line 2', '', 'tab-1', { live_output: true })
    appendLine('[process exited with code 0]', 'exit-ok', 'tab-1')

    expect(appendHighVolumeOutputFinalSummary('tab-1')).toBe(true)
    expect(appendHighVolumeOutputFinalSummary('tab-1')).toBe(false)

    const renderedText = Array.from(document.querySelectorAll('.line')).map(line => line.textContent).join('\n')
    expect(renderedText).toContain('[process exited with code 0]')
    expect(renderedText).toContain('high-volume output summary: 1 line was not rendered live in this tab')
    expect(renderedText).toContain('retained output follows the normal saved preview and full-output settings')
    expect(renderedText).not.toContain('line 2')
  })

  it('resets high-volume counters for a new run', () => {
    const { appendLine, resetHighVolumeOutputState, _getTabs } = loadOutputFns({
      appConfig: {
        high_volume_output_line_threshold: 1,
        high_volume_output_status_interval_lines: 1,
        max_output_lines: 20,
      },
    })

    appendLine('line 1', '', 'tab-1', { live_output: true })
    appendLine('line 2', '', 'tab-1', { live_output: true })
    resetHighVolumeOutputState('tab-1')
    _getTabs()[0].st = 'running'
    appendLine('line 3', '', 'tab-1', { live_output: true })

    const renderedText = Array.from(document.querySelectorAll('.line')).map(line => line.textContent).join('\n')
    expect(renderedText).not.toContain('high-volume output mode: 3 lines received')
    expect(renderedText).toContain('line 3')
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
