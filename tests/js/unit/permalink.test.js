import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'
import { vi, beforeEach, afterEach } from 'vitest'

// Silence jsdom's "Not implemented: navigation to another Document" warning
// that fires when a.click() is called on a download anchor. The actual download
// behaviour is tested via URL.createObjectURL mock calls — navigation is irrelevant.
beforeEach(() => {
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
})
afterEach(() => {
  vi.restoreAllMocks()
})

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../../../')
const PERMALINK_SRC = readFileSync(resolve(REPO_ROOT, 'app/static/js/permalink.js'), 'utf8')

// ── Helpers ────────────────────────────────────────────────────────────────────

function makeAnsiUpMock() {
  const instance = { ansi_to_html: vi.fn((t) => t), use_classes: false }
  // Regular function (not arrow) so it can be called with `new`.
  // When a constructor returns an object, that object is what `new` yields.
  function MockAnsiUp() { return instance }
  return { Ctor: MockAnsiUp, instance }
}

function makeExportHtmlUtilsMock() {
  return {
    renderExportPromptEcho: vi.fn(
      (t) => '<span class="prompt-prefix">$</span>' + (t || ''),
    ),
    exportTimestamp: vi.fn(() => '2025-01-15T10-30-00'),
    buildExportLinesHtml: vi.fn(() => ({ linesHtml: '<span>line</span>', prefixWidth: 0 })),
    buildTerminalExportHtml: vi.fn(() => '<html>export</html>'),
    fetchTerminalExportCss: vi.fn(() => Promise.resolve('.export{}')),
  }
}

function makeExportPdfUtilsMock() {
  const doc = { save: vi.fn() }
  return {
    buildTerminalExportPdf: vi.fn(() => doc),
    _doc: doc,
  }
}

function makeUrlMock() {
  return {
    createObjectURL: vi.fn(() => 'blob:mock'),
    revokeObjectURL: vi.fn(),
  }
}

/**
 * Insert the required DOM scaffold and load permalink.js as an IIFE.
 * Returns handles to the DOM elements and all injected mocks.
 */
function loadPermalink({
  lines = [],
  hasTimestampMetadata = false,
  appName = 'testapp',
  label = 'test label',
  created = '2025-01-15T10:30:00Z',
  fontFacesCss = '',
  permalinkMeta = null,
  cookie = '',
  jspdf = null,
} = {}) {
  // Build DOM scaffold
  const container = document.createElement('div')
  container.id = 'permalink-test-root'
  container.innerHTML = `
    <div id="output"></div>
    <button id="toggle-ln">line numbers: off</button>
    <button id="toggle-ts">timestamps: off</button>
    <div id="perm-save-wrap">
      <button id="perm-save-btn">save</button>
    </div>
    <div id="permalink-toast"></div>
  `
  document.body.appendChild(container)

  // Seed PermData
  window.PermData = {
    lines,
    hasTimestampMetadata,
    appName,
    label,
    created,
    fontFacesCss,
    permalinkMeta,
  }

  // Seed cookie (jsdom cookie jar — set then read back via getCookie)
  document.cookie = `pref_line_numbers=${cookie.includes('pref_line_numbers=on') ? 'on' : 'off'}`
  if (cookie.includes('pref_timestamps=')) {
    const m = cookie.match(/pref_timestamps=([^;]+)/)
    if (m) document.cookie = `pref_timestamps=${m[1]}`
  }

  const ansiUp = makeAnsiUpMock()
  const ExportHtmlUtils = makeExportHtmlUtilsMock()
  const ExportPdfUtils = makeExportPdfUtilsMock()
  const copyTextToClipboard = vi.fn(() => Promise.resolve())
  const showToast = vi.fn()
  const URL = makeUrlMock()
  const win = Object.assign({}, window, {
    PermData: window.PermData,
    jspdf: jspdf ?? { jsPDF: vi.fn(() => ({ save: vi.fn() })) },
  })

  new Function(
    'window',
    'document',
    'AnsiUp',
    'ExportHtmlUtils',
    'ExportPdfUtils',
    'copyTextToClipboard',
    'showToast',
    'URL',
    PERMALINK_SRC,
  )(win, document, ansiUp.Ctor, ExportHtmlUtils, ExportPdfUtils, copyTextToClipboard, showToast, URL)

  return {
    el: {
      output: document.getElementById('output'),
      toggleLn: document.getElementById('toggle-ln'),
      toggleTs: document.getElementById('toggle-ts'),
      saveWrap: document.getElementById('perm-save-wrap'),
      saveBtn: document.getElementById('perm-save-btn'),
      toast: document.getElementById('permalink-toast'),
      container,
    },
    mocks: {
      ansiUpInstance: ansiUp.instance,
      AnsiUp: ansiUp.Ctor,
      ExportHtmlUtils,
      ExportPdfUtils,
      copyTextToClipboard,
      showToast,
      URL,
    },
  }
}

