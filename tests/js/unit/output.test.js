import { fromDomScripts } from './helpers/extract.js'

function loadOutputFns() {
  class FakeAnsiUp {
    constructor() {
      this.use_classes = false
    }

    ansi_to_html(s) {
      return '<em>' + s + '</em>'
    }
  }

  return fromDomScripts([
    'app/static/js/output.js',
  ], {
    document,
    AnsiUp: FakeAnsiUp,
    activeTabId: 'tab-1',
    tabs: [{ id: 'tab-1', rawLines: [], runStart: 1000 }],
    APP_CONFIG: { max_output_lines: 2 },
    getOutput: () => document.getElementById('out'),
  }, `{
    appendLine,
    _getTabs: () => tabs,
  }`)
}

describe('appendLine', () => {
  beforeEach(() => {
    document.body.innerHTML = `<div id="out"></div>`
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

  it('does nothing when there is no output container for the target tab', () => {
    document.body.innerHTML = ''
    const { appendLine, _getTabs } = loadOutputFns()

    appendLine('orphan line', '', 'missing-tab')

    expect(document.querySelector('.line')).toBeNull()
    expect(_getTabs()[0].rawLines).toHaveLength(0)
  })
})
