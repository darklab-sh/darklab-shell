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
  const w = {}
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
        return {
          width: 1,
          height: 1,
          getContext() {
            return {
              fillStyle: '',
              fillRect() {},
              getImageData() { return { data: [100, 150, 200, 255] } },
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
    }
    setFillColor() {} rect() {} setFont() {} setFontSize() {} setTextColor() {}
    setCharSpace() {} text() {} setDrawColor() {} setLineWidth() {} line() {}
    getTextWidth() { return 50 }
    addPage() {}
    splitTextToSize(t) { return [t] }
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

  it('returns a jsPDF doc instance', () => {
    const { buildTerminalExportPdf } = buildUtils()
    const MockJsPDF = makeMockJsPDF()
    const doc = buildTerminalExportPdf({
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

  it('returns a doc when rawLines is empty', () => {
    const { buildTerminalExportPdf } = buildUtils()
    const MockJsPDF = makeMockJsPDF()
    const doc = buildTerminalExportPdf({
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

  it('renders exit-ok / exit-fail / denied / notice / prompt-echo line classes without throwing', () => {
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
    expect(() => buildTerminalExportPdf({
      jsPDF: MockJsPDF,
      appName: 'test',
      metaLine: 'run  ·  now',
      runMeta: null,
      rawLines,
      getPrefix: () => '',
      ansiToHtml: (t) => `<span style="color:rgb(1,2,3)">${t}</span>`,
    })).not.toThrow()
  })

  it('renders runMeta badges without throwing', () => {
    const { buildTerminalExportPdf } = buildUtils()
    const MockJsPDF = makeMockJsPDF()
    expect(() => buildTerminalExportPdf({
      jsPDF: MockJsPDF,
      appName: 'test',
      metaLine: 'run  ·  now',
      runMeta: { exitCode: 0, duration: '1.2s', lines: '10 lines', version: '1.5' },
      rawLines: [{ text: 'hello', cls: '' }],
      getPrefix: () => '',
      ansiToHtml: (t) => t,
    })).not.toThrow()
  })

  it('renders prefix gutter when getPrefix returns non-empty strings', () => {
    const { buildTerminalExportPdf } = buildUtils()
    const MockJsPDF = makeMockJsPDF()
    expect(() => buildTerminalExportPdf({
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
    })).not.toThrow()
  })
})