afterEach(() => {
  // Remove any scaffold inserted by loadPermalink
  const el = document.getElementById('permalink-test-root')
  if (el) el.remove()
  // Clear PermData
  delete window.PermData
  // Clear cookies set during test
  for (const pair of document.cookie.split(';')) {
    const key = pair.trim().split('=')[0]
    if (key) document.cookie = `${key}=; expires=Thu, 01 Jan 1970 00:00:00 GMT`
  }
})

// ── renderOutput ───────────────────────────────────────────────────────────────

describe('renderOutput — output element structure', () => {
  it('clears and re-populates #output on load', () => {
    const lines = [{ text: 'hello world', cls: '' }]
    const { el } = loadPermalink({ lines })
    expect(el.output.children.length).toBe(1)
  })

  it('produces no child nodes for an empty lines array', () => {
    const { el } = loadPermalink({ lines: [] })
    expect(el.output.children.length).toBe(0)
  })

  it('creates a .line span for each entry', () => {
    const lines = [
      { text: 'line one', cls: '' },
      { text: 'line two', cls: '' },
      { text: 'line three', cls: '' },
    ]
    const { el } = loadPermalink({ lines })
    expect(el.output.children.length).toBe(3)
    for (const child of el.output.children) {
      expect(child.tagName).toBe('SPAN')
      expect(child.className).toContain('line')
    }
  })

  it('adds the cls class alongside "line"', () => {
    const lines = [{ text: 'ok', cls: 'exit-ok' }]
    const { el } = loadPermalink({ lines })
    expect(el.output.children[0].className).toBe('line exit-ok')
  })

  it('calls ansi_to_html for normal output lines', () => {
    const lines = [{ text: '\x1b[32mgreen\x1b[0m', cls: '' }]
    const { mocks } = loadPermalink({ lines })
    expect(mocks.ansiUpInstance.ansi_to_html).toHaveBeenCalledWith('\x1b[32mgreen\x1b[0m')
  })

  it('uses ExportHtmlUtils.renderExportPromptEcho for prompt-echo lines', () => {
    const lines = [{ text: '$ nmap target', cls: 'prompt-echo' }]
    const { mocks } = loadPermalink({ lines })
    expect(mocks.ExportHtmlUtils.renderExportPromptEcho).toHaveBeenCalledWith('$ nmap target')
    expect(mocks.ansiUpInstance.ansi_to_html).not.toHaveBeenCalled()
  })

  it('uses textContent (not ansi_to_html) for plain classes', () => {
    for (const cls of ['exit-ok', 'exit-fail', 'denied', 'notice']) {
      afterEach(() => {
        document.getElementById('permalink-test-root')?.remove()
        delete window.PermData
      })
      const lines = [{ text: 'plain', cls }]
      const { el, mocks } = loadPermalink({ lines })
      const contentEl = el.output.querySelector('.perm-content')
      expect(contentEl.textContent).toBe('plain')
      expect(mocks.ansiUpInstance.ansi_to_html).not.toHaveBeenCalled()
      el.container.remove()
      delete window.PermData
    }
  })

  it('sets #toggle-ln text to "line numbers: off" initially', () => {
    const { el } = loadPermalink()
    expect(el.toggleLn.textContent).toBe('line numbers: off')
  })

  it('sets #toggle-ts text to "timestamps: unavailable" when no metadata', () => {
    const { el } = loadPermalink({ hasTimestampMetadata: false })
    expect(el.toggleTs.textContent).toBe('timestamps: unavailable')
  })

  it('sets #toggle-ts text to "timestamps: off" when metadata present', () => {
    const { el } = loadPermalink({ hasTimestampMetadata: true })
    expect(el.toggleTs.textContent).toBe('timestamps: off')
  })
})

