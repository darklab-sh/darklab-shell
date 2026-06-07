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
    recordLiveOutputCoalescedLines,
    disableHighVolumeOutputResumeControls,
    renderRestoredTabOutput,
    renderCommandOutcomeSummary,
    setTabCommandOutcomeSummary,
    refreshCommandOutcomeSummaries,
    resetHighVolumeOutputState,
    _restoreOutputTailAfterLayout,
    syncOutputPrefixes,
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
    appendLine('', 'prompt-echo', 'tab-1')

    const line = document.querySelector('.line.prompt-echo')
    expect(line).not.toBeNull()
    expect(line.querySelector('.prompt-prefix')?.textContent).toContain('anon@darklab')
    expect(line.textContent).toContain('nmap darklab.sh')
    const blankPrompt = document.querySelectorAll('.line.prompt-echo')[1]
    expect(blankPrompt.classList.contains('is-blank')).toBe(false)
    expect(blankPrompt.querySelector('.line-content')?.firstElementChild?.classList.contains('prompt-prefix')).toBe(true)
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
    class LinkAnsiUp {
      constructor() {
        this.use_classes = false
      }

      ansi_to_html(text) {
        const raw = String(text || '')
        return raw
          .replace(/\x1b]8;;([^\x07]+)\x07([^\x1b]+)\x1b]8;;\x07/g, '<a href="$1">$2</a>')
          .replace(/^hello$/, '<em>hello</em>')
      }
    }
    const { appendLine } = loadOutputFns({ AnsiUpCtor: LinkAnsiUp, appConfig: { max_output_lines: 10 } })

    appendLine('hello', '', 'tab-1')
    appendLine('README: \x1b]8;;https://example.test\x07README\x1b]8;;\x07', 'builtin-note', 'tab-1')

    const line = document.querySelector('.line:not(.builtin-note)')
    expect(line.innerHTML).toContain('<em>hello</em>')
    const link = document.querySelector('.line.builtin-note a')
    expect(link?.getAttribute('href')).toBe('https://example.test')
    expect(link?.getAttribute('target')).toBe('_blank')
    expect(link?.getAttribute('rel')).toBe('noopener')
    expect(link?.textContent).toBe('README')
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
    appendLine('', '', 'tab-1')

    const line = document.querySelector('.line')
    const blankLine = document.querySelectorAll('.line')[1]
    expect(line.querySelector('.line-content')).not.toBeNull()
    expect(line.firstElementChild?.classList.contains('line-content')).toBe(true)
    expect(line.querySelector('.line-content').innerHTML).toContain('<em>hello</em>')
    expect(blankLine.classList.contains('is-blank')).toBe(true)
    expect(blankLine.querySelector('.line-content')?.textContent).toBe('')
  })

  it('renders builtin help and FAQ rows as structured terminal content', () => {
    const activateFaqCommandChip = vi.fn()
    const { appendLine } = loadOutputFns({
      appConfig: { max_output_lines: 20 },
      extraGlobals: { activateFaqCommandChip },
    })

    appendLine('  history  Show saved runs', 'builtin-help-row', 'tab-1')
    appendLine('Q  How do I export?', 'builtin-faq-q', 'tab-1')
    appendLine('A  Run `help` first.', 'builtin-faq-a', 'tab-1')

    const helpLine = document.querySelector('.line.builtin-help-row')
    expect(helpLine.querySelector('.faq-chip[data-faq-command="history"]')).toBeNull()
    expect(helpLine.querySelector('.builtin-help-label')?.textContent).toBe('history')
    expect(helpLine.querySelector('.builtin-help-description')?.textContent).toBe('Show saved runs')
    expect(activateFaqCommandChip).not.toHaveBeenCalled()

    expect(document.querySelector('.line.builtin-faq-q .builtin-row-marker')?.textContent).toBe('Q')
    expect(document.querySelector('.line.builtin-faq-q .builtin-faq-question-text')?.textContent).toBe('How do I export?')
    expect(document.querySelector('.line.builtin-faq-a .builtin-row-marker')?.textContent).toBe('A')
    expect(document.querySelector('.line.builtin-faq-a .builtin-inline-code')?.textContent).toBe('help')
  })

  it('keeps automatic command chips out of command list rows', () => {
    const activateFaqCommandChip = vi.fn()
    const { appendLine } = loadOutputFns({
      appConfig: { max_output_lines: 20 },
      extraGlobals: { activateFaqCommandChip },
    })

    appendLine('  banner  Print the configured banner art', 'builtin-help-row', 'tab-1')
    appendLine('  cat <file>                    Show a session file.', 'builtin-help-row', 'tab-1')
    appendLine('id                                   kind       muted  label', 'builtin-table-header', 'tab-1')
    appendLine('  nmap  Fast network scanner', 'builtin-catalog-item', 'tab-1')

    expect(document.querySelectorAll('.line.builtin-help-row .faq-chip, .line.builtin-catalog-item .faq-chip')).toHaveLength(0)
    expect(document.querySelectorAll('.line.builtin-help-row .builtin-help-label')).toHaveLength(2)
    expect(document.querySelectorAll('.line.builtin-help-row .builtin-help-label')[1].textContent).toBe('cat <file>')
    expect(document.querySelectorAll('.line.builtin-help-row .builtin-help-description')[1].textContent).toBe('Show a session file.')

    const tableHeader = document.querySelector('.line.builtin-table-header')
    expect(tableHeader.querySelector('.builtin-help-label')).toBeNull()
    expect(tableHeader.querySelector('.builtin-help-description')).toBeNull()
    expect(tableHeader.textContent).toContain('id')
    expect(tableHeader.textContent).toContain('kind')
    expect(activateFaqCommandChip).not.toHaveBeenCalled()
  })

  it('renders ANSI-styled structured builtin rows through ansi_to_html', () => {
    class TableAnsiUp {
      constructor() {
        this.use_classes = false
      }

      ansi_to_html(text) {
        return String(text || '')
          .replace(/\x1b\[4m([^\x1b]+)\x1b\[0m/g, '<u>$1</u>')
          .replace(/\x1b\[36m([^\x1b]+)\x1b\[0m/g, '<span class="cyan">$1</span>')
      }
    }
    const { appendLine } = loadOutputFns({
      AnsiUpCtor: TableAnsiUp,
      appConfig: { max_output_lines: 20 },
    })

    appendLine('  \x1b[4mrun\x1b[0m  command', 'builtin-table-header', 'tab-1')
    appendLine('  \x1b[36mrun-abcd\x1b[0m  ping darklab.sh', 'builtin-table-row', 'tab-1')

    const header = document.querySelector('.line.builtin-table-header .line-content')
    const row = document.querySelector('.line.builtin-table-row .line-content')
    expect(header?.textContent).toContain('run  command')
    expect(header?.textContent).not.toContain('[4m')
    expect(header?.querySelector('u')?.textContent).toBe('run')
    expect(row?.textContent).toContain('run-abcd  ping darklab.sh')
    expect(row?.textContent).not.toContain('[36m')
    expect(row?.querySelector('.cyan')?.textContent).toBe('run-abcd')
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

  it('coalesces consecutive progress rows in the live renderer while retaining raw lines', () => {
    const { appendLine, _getTabs } = loadOutputFns({ appConfig: { max_output_lines: 20 } })

    appendLine({ text: '10%', kind: 'info', role: 'progress' }, 'tab-1')
    const firstProgressLine = document.querySelector('.line.progress')
    appendLine({ text: '20%', kind: 'info', role: 'progress' }, 'tab-1')
    appendLine('done', '', 'tab-1')
    appendLine({ text: 'index 1', kind: 'info', role: 'progress' }, 'tab-1')

    const lines = Array.from(document.querySelectorAll('.line'))
    expect(lines).toHaveLength(3)
    expect(lines[0]).toBe(firstProgressLine)
    expect(lines[0].textContent).toContain('20%')
    expect(lines[0].dataset.lineNumber).toBe('1')
    expect(lines[1].textContent).toContain('done')
    expect(lines[2].textContent).toContain('index 1')
    expect(_getTabs()[0].rawLines.map(line => line.text)).toEqual(['10%', '20%', 'done', 'index 1'])
  })

  it('coalesces batched status rows without dropping raw output history', async () => {
    const { appendLines, _getTabs } = loadOutputFns({ appConfig: { max_output_lines: 20 } })

    await appendLines([
      { text: 'phase 1', kind: 'info', role: 'status-line' },
      { text: 'phase 2', kind: 'info', role: 'status-line' },
      { text: 'body', cls: '' },
      { text: 'phase 3', kind: 'info', role: 'status-line' },
      { text: 'phase 4', kind: 'info', role: 'status-line' },
    ], 'tab-1')
    await new Promise((resolve) => setTimeout(resolve, 25))

    const lines = Array.from(document.querySelectorAll('.line'))
    expect(lines).toHaveLength(3)
    expect(lines.map(line => line.textContent.trim())).toEqual(['phase 2', 'body', 'phase 4'])
    expect(lines[0].dataset.lineNumber).toBe('1')
    expect(lines[2].dataset.lineNumber).toBe('3')
    expect(_getTabs()[0].rawLines.map(line => line.text)).toEqual(['phase 1', 'phase 2', 'body', 'phase 3', 'phase 4'])
  })

  it('coalesces restored progress rows while keeping restored raw lines intact', () => {
    const { renderRestoredTabOutput, setTabCommandOutcomeSummary, _getTabs } = loadOutputFns({ appConfig: { max_output_lines: 20 } })

    setTabCommandOutcomeSummary('tab-1', {
      title: 'Command outcome',
      items: [{ label: 'Result', value: 'Finished cleanly' }],
    }, { render: false })

    renderRestoredTabOutput('tab-1', [
      { text: 'loading 1', cls: 'progress', tsC: '12:00:00', tsE: '+0.1s', line_number: 1 },
      { text: 'loading 2', cls: 'progress', tsC: '12:00:01', tsE: '+0.2s', line_number: 2 },
      { text: 'finished', cls: '', tsC: '12:00:02', tsE: '+0.3s', line_number: 3 },
    ])

    const lines = Array.from(document.querySelectorAll('.line'))
    expect(lines).toHaveLength(4)
    expect(lines[0].textContent).toContain('loading 2')
    expect(lines[0].dataset.lineNumber).toBe('1')
    expect(lines[1].textContent).toContain('finished')
    expect(lines[2].classList.contains('command-outcome-summary-title')).toBe(true)
    expect(lines[3].classList.contains('command-outcome-summary-row')).toBe(true)
    expect(lines[3].textContent).toContain('Result: Finished cleanly')
    expect(lines[2].dataset.lineNumber).toBeUndefined()
    expect(lines[3].dataset.lineNumber).toBeUndefined()
    expect(_getTabs()[0].rawLines.map(line => line.text)).toEqual(['loading 1', 'loading 2', 'finished'])
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
    expect(token?.tagName).toBe('SPAN')
    expect(token?.getAttribute('role')).toBe('button')
    expect(token?.getAttribute('tabindex')).toBe('0')
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

  it('keeps highlighted entity text selectable with the rest of the output line', () => {
    const { appendLine } = loadOutputFns()

    appendLine('https://tor-stats.darklab.sh/static/', '', 'tab-1', {
      entities: [{
        type: 'domain',
        value: 'tor-stats.darklab.sh',
        canonical_value: 'tor-stats.darklab.sh',
        start: 8,
        end: 28,
      }],
    })

    const content = document.querySelector('.line-content')
    const selection = window.getSelection()
    const range = document.createRange()
    expect(content?.textContent).toBe('https://tor-stats.darklab.sh/static/')

    range.selectNodeContents(content)
    selection?.removeAllRanges()
    selection?.addRange(range)

    expect(selection?.toString()).toBe('https://tor-stats.darklab.sh/static/')
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
    expect(document.getElementById('ln-btn').textContent).toBe('line numbers')
    expect(document.getElementById('ln-btn').getAttribute('aria-pressed')).toBe('true')

    _setLnMode('off')
    expect(document.body.classList.contains('ln-on')).toBe(false)
    expect(document.getElementById('ln-btn').textContent).toBe('line numbers')
    expect(document.getElementById('ln-btn').getAttribute('aria-pressed')).toBe('false')
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
    const { appendLine, renderCommandOutcomeSummary, _getTabs, _setLnMode, _setTsMode } = loadOutputFns({
      appConfig: { max_output_lines: 20 },
    })

    _setLnMode('on')
    _setTsMode('elapsed')
    _getTabs()[0].command = 'nmap -sV darklab.sh'
    appendLine('443/tcp open https', '', 'tab-1', { signals: ['findings'], command_root: 'nmap' })
    appendLine('22/tcp open ssh OpenSSH 9.9', '', 'tab-1')
    appendLine('Service Info: OS: Linux; CPE: cpe:/o:linux:linux_kernel', '', 'tab-1')
    appendLine('Nmap done: 1 IP address (1 host up) scanned in 3.00 seconds', '', 'tab-1')
    appendLine('Command Findings:', 'builtin-signal-summary-header', 'tab-1')
    appendLine('findings (2)', 'builtin-signal-summary-section', 'tab-1')
    appendLine('- 443/tcp open https', 'builtin-signal-summary-row', 'tab-1')
    expect(renderCommandOutcomeSummary('tab-1')).toBe(true)

    const lines = document.querySelectorAll('.line')
    expect(lines[0]?.dataset.prefix || '').toMatch(/^\+\d+\.\ds$/)
    const syntheticLines = Array.from(document.querySelectorAll([
      '.builtin-signal-summary-header',
      '.builtin-signal-summary-section',
      '.builtin-signal-summary-row',
      '.command-outcome-summary',
    ].join(',')))
    expect(syntheticLines.every(line => (line.dataset.prefix || '') === '')).toBe(true)
    expect(syntheticLines.every(line => line.dataset.lineNumber === undefined)).toBe(true)
    expect(document.querySelector('.command-outcome-summary-row')?.textContent)
      .toContain('Hosts: 1 up')
    expect(document.getElementById('out').textContent)
      .toContain('Open ports: 2 (443/tcp https, 22/tcp ssh OpenSSH 9.9)')
    expect(document.getElementById('out').textContent)
      .toContain('OS / service hints: OS: Linux; CPE: cpe:/o:linux:linux_kernel')
    expect(_getTabs()[0].rawLines.map(line => line.text)).toEqual([
      '443/tcp open https',
      '22/tcp open ssh OpenSSH 9.9',
      'Service Info: OS: Linux; CPE: cpe:/o:linux:linux_kernel',
      'Nmap done: 1 IP address (1 host up) scanned in 3.00 seconds',
      'Command Findings:',
      'findings (2)',
      '- 443/tcp open https',
    ])
    expect(_getTabs()[0]._outputSignalCounts).toEqual({
      findings: 1,
      warnings: 0,
      errors: 0,
      summaries: 0,
    })
    expect(document.getElementById('shell-prompt-wrap')?.dataset.prefix).toBe('+0.0s')

    const disabled = loadOutputFns({
      extraGlobals: {
        getCommandOutcomeSummariesPreference: () => 'off',
      },
    })
    disabled._getTabs()[0].commandOutcomeSummary = {
      title: 'Command outcome',
      items: [{ value: 'Hidden by preference' }],
    }
    expect(disabled.renderCommandOutcomeSummary('tab-1')).toBe(false)
    expect(document.querySelector('.command-outcome-summary')).toBeNull()

    const resetOutputFixture = () => {
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
    }
    const parserCases = [
      {
        command: 'dig example.com',
        lines: [
          ';; ->>HEADER<<- opcode: QUERY, status: NOERROR, id: 1',
          ';; flags: qr rd ra; QUERY: 1, ANSWER: 2, AUTHORITY: 0, ADDITIONAL: 1',
          ';; ANSWER SECTION:',
          'example.com. 300 IN A 93.184.216.34',
          'example.com. 300 IN A 93.184.216.35',
          ';; Query time: 12 msec',
          ';; SERVER: 1.1.1.1#53(1.1.1.1) (UDP)',
        ],
        expected: [
          'Status: NOERROR',
          'Answers: 2',
          'Answer records: example.com A 93.184.216.34, example.com A 93.184.216.35',
          'Record types: A',
          'Query time: 12 msec',
        ],
      },
      {
        command: 'curl -I https://example.com',
        lines: [
          'HTTP/2 301',
          'location: https://www.example.com/',
          'HTTP/2 200',
          'content-type: text/html; charset=UTF-8',
          'content-length: 1256',
        ],
        expected: ['Final status: 200', 'Redirects: 1', 'Final URL: https://www.example.com/', 'Content type: text/html; charset=UTF-8'],
      },
      {
        command: 'nslookup -type=A darklab.sh',
        lines: [
          'Server:\t\t127.0.0.11',
          'Address:\t127.0.0.11#53',
          'Non-authoritative answer:',
          'Name:\tdarklab.sh',
          'Address: 104.21.4.35',
          'Name:\tdarklab.sh',
          'Address: 172.67.131.156',
        ],
        expected: [
          'Answers: 2',
          'A records: darklab.sh A 104.21.4.35, darklab.sh A 172.67.131.156',
          'Record types: A',
          'Resolver: 127.0.0.11 (127.0.0.11#53)',
        ],
      },
      {
        command: 'nslookup -type=MX darklab.sh',
        lines: [
          'Server:\t\t127.0.0.11',
          'Address:\t127.0.0.11#53',
          'Non-authoritative answer:',
          'darklab.sh\tmail exchanger = 10 alt3.aspmx.l.google.com.',
          'darklab.sh\tmail exchanger = 5 alt1.aspmx.l.google.com.',
        ],
        expected: [
          'Answers: 2',
          'MX records: darklab.sh MX 10 alt3.aspmx.l.google.com, darklab.sh MX 5 alt1.aspmx.l.google.com',
          'Record types: MX',
        ],
      },
      {
        command: 'nslookup -type=TXT darklab.sh',
        lines: [
          'Server:\t\t127.0.0.11',
          'Address:\t127.0.0.11#53',
          'Non-authoritative answer:',
          'darklab.sh\ttext = "v=spf1 include:_spf.protonmail.ch mx include:_spf.google.com ~all"',
          'darklab.sh\ttext = "openai-domain-verification=dv-f0XWNwfe5BYCJzmlj3w4a9DE"',
        ],
        expected: [
          'Answers: 2',
          'TXT records: darklab.sh TXT v=spf1 include:_spf.protonmail.ch mx include:_spf.google.com ~all, darklab.sh TXT openai-domain-verification=dv-f0XWNwfe5BYCJzmlj3w4a9DE',
          'Record types: TXT',
        ],
      },
      {
        command: 'openssl s_client -connect example.com:443',
        lines: [
          'subject=CN = example.com',
          'issuer=C = US, O = Example CA',
          'notBefore=Jan  1 00:00:00 2026 GMT',
          'notAfter=Apr  1 00:00:00 2026 GMT',
          'Protocol  : TLSv1.3',
          'Cipher    : TLS_AES_256_GCM_SHA384',
          'Verify return code: 0 (ok)',
        ],
        expected: ['Subject: CN = example.com', 'Issuer: C = US, O = Example CA', 'Protocol: TLSv1.3', 'Cipher: TLS_AES_256_GCM_SHA384'],
      },
    ]
    parserCases.forEach(({ command, lines: outputLines, expected }) => {
      resetOutputFixture()
      const parsed = loadOutputFns({ appConfig: { max_output_lines: 30 } })
      parsed._getTabs()[0].command = command
      outputLines.forEach(line => parsed.appendLine(line, '', 'tab-1'))
      expect(parsed.renderCommandOutcomeSummary('tab-1')).toBe(true)
      const rendered = document.getElementById('out').textContent
      expected.forEach(text => expect(rendered).toContain(text))
      expect(parsed._getTabs()[0].rawLines.map(line => line.text)).toEqual(outputLines)
    })

    resetOutputFixture()
    const noiseFiltered = loadOutputFns({ appConfig: { max_output_lines: 30 } })
    noiseFiltered._getTabs()[0].command = 'nmap -sV darklab.sh'
    noiseFiltered.appendLine('9999/tcp open fake-service', '', 'tab-1', { noise_kind: 'boilerplate' })
    noiseFiltered.appendLine('443/tcp open https nginx', '', 'tab-1')
    expect(noiseFiltered.renderCommandOutcomeSummary('tab-1')).toBe(true)
    const outcomeText = Array.from(document.querySelectorAll('.command-outcome-summary-row'))
      .map(line => line.textContent)
      .join('\n')
    expect(outcomeText).toContain('Open ports: 1 (443/tcp https nginx)')
    expect(outcomeText).not.toContain('fake-service')

    resetOutputFixture()
    const unsupported = loadOutputFns({ appConfig: { max_output_lines: 30 } })
    unsupported._getTabs()[0].command = 'whoami'
    unsupported.appendLine('nona', '', 'tab-1')
    expect(unsupported.renderCommandOutcomeSummary('tab-1')).toBe(false)
    expect(document.querySelector('.command-outcome-summary')).toBeNull()

    resetOutputFixture()
    const failedNmap = loadOutputFns({ appConfig: { max_output_lines: 30 } })
    failedNmap._getTabs()[0].command = [
      'nmap -sC -p 139,445',
      '--script=smb-vuln-cve2009-1231,smb-vuln-cve-2017-7494',
      '192.168.1.5',
    ].join(' ')
    failedNmap._getTabs()[0].commandOutcomeSummary = {
      title: 'Command outcome',
      items: [
        { label: 'Hosts', value: '1 up' },
        { label: 'Open ports', value: '25 (22/tcp ssh OpenSSH 10.0)' },
      ],
    }
    failedNmap.appendLine('Starting Nmap 7.95 ( https://nmap.org ) at 2026-06-03 01:15 UTC', '', 'tab-1')
    failedNmap.appendLine('NSE: failed to initialize the script engine:', 'error', 'tab-1')
    failedNmap.appendLine("'smb-vuln-cve2009-1231' did not match a category, filename, or directory", 'error', 'tab-1')
    failedNmap.appendLine('QUITTING!', 'error', 'tab-1')
    failedNmap.appendLine('[process exited with code 1 in 0.2s]', 'exit-fail', 'tab-1')
    expect(failedNmap.renderCommandOutcomeSummary('tab-1')).toBe(false)
    expect(document.querySelector('.command-outcome-summary')).toBeNull()
    expect(document.getElementById('out').textContent).not.toContain('Open ports: 25')
    expect(failedNmap._getTabs()[0].commandOutcomeSummary).toBeNull()

    resetOutputFixture()
    const bracketFailedNmap = loadOutputFns({ appConfig: { max_output_lines: 30 } })
    bracketFailedNmap._getTabs()[0].command = 'nmap -sT -p 10-10000 [192.168.1.5]'
    bracketFailedNmap.appendLine('22/tcp open ssh', '', 'tab-1')
    bracketFailedNmap.appendLine('80/tcp open http', '', 'tab-1')
    bracketFailedNmap.appendLine('Nmap done: 1 IP address (1 host up) scanned in 0.28 seconds', '', 'tab-1')
    bracketFailedNmap._getTabs()[0].currentRunStartIndex = bracketFailedNmap._getTabs()[0].rawLines.length
    bracketFailedNmap.appendLine('Failed to resolve "[192.168.1.5]".', 'error', 'tab-1')
    bracketFailedNmap.appendLine('WARNING: No targets were specified, so 0 hosts scanned.', 'warning', 'tab-1')
    bracketFailedNmap.appendLine('Nmap done: 0 IP addresses (0 hosts up) scanned in 0.03 seconds', '', 'tab-1')
    expect(bracketFailedNmap.renderCommandOutcomeSummary('tab-1')).toBe(true)
    const bracketOutcomeText = Array.from(document.querySelectorAll('.command-outcome-summary-row'))
      .map(line => line.textContent)
      .join('\n')
    expect(bracketOutcomeText).toContain('Hosts: 0 up')
    expect(bracketOutcomeText).not.toContain('Open ports:')
    expect(bracketOutcomeText).not.toContain('22/tcp')

    resetOutputFixture()
    const explicitOutcome = loadOutputFns({ appConfig: { max_output_lines: 30 } })
    explicitOutcome._getTabs()[0].command = 'nmap --script bad 192.168.1.5'
    explicitOutcome.appendLine('NSE: failed to initialize the script engine:', 'error', 'tab-1')
    explicitOutcome.setTabCommandOutcomeSummary('tab-1', {
      title: 'Command outcome',
      items: [{ label: 'Status', value: 'saved summary' }],
    })
    expect(document.getElementById('out').textContent).toContain('Status: saved summary')
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

  it('keeps the elapsed timestamp gutter stable after a full prefix resync', () => {
    const { appendLine, syncOutputPrefixes, _setTsMode } = loadOutputFns({
      extraGlobals: {
        tabs: [{ id: 'tab-1', st: 'idle', rawLines: [], runStart: 0 }],
      },
    })

    _setTsMode('elapsed')
    appendLine('', 'prompt-echo', 'tab-1')
    expect(document.getElementById('out').style.getPropertyValue('--output-prefix-width')).toBe('8ch')

    syncOutputPrefixes()

    expect(document.querySelector('.line.prompt-echo')?.dataset.prefix).toBe('+0.0s')
    expect(document.getElementById('shell-prompt-wrap')?.dataset.prefix).toBe('+0.0s')
    expect(document.getElementById('out').style.getPropertyValue('--output-prefix-width')).toBe('8ch')
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
    expect(renderedText).toContain('live output summary: 1 line was not rendered live in this tab')
    expect(renderedText).toContain('full transcript output is preserved in saved output, permalinks, and exports')
    expect(renderedText).not.toContain('line 2')
  })

  it('adds a final live summary when progress rows were collapsed', () => {
    const { appendLine, appendHighVolumeOutputFinalSummary, recordLiveOutputCoalescedLines } = loadOutputFns({
      appConfig: { max_output_lines: 20 },
    })

    appendLine('line 1', '', 'tab-1')
    recordLiveOutputCoalescedLines('tab-1', 12)

    expect(appendHighVolumeOutputFinalSummary('tab-1')).toBe(true)

    const renderedText = Array.from(document.querySelectorAll('.line')).map(line => line.textContent).join('\n')
    expect(renderedText).toContain('progress/status updates were collapsed in this tab')
    expect(renderedText).toContain('live line numbers may differ from the saved transcript')
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
