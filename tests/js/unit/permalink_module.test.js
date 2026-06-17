import { resolve, dirname } from 'path'
import { fileURLToPath, pathToFileURL } from 'url'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../../../')
const PERMALINK_ENTRY_URL = pathToFileURL(resolve(REPO_ROOT, 'app/static/js/permalink.entry.js')).href

function makeAnsiUpMock() {
  const instance = { ansi_to_html: vi.fn((text) => text), use_classes: false }
  function MockAnsiUp() { return instance }
  return { Ctor: MockAnsiUp, instance }
}

beforeEach(() => {
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
})

afterEach(() => {
  vi.restoreAllMocks()
  document.body.innerHTML = ''
  delete window.AnsiUp
  delete window.PermData
  delete window.ExportHtmlUtils
  delete window.DarklabRunOutputModel
  delete window.DarklabOutputCore
})

describe('permalink module entry', () => {
  it('loads the source-mode import graph and renders output', async () => {
    document.body.innerHTML = `
      <script id="lazy-assets-json" type="application/json">{}</script>
      <main id="output"></main>
      <button id="toggle-ln"></button>
      <button id="toggle-ts"></button>
      <button id="toggle-highlights"></button>
      <div id="perm-save-wrap">
        <button id="perm-save-btn"></button>
        <div class="save-menu"></div>
      </div>
      <div id="permalink-toast"></div>
    `
    const ansiUp = makeAnsiUpMock()
    window.AnsiUp = ansiUp.Ctor
    window.PermData = {
      lines: [{ text: 'module line', cls: '' }],
      hasTimestampMetadata: false,
      appName: 'darklab',
      label: 'module smoke',
      created: '2026-06-11T00:00:00Z',
    }

    await import(`${PERMALINK_ENTRY_URL}?test=${Date.now()}`)

    expect(document.querySelectorAll('#output .line')).toHaveLength(1)
    expect(document.getElementById('output').textContent).toContain('module line')
    expect(ansiUp.instance.ansi_to_html).toHaveBeenCalledWith('module line')
  })
})
