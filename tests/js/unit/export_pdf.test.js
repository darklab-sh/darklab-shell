import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'
import { vi } from 'vitest'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../../../')

// Load export_pdf.js into an isolated context and return window.ExportPdfUtils.
// Callers may inject a custom document to avoid the canvas / getComputedStyle
// requirements; omit it to use the real jsdom document (canvas unsupported).
function loadExportPdfUtils(overrides = {}) {
  const src = readFileSync(resolve(REPO_ROOT, 'app/static/js/export_pdf.js'), 'utf8')
  const w = { ...(overrides.windowProps ?? {}) }
  const globals = {
    window: w,
    document: overrides.document ?? document,
    getComputedStyle: overrides.getComputedStyle ?? getComputedStyle,
    Node: overrides.Node ?? Node,
    ...overrides.extra,
  }
  new Function(...Object.keys(globals), src)(...Object.values(globals))
  return w.ExportPdfUtils
}

// A document mock that provides working canvas and div primitives so
// parseCssColor / renderAnsiLine can be exercised without native canvas.
function makeDocumentMock() {
  return {
    createElement(tag) {
      if (tag === 'canvas') {
        let fillStyle = 'rgb(0, 0, 0)'
        return {
          width: 1,
          height: 1,
          getContext() {
            return {
              get fillStyle() { return fillStyle },
              set fillStyle(value) { fillStyle = value },
              fillRect() {},
              getImageData() {
                const match = String(fillStyle).match(/(\d+)\D+(\d+)\D+(\d+)/)
                if (!match) return { data: [100, 150, 200, 255] }
                return { data: [Number(match[1]), Number(match[2]), Number(match[3]), 255] }
              },
            }
          },
        }
      }
      if (tag === 'div') {
        const el = { innerHTML: '', childNodes: [] }
        Object.defineProperty(el, 'innerHTML', {
          set(html) {
            // Produce a minimal childNodes array from plain-text HTML fragments.
            // Handles: bare text, <span style="color:rgb(1,2,3)">text</span>.
            const nodes = []
            const re = /(<span[^>]*>)(.*?)<\/span>|([^<]+)/g
            let m
            while ((m = re.exec(html)) !== null) {
              if (m[3] !== undefined) {
                // plain text node
                nodes.push({ nodeType: 3, textContent: m[3], style: {} })
              } else {
                // element node — extract color from style attribute if present
                const colorMatch = m[1].match(/color\s*:\s*([^;"']+)/)
                nodes.push({
                  nodeType: 1,
                  textContent: m[2],
                  style: { color: colorMatch ? colorMatch[1].trim() : '' },
                })
              }
            }
            el.childNodes = nodes
          },
          get() { return '' },
          configurable: true,
        })
        return el
      }
      return {}
    },
    documentElement: {},
  }
}

function makeMockGetComputedStyle() {
  return () => ({ getPropertyValue: () => 'rgb(80, 80, 80)' })
}

// Minimal jsPDF mock — records save() calls so tests can assert on them.
function makeMockJsPDF() {
  return class MockJsPDF {
    constructor() {
      this.internal = { pageSize: { getWidth: () => 595, getHeight: () => 842 } }
      this.savedAs = null
      this.textCalls = []
      this.setFontCalls = []
      this.addFileToVFSCalls = []
      this.addFontCalls = []
      this.drawColorCalls = []
    }
    setFillColor() {} rect() {}
    setFont(family, style) { this.setFontCalls.push({ family, style }) }
    setFontSize() {} setTextColor() {}
    setCharSpace() {}
    setDrawColor(...args) { this.drawColorCalls.push(args) }
    setLineWidth() {} line() {}
    getTextWidth() { return 50 }
    addPage() {}
    addFileToVFS(filename) { this.addFileToVFSCalls.push(filename) }
    addFont(filename, family, style) { this.addFontCalls.push({ filename, family, style }) }
    splitTextToSize(t) { return [t] }
    text(text, x, y) { this.textCalls.push({ text, x, y }) }
    save(name) { this.savedAs = name }
  }
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ExportPdfUtils module', () => {
  it('exposes ExportPdfUtils on window with the expected API', () => {
    // Use real jsdom document — only testing the module shape, not canvas calls.
    const utils = loadExportPdfUtils()
    expect(typeof utils).toBe('object')
    expect(typeof utils.buildTerminalExportPdf).toBe('function')
    expect(typeof utils.parseCssColor).toBe('function')
    expect(typeof utils.themeColors).toBe('function')
  })
})

describe('buildTerminalExportPdf', () => {
  function buildUtils() {
    return loadExportPdfUtils({
      document: makeDocumentMock(),
      getComputedStyle: makeMockGetComputedStyle(),
      Node: { ELEMENT_NODE: 1 },
    })
  }

  it('returns a jsPDF doc instance', async () => {
    const { buildTerminalExportPdf } = buildUtils()
    const MockJsPDF = makeMockJsPDF()
    const doc = await buildTerminalExportPdf({
      jsPDF: MockJsPDF,
      appName: 'darklab shell',
      metaLine: 'my run  ·  01/01/2025',
      runMeta: null,
      rawLines: [{ text: 'hello', cls: '' }],
      getPrefix: () => '',
      ansiToHtml: (t) => t,
    })
    expect(doc).toBeInstanceOf(MockJsPDF)
  })

  it('returns a doc when rawLines is empty', async () => {
    const { buildTerminalExportPdf } = buildUtils()
    const MockJsPDF = makeMockJsPDF()
    const doc = await buildTerminalExportPdf({
      jsPDF: MockJsPDF,
      appName: 'darklab shell',
      metaLine: '',
      runMeta: null,
      rawLines: [],
      getPrefix: () => '',
      ansiToHtml: (t) => t,
    })
    expect(doc).toBeInstanceOf(MockJsPDF)
  })

  it('renders exit-ok / exit-fail / denied / notice / prompt-echo line classes without throwing', async () => {
    const { buildTerminalExportPdf } = buildUtils()
    const MockJsPDF = makeMockJsPDF()
    const rawLines = [
      { text: 'success', cls: 'exit-ok' },
      { text: 'failure', cls: 'exit-fail' },
      { text: 'blocked', cls: 'denied' },
      { text: 'info',    cls: 'notice' },
      { text: '$ ls -la', cls: 'prompt-echo' },
      { text: 'plain',   cls: '' },
    ]
    await expect(buildTerminalExportPdf({
      jsPDF: MockJsPDF,
      appName: 'test',
      metaLine: 'run  ·  now',
      runMeta: null,
      rawLines,
      getPrefix: () => '',
      ansiToHtml: (t) => `<span style="color:rgb(1,2,3)">${t}</span>`,
    })).resolves.toBeInstanceOf(MockJsPDF)
  })

  it('renders runMeta badges without throwing', async () => {
    const { buildTerminalExportPdf } = buildUtils()
    const MockJsPDF = makeMockJsPDF()
    await expect(buildTerminalExportPdf({
      jsPDF: MockJsPDF,
      appName: 'test',
      metaLine: 'run  ·  now',
      runMeta: { exitCode: 0, duration: '1.2s', lines: '10 lines', version: '1.5' },
      rawLines: [{ text: 'hello', cls: '' }],
      getPrefix: () => '',
      ansiToHtml: (t) => t,
    })).resolves.toBeInstanceOf(MockJsPDF)
  })

  it('renders prefix gutter when getPrefix returns non-empty strings', async () => {
    const { buildTerminalExportPdf } = buildUtils()
    const MockJsPDF = makeMockJsPDF()
    await expect(buildTerminalExportPdf({
      jsPDF: MockJsPDF,
      appName: 'test',
      metaLine: '',
      runMeta: null,
      rawLines: [
        { text: 'line one', cls: '' },
        { text: 'line two', cls: '' },
      ],
      getPrefix: (_, i) => String(i + 1),
      ansiToHtml: (t) => t,
    })).resolves.toBeInstanceOf(MockJsPDF)
  })

  it('uses ExportHtmlUtils theme vars before falling back to computed CSS', () => {
    const { themeColors } = loadExportPdfUtils({
      document: makeDocumentMock(),
      getComputedStyle: () => ({ getPropertyValue: () => 'rgb(1, 2, 3)' }),
      Node: { ELEMENT_NODE: 1 },
      windowProps: {
        ExportHtmlUtils: {
          getThemeExportVars: () => ({
            '--bg': 'rgb(10, 11, 12)',
            '--surface': 'rgb(20, 21, 22)',
            '--border': 'rgb(30, 31, 32)',
            '--text': 'rgb(40, 41, 42)',
            '--muted': 'rgb(50, 51, 52)',
            '--green': 'rgb(60, 61, 62)',
            '--red': 'rgb(70, 71, 72)',
            '--amber': 'rgb(80, 81, 82)',
            '--blue': 'rgb(90, 91, 92)',
          }),
        },
      },
    })

    const colors = themeColors()

    expect(colors.bg).toEqual([10, 11, 12])
    expect(colors.text).toEqual([40, 41, 42])
    expect(colors.greenDim).toEqual([1, 2, 3])
  })

  it('uses the shared header model ordering for app name, meta line, and run meta', async () => {
    const { buildTerminalExportPdf } = loadExportPdfUtils({
      document: makeDocumentMock(),
      getComputedStyle: makeMockGetComputedStyle(),
      Node: { ELEMENT_NODE: 1 },
      windowProps: {
        ExportHtmlUtils: {
          getThemeExportVars: () => ({}),
          buildExportHeaderModel: () => ({
            appName: 'shared app',
            metaLine: 'shared meta',
            runMetaItems: [
              { kind: 'badge', tone: 'fail', text: 'exit 9' },
              { kind: 'item', text: '5 lines' },
              { kind: 'item', text: 'v1.5' },
            ],
          }),
        },
      },
    })
    const MockJsPDF = makeMockJsPDF()
    const doc = await buildTerminalExportPdf({
      jsPDF: MockJsPDF,
      appName: 'ignored',
      metaLine: 'ignored',
      runMeta: { exitCode: 0, lines: '1 line', version: '1.0' },
      rawLines: [{ text: 'hello', cls: '' }],
      getPrefix: () => '',
      ansiToHtml: (t) => t,
    })

    expect(doc.textCalls.map((call) => call.text)).toContain('shared app')
    expect(doc.textCalls.map((call) => call.text)).toContain('shared meta')
    expect(doc.textCalls.map((call) => call.text)).toContain('exit 9')
    expect(doc.textCalls.map((call) => call.text)).toContain('5 LINES')
    expect(doc.textCalls.map((call) => call.text)).toContain('V1.5')
  })

  it('embeds JetBrains Mono into the PDF when font VFS hooks are available', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      arrayBuffer: () => Promise.resolve(new Uint8Array([1, 2, 3]).buffer),
    })

    try {
      const { buildTerminalExportPdf } = buildUtils()
      const MockJsPDF = makeMockJsPDF()
      const doc = await buildTerminalExportPdf({
        jsPDF: MockJsPDF,
        appName: 'darklab shell',
        metaLine: 'scan · now',
        runMeta: null,
        rawLines: [{ text: 'hello', cls: '' }],
        getPrefix: () => '',
        ansiToHtml: (t) => t,
      })

      expect(doc.addFileToVFSCalls).toContain('JetBrainsMono-400.ttf')
      expect(doc.addFileToVFSCalls).toContain('JetBrainsMono-700.ttf')
      expect(doc.addFontCalls).toContainEqual({
        filename: 'JetBrainsMono-400.ttf',
        family: 'JetBrains Mono',
        style: 'normal',
      })
      expect(doc.setFontCalls).toContainEqual({ family: 'JetBrains Mono', style: 'normal' })
    } finally {
      fetchMock.mockRestore()
    }
  })

  it('uses the dim green border color for success badges', async () => {
    const { buildTerminalExportPdf } = loadExportPdfUtils({
      document: makeDocumentMock(),
      getComputedStyle: () => ({ getPropertyValue: () => 'rgb(1, 2, 3)' }),
      Node: { ELEMENT_NODE: 1 },
      windowProps: {
        ExportHtmlUtils: {
          getThemeExportVars: () => ({
            '--bg': 'rgb(10, 10, 10)',
            '--surface': 'rgb(20, 20, 20)',
            '--border': 'rgb(30, 30, 30)',
            '--text': 'rgb(40, 40, 40)',
            '--muted': 'rgb(50, 50, 50)',
            '--green': 'rgb(80, 80, 80)',
            '--green-dim': 'rgb(40, 40, 40)',
            '--red': 'rgb(70, 70, 70)',
            '--amber': 'rgb(80, 80, 80)',
            '--blue': 'rgb(90, 90, 90)',
          }),
          buildExportHeaderModel: () => ({
            appName: 'darklab shell',
            metaLine: 'scan · now',
            runMetaItems: [
              { kind: 'badge', tone: 'ok', text: 'exit 0' },
              { kind: 'item', text: '5 lines' },
            ],
          }),
        },
      },
    })
    const MockJsPDF = makeMockJsPDF()
    const doc = await buildTerminalExportPdf({
      jsPDF: MockJsPDF,
      appName: 'darklab shell',
      metaLine: 'scan · now',
      runMeta: { exitCode: 0, duration: '1s', lines: '5 lines', version: '1.5' },
      rawLines: [{ text: 'hello', cls: '' }],
      getPrefix: () => '',
      ansiToHtml: (t) => t,
    })

    expect(doc.drawColorCalls).toContainEqual([40, 40, 40])
  })

  it('skips fully empty raw lines without prefixes so PDF output matches browser rendering', async () => {
    const { buildTerminalExportPdf } = buildUtils()
    const MockJsPDF = makeMockJsPDF()
    const doc = await buildTerminalExportPdf({
      jsPDF: MockJsPDF,
      appName: 'darklab shell',
      metaLine: 'scan · now',
      runMeta: null,
      rawLines: [
        { text: 'anon@darklab.sh:~$ ping -i 0.5 -c 20 darklab.sh', cls: 'prompt-echo' },
        { text: '', cls: 'prompt-echo' },
        { text: 'PING darklab.sh (104.21.4.35) 56(84) bytes of data.', cls: '' },
        { text: '', cls: '' },
        { text: '--- darklab.sh ping statistics ---', cls: '' },
      ],
      getPrefix: () => '',
      ansiToHtml: (t) => t,
    })

    const renderedText = doc.textCalls.map((call) => call.text)
    const renderedJoined = renderedText.join('')
    expect(renderedJoined).toContain('anon@darklab.sh:~$ ping -i 0.5 -c 20 darklab.sh')
    expect(renderedJoined).toContain('PING darklab.sh (104.21.4.35) 56(84) bytes of data.')
    expect(renderedJoined).toContain('--- darklab.sh ping statistics ---')
    expect(renderedText).not.toContain('')
  })
})
