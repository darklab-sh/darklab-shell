import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'fs'
import { resolve, dirname, join } from 'path'
import { fileURLToPath } from 'url'
import { JSDOM } from 'jsdom'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../../..')
const TEMPLATE_DIR = join(REPO_ROOT, 'app/templates')
const FIXTURE_PATH = join(REPO_ROOT, 'tests/js/fixtures/button_primitive_allowlist.json')

// Positive counterpart to button_primitives.test.js. That suite blocks a
// hand-maintained list of retired class names; this one asserts the
// *opposite* contract: every button-like element in the HTML templates must
// either carry one of the allowed primitive classes (btn / nav-item /
// close-btn / toggle-btn / kb-key) OR match a selector in the allowlist
// fixture. The fixture documents surfaces that deliberately use a
// legacy/surface-specific class family instead of the primitives.
//
// Scope is deliberately HTML-only plus `<a role="button">`:
//  - <button> elements in app/templates/**.html
//  - any element carrying role="button" (including <a role="button">)
// Buttons injected by JS at runtime (e.g. tab close buttons) are not
// scanned here; their class names are covered by the negative blocklist in
// button_primitives.test.js or by their own unit suites.

const FIXTURE = JSON.parse(readFileSync(FIXTURE_PATH, 'utf8'))
const ALLOWED = new Set(FIXTURE.allowed_primitive_classes)
const EXCEPTION_SELECTORS = FIXTURE.exceptions.map(e => e.selector)

function walkHtml(dir) {
  const out = []
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    if (statSync(full).isDirectory()) out.push(...walkHtml(full))
    else if (name.endsWith('.html')) out.push(full)
  }
  return out
}

// Flask/Jinja tags would break the HTML parser on nested-attribute cases
// (e.g. `{% if toggle_ts_disabled %} disabled title="…"{% endif %}`).
// Replace the three Jinja delimiters with whitespace so jsdom sees plain
// HTML; the scan only cares about static tag/attribute shape.
function stripJinja(src) {
  return src
    .replace(/\{%[\s\S]*?%\}/g, ' ')
    .replace(/\{\{[\s\S]*?\}\}/g, ' ')
    .replace(/\{#[\s\S]*?#\}/g, ' ')
}

function identify(el) {
  if (el.id) return `#${el.id}`
  const cls = Array.from(el.classList).join('.')
  if (cls) return `${el.tagName.toLowerCase()}.${cls}`
  return `<${el.tagName.toLowerCase()}>`
}

function matchesAnyException(el) {
  for (const sel of EXCEPTION_SELECTORS) {
    try {
      if (el.matches(sel)) return true
    } catch {
      // Invalid selector in fixture — surface as a test failure via the
      // outer assertion rather than silently skipping.
      return false
    }
  }
  return false
}

describe('button primitive allowlist contract', () => {
  const files = walkHtml(TEMPLATE_DIR)

  for (const file of files) {
    const rel = file.replace(REPO_ROOT + '/', '')
    const dom = new JSDOM(stripJinja(readFileSync(file, 'utf8')))
    const { document } = dom.window

    const buttons = Array.from(
      document.querySelectorAll('button, [role="button"]')
    )

    it(`${rel}: every button-like element uses a primitive class or an allowlisted selector`, () => {
      const violations = []
      for (const el of buttons) {
        const classes = Array.from(el.classList)
        const hasPrimitive = classes.some(c => ALLOWED.has(c))
        if (hasPrimitive) continue
        if (matchesAnyException(el)) continue
        violations.push(`${identify(el)} → ${el.outerHTML.slice(0, 160).replace(/\s+/g, ' ')}`)
      }
      expect(violations).toEqual([])
    })
  }

  it('fixture selectors are all syntactically valid', () => {
    const dom = new JSDOM('<!doctype html><html><body></body></html>')
    const { document } = dom.window
    const invalid = []
    for (const sel of EXCEPTION_SELECTORS) {
      try {
        document.querySelector(sel)
      } catch (err) {
        invalid.push(`${sel} (${err.message})`)
      }
    }
    expect(invalid).toEqual([])
  })
})