// ── prefix rendering ───────────────────────────────────────────────────────────

describe('renderOutput — prefix column', () => {
  it('does not render a perm-prefix span when line numbers and timestamps are off', () => {
    const lines = [{ text: 'hello', cls: '' }]
    const { el } = loadPermalink({ lines })
    expect(el.output.querySelector('.perm-prefix')).toBeNull()
  })

  it('renders a perm-prefix span with line number when line numbers cookie is on', () => {
    const lines = [
      { text: 'first', cls: '' },
      { text: 'second', cls: '' },
    ]
    const { el } = loadPermalink({ lines, cookie: 'pref_line_numbers=on' })
    const prefixes = el.output.querySelectorAll('.perm-prefix')
    expect(prefixes.length).toBe(2)
    expect(prefixes[0].textContent).toBe('1')
    expect(prefixes[1].textContent).toBe('2')
  })

  it('renders elapsed timestamp in perm-prefix when tsMode is elapsed', () => {
    const lines = [{ text: 'out', cls: '', tsE: '0.5s', tsC: '10:00:01' }]
    const { el } = loadPermalink({
      lines,
      hasTimestampMetadata: true,
      cookie: 'pref_timestamps=elapsed',
    })
    const prefix = el.output.querySelector('.perm-prefix')
    expect(prefix).not.toBeNull()
    expect(prefix.textContent).toBe('0.5s')
  })

  it('renders clock timestamp in perm-prefix when tsMode is clock', () => {
    const lines = [{ text: 'out', cls: '', tsE: '0.5s', tsC: '10:00:01' }]
    const { el } = loadPermalink({
      lines,
      hasTimestampMetadata: true,
      cookie: 'pref_timestamps=clock',
    })
    const prefix = el.output.querySelector('.perm-prefix')
    expect(prefix).not.toBeNull()
    expect(prefix.textContent).toBe('10:00:01')
  })

  it('ignores timestamp cookie when hasTimestampMetadata is false', () => {
    const lines = [{ text: 'out', cls: '', tsE: '0.5s', tsC: '10:00:01' }]
    const { el } = loadPermalink({
      lines,
      hasTimestampMetadata: false,
      cookie: 'pref_timestamps=clock',
    })
    expect(el.output.querySelector('.perm-prefix')).toBeNull()
  })

  it('sets --perm-prefix-width CSS variable based on widest prefix', () => {
    const lines = [
      { text: 'first', cls: '' },
      { text: 'second', cls: '' },
      { text: 'third', cls: '' },
      { text: 'fourth', cls: '' },
      { text: 'fifth', cls: '' },
      { text: 'sixth', cls: '' },
      { text: 'seventh', cls: '' },
      { text: 'eighth', cls: '' },
      { text: 'ninth', cls: '' },
      { text: 'tenth', cls: '' },
    ]
    const { el } = loadPermalink({ lines, cookie: 'pref_line_numbers=on' })
    // 10 lines — widest prefix is '10' (2 chars)
    expect(el.output.style.getPropertyValue('--perm-prefix-width')).toBe('2ch')
  })
})

