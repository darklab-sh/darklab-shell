import { fromDomScripts } from './helpers/extract.js'

function loadOutputFns({ appConfig = {} } = {}) {
  class FakeAnsiUp {
    constructor() {
      this.use_classes = false
    }

    ansi_to_html(s) {
      return '<em>' + s + '</em>'
    }
  }

  return fromDomScripts(
    ['app/static/js/output.js'],
    {
      document,
      AnsiUp: FakeAnsiUp,
      activeTabId: 'tab-1',
      tabs: [{ id: 'tab-1', rawLines: [], runStart: 1000 }],
      APP_CONFIG: { max_output_lines: 2, ...appConfig },
      getOutput: () => document.getElementById('out'),
      shellPromptWrap: document.getElementById('shell-prompt-wrap'),
    },
    `{
    appendLine,
    _setTsMode,
    _setLnMode,
    _getTabs: () => tabs,
  }`,
    'setTabs(tabs); setActiveTabId(activeTabId);',
  )
}

describe('appendLine', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div id="out">
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

  it('falls back to plain-text rendering when AnsiUp is unavailable', () => {
    const { appendLine } = fromDomScripts(
      ['app/static/js/utils.js', 'app/static/js/output.js'],
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

  it('adds timestamp dataset fields', () => {
    const { appendLine } = loadOutputFns()

    appendLine('timed line', '', 'tab-1')

    const line = document.querySelector('.line')
    expect(line.dataset.tsC).toMatch(/^\d{2}:\d{2}:\d{2}$/)
    expect(line.dataset.tsE).toMatch(/^\+\d+\.\d+s$/)
  })

  it('toggles the line-number body class and button labels', () => {
    document.body.innerHTML = `
      <button id="ln-btn"></button>
      <button id="ts-btn"></button>
      <div id="mobile-menu"><button data-action="ln"></button></div>
      <div id="out"></div>
    `
    const { _setLnMode } = loadOutputFns()

    _setLnMode('on')
    expect(document.body.classList.contains('ln-on')).toBe(true)
    expect(document.getElementById('ln-btn').textContent).toBe('line numbers: on')
    expect(document.querySelector('#mobile-menu [data-action="ln"]').textContent).toBe(
      'line numbers: on',
    )

    _setLnMode('off')
    expect(document.body.classList.contains('ln-on')).toBe(false)
    expect(document.getElementById('ln-btn').textContent).toBe('line numbers: off')
  })

  it('numbers the prompt line after the current output rows', () => {
    const { appendLine, _setLnMode } = loadOutputFns()

    _setLnMode('on')
    appendLine('hello', '', 'tab-1')

    expect(document.querySelector('.line')?.dataset.prefix).toBe('1')
    expect(document.getElementById('shell-prompt-wrap')?.dataset.prefix).toBe('2')
  })

  it('does not assign prefixes to welcome animation lines', () => {
    const { appendLine, _setLnMode } = loadOutputFns()

    _setLnMode('on')
    appendLine('loading /', 'welcome-status-line', 'tab-1')
    appendLine('hello', '', 'tab-1')

    expect(document.querySelector('.line.welcome-status-line')?.dataset.prefix).toBe('')
    expect(document.querySelector('.line:not(.welcome-status-line)')?.dataset.prefix).toBe('1')
    expect(document.getElementById('shell-prompt-wrap')?.dataset.prefix).toBe('2')
  })

  it('combines line numbers and timestamps into a compact shared prefix', () => {
    const { appendLine, _setLnMode, _setTsMode } = loadOutputFns()

    _setLnMode('on')
    _setTsMode('elapsed')

    appendLine('timed line', '', 'tab-1')

    expect(document.querySelector('.line')?.dataset.prefix).toMatch(/^1\s+\+\d+\.\ds$/)
    expect(document.getElementById('shell-prompt-wrap')?.dataset.prefix).toBe('2')
  })

  it('does nothing when there is no output container for the target tab', () => {
    document.body.innerHTML = ''
    const { appendLine, _getTabs } = loadOutputFns()

    appendLine('orphan line', '', 'missing-tab')

    expect(document.querySelector('.line')).toBeNull()
    expect(_getTabs()[0].rawLines).toHaveLength(0)
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
})