// ── toggle-ln ─────────────────────────────────────────────────────────────────

describe('toggle-ln button', () => {
  it('clicking toggle-ln flips label to "line numbers: on"', () => {
    const lines = [{ text: 'a', cls: '' }]
    const { el } = loadPermalink({ lines })
    expect(el.toggleLn.textContent).toBe('line numbers: off')
    el.toggleLn.click()
    expect(el.toggleLn.textContent).toBe('line numbers: on')
  })

  it('clicking toggle-ln twice returns to "line numbers: off"', () => {
    const lines = [{ text: 'a', cls: '' }]
    const { el } = loadPermalink({ lines })
    el.toggleLn.click()
    el.toggleLn.click()
    expect(el.toggleLn.textContent).toBe('line numbers: off')
  })

  it('clicking toggle-ln re-renders output with prefix spans', () => {
    const lines = [{ text: 'first', cls: '' }, { text: 'second', cls: '' }]
    const { el } = loadPermalink({ lines })
    expect(el.output.querySelector('.perm-prefix')).toBeNull()
    el.toggleLn.click()
    const prefixes = el.output.querySelectorAll('.perm-prefix')
    expect(prefixes.length).toBe(2)
    expect(prefixes[0].textContent).toBe('1')
    expect(prefixes[1].textContent).toBe('2')
  })
})

// ── toggle-ts ─────────────────────────────────────────────────────────────────

describe('toggle-ts button', () => {
  it('does nothing when hasTimestampMetadata is false', () => {
    const lines = [{ text: 'a', cls: '', tsE: '0.5s', tsC: '10:00:01' }]
    const { el } = loadPermalink({ lines, hasTimestampMetadata: false })
    el.toggleTs.click()
    // Still no prefix (timestamps still off)
    expect(el.output.querySelector('.perm-prefix')).toBeNull()
    expect(el.toggleTs.textContent).toBe('timestamps: unavailable')
  })

  it('cycles off → elapsed → clock → off when metadata present', () => {
    const lines = [{ text: 'a', cls: '', tsE: '0.5s', tsC: '10:00:01' }]
    const { el } = loadPermalink({ lines, hasTimestampMetadata: true })
    expect(el.toggleTs.textContent).toBe('timestamps: off')
    el.toggleTs.click()
    expect(el.toggleTs.textContent).toBe('timestamps: elapsed')
    el.toggleTs.click()
    expect(el.toggleTs.textContent).toBe('timestamps: clock')
    el.toggleTs.click()
    expect(el.toggleTs.textContent).toBe('timestamps: off')
  })

  it('re-renders output when mode changes', () => {
    const lines = [{ text: 'a', cls: '', tsE: '2.1s', tsC: '10:00:05' }]
    const { el } = loadPermalink({ lines, hasTimestampMetadata: true })
    expect(el.output.querySelector('.perm-prefix')).toBeNull()
    el.toggleTs.click() // → elapsed
    const prefix = el.output.querySelector('.perm-prefix')
    expect(prefix).not.toBeNull()
    expect(prefix.textContent).toBe('2.1s')
  })
})

// ── data-action dispatch ───────────────────────────────────────────────────────

describe('data-action dispatch', () => {
  it('copy-txt calls copyTextToClipboard with joined line text', async () => {
    const lines = [
      { text: 'line one', cls: '' },
      { text: 'line two', cls: '' },
    ]
    const { el, mocks } = loadPermalink({ lines })
    const btn = document.createElement('button')
    btn.dataset.action = 'copy-txt'
    el.container.appendChild(btn)
    btn.click()
    // copyTextToClipboard is called with the text of all lines joined by \n
    expect(mocks.copyTextToClipboard).toHaveBeenCalledOnce()
    const arg = mocks.copyTextToClipboard.mock.calls[0][0]
    expect(arg).toBe('line one\nline two')
  })

  it('copy-txt calls showToast on success', async () => {
    const lines = [{ text: 'hello', cls: '' }]
    const { el, mocks } = loadPermalink({ lines })
    mocks.copyTextToClipboard.mockResolvedValue(undefined)
    const btn = document.createElement('button')
    btn.dataset.action = 'copy-txt'
    el.container.appendChild(btn)
    btn.click()
    await Promise.resolve()
    expect(mocks.showToast).toHaveBeenCalledWith('Copied to clipboard')
  })

  it('save-txt triggers blob download with txt content', () => {
    const lines = [{ text: 'output text', cls: '' }]
    const { el, mocks } = loadPermalink({ lines })
    const btn = document.createElement('button')
    btn.dataset.action = 'save-txt'
    el.container.appendChild(btn)
    btn.click()
    expect(mocks.URL.createObjectURL).toHaveBeenCalledOnce()
    expect(mocks.URL.revokeObjectURL).toHaveBeenCalledOnce()
  })

  it('save-html calls ExportHtmlUtils chain', async () => {
    const lines = [{ text: 'out', cls: '' }]
    const { el, mocks } = loadPermalink({
      lines,
      appName: 'myapp',
      label: 'nmap scan',
      created: '2025-01-15T10:30:00Z',
      permalinkMeta: { exit_code: 0, duration: '1.2s', lines: '42', version: '1.5' },
    })
    const btn = document.createElement('button')
    btn.dataset.action = 'save-html'
    el.container.appendChild(btn)
    btn.click()
    // fetchTerminalExportCss is async — wait for promise chain
    await new Promise((r) => setTimeout(r, 0))
    expect(mocks.ExportHtmlUtils.fetchTerminalExportCss).toHaveBeenCalledOnce()
    expect(mocks.ExportHtmlUtils.buildExportLinesHtml).toHaveBeenCalledOnce()
    expect(mocks.ExportHtmlUtils.buildTerminalExportHtml).toHaveBeenCalledOnce()
    expect(mocks.URL.createObjectURL).toHaveBeenCalledOnce()
  })

  it('save-html passes runMeta with exit_code, duration, lines, version', async () => {
    const lines = [{ text: 'out', cls: '' }]
    const { el, mocks } = loadPermalink({
      lines,
      permalinkMeta: { exit_code: 1, duration: '0.5s', lines: '10', version: '1.5' },
    })
    const btn = document.createElement('button')
    btn.dataset.action = 'save-html'
    el.container.appendChild(btn)
    btn.click()
    await new Promise((r) => setTimeout(r, 0))
    const call = mocks.ExportHtmlUtils.buildTerminalExportHtml.mock.calls[0][0]
    expect(call.runMeta).toEqual({
      exitCode: 1,
      duration: '0.5s',
      lines: '10',
      version: '1.5',
    })
  })

  it('save-html passes null runMeta when permalinkMeta is null', async () => {
    const lines = [{ text: 'out', cls: '' }]
    const { el, mocks } = loadPermalink({ lines, permalinkMeta: null })
    const btn = document.createElement('button')
    btn.dataset.action = 'save-html'
    el.container.appendChild(btn)
    btn.click()
    await new Promise((r) => setTimeout(r, 0))
    const call = mocks.ExportHtmlUtils.buildTerminalExportHtml.mock.calls[0][0]
    expect(call.runMeta).toBeNull()
  })

  it('save-pdf calls ExportPdfUtils.buildTerminalExportPdf and doc.save', () => {
    const lines = [{ text: 'out', cls: '' }]
    const { el, mocks } = loadPermalink({ lines })
    const btn = document.createElement('button')
    btn.dataset.action = 'save-pdf'
    el.container.appendChild(btn)
    btn.click()
    expect(mocks.ExportPdfUtils.buildTerminalExportPdf).toHaveBeenCalledOnce()
    const doc = mocks.ExportPdfUtils._doc
    expect(doc.save).toHaveBeenCalledOnce()
  })

  it('save-pdf download filename uses appName and exportTimestamp', () => {
    const lines = [{ text: 'out', cls: '' }]
    const { el, mocks } = loadPermalink({ lines, appName: 'darklab' })
    const btn = document.createElement('button')
    btn.dataset.action = 'save-pdf'
    el.container.appendChild(btn)
    btn.click()
    const doc = mocks.ExportPdfUtils._doc
    expect(doc.save).toHaveBeenCalledWith('darklab-2025-01-15T10-30-00.pdf')
  })

  it('does nothing for unknown data-action values', () => {
    const { el, mocks } = loadPermalink()
    const btn = document.createElement('button')
    btn.dataset.action = 'unknown-action'
    el.container.appendChild(btn)
    btn.click()
    expect(mocks.copyTextToClipboard).not.toHaveBeenCalled()
    expect(mocks.ExportHtmlUtils.buildExportLinesHtml).not.toHaveBeenCalled()
  })
})

// ── save dropdown ──────────────────────────────────────────────────────────────

describe('save dropdown', () => {
  it('clicking perm-save-btn toggles open class', () => {
    const { el } = loadPermalink()
    expect(el.saveWrap.classList.contains('open')).toBe(false)
    el.saveBtn.click()
    expect(el.saveWrap.classList.contains('open')).toBe(true)
  })

  it('clicking perm-save-btn again closes the dropdown', () => {
    const { el } = loadPermalink()
    el.saveBtn.click()
    el.saveBtn.click()
    expect(el.saveWrap.classList.contains('open')).toBe(false)
  })
})

// ── download filename ──────────────────────────────────────────────────────────

describe('download filename', () => {
  it('save-txt download uses appName and exportTimestamp', () => {
    const lines = [{ text: 'output', cls: '' }]
    const { el, mocks } = loadPermalink({ lines, appName: 'darklab' })
    const btn = document.createElement('button')
    btn.dataset.action = 'save-txt'
    el.container.appendChild(btn)
    btn.click()
    // The blob URL is created; we can't read the anchor download attr directly
    // but we can verify the exportTimestamp mock was called to build the name.
    expect(mocks.ExportHtmlUtils.exportTimestamp).toHaveBeenCalled()
  })

  it('save-html download uses appName and exportTimestamp', async () => {
    const lines = [{ text: 'output', cls: '' }]
    const { el, mocks } = loadPermalink({ lines, appName: 'myapp' })
    const btn = document.createElement('button')
    btn.dataset.action = 'save-html'
    el.container.appendChild(btn)
    btn.click()
    await new Promise((r) => setTimeout(r, 0))
    expect(mocks.ExportHtmlUtils.exportTimestamp).toHaveBeenCalled()
  })
})

// ── prefix in exported text ───────────────────────────────────────────────────

describe('copy-txt prefix formatting', () => {
  it('includes line numbers in copied text when lnMode is on', async () => {
    const lines = [{ text: 'cmd output', cls: '' }]
    const { el, mocks } = loadPermalink({
      lines,
      cookie: 'pref_line_numbers=on',
    })
    const btn = document.createElement('button')
    btn.dataset.action = 'copy-txt'
    el.container.appendChild(btn)
    btn.click()
    const text = mocks.copyTextToClipboard.mock.calls[0][0]
    // Should include "1  cmd output" (prefix + two spaces + text)
    expect(text).toBe('1  cmd output')
  })

  it('omits prefix in copied text when both lnMode and tsMode are off', async () => {
    const lines = [{ text: 'plain', cls: '' }]
    const { el, mocks } = loadPermalink({ lines })
    const btn = document.createElement('button')
    btn.dataset.action = 'copy-txt'
    el.container.appendChild(btn)
    btn.click()
    expect(mocks.copyTextToClipboard.mock.calls[0][0]).toBe('plain')
  })
})
