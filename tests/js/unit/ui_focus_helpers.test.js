import { vi, describe, it, beforeEach, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

// focusElement + blurActiveElement live inside ui_helpers.js's IIFE, which
// needs state.js's getAppState() at load time. Bundle both and install the
// IIFE into window per test so there is no cross-test global leakage.
const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../../..')
const STATE_SRC = readFileSync(resolve(REPO_ROOT, 'app/static/js/state.js'), 'utf8')
const UI_HELPERS_SRC = readFileSync(resolve(REPO_ROOT, 'app/static/js/ui_helpers.js'), 'utf8')

function loadHelpers() {
  delete window.focusElement
  delete window.blurActiveElement
  new Function(STATE_SRC + '\n' + UI_HELPERS_SRC)()
  return window
}

describe('focusElement', () => {
  let g

  beforeEach(() => {
    g = loadHelpers()
    document.body.replaceChildren()
  })

  it('returns false when el is null', () => {
    expect(g.focusElement(null)).toBe(false)
  })

  it('returns false when el has no focus method', () => {
    expect(g.focusElement({})).toBe(false)
  })

  it('focuses a real DOM element and returns true', () => {
    const input = document.createElement('input')
    document.body.appendChild(input)
    expect(g.focusElement(input)).toBe(true)
    expect(document.activeElement).toBe(input)
  })

  it('passes { preventScroll: true } when requested', () => {
    const el = { focus: vi.fn() }
    g.focusElement(el, { preventScroll: true })
    expect(el.focus).toHaveBeenCalledWith({ preventScroll: true })
  })

  it('calls focus without options when preventScroll is omitted', () => {
    const el = { focus: vi.fn() }
    g.focusElement(el)
    expect(el.focus).toHaveBeenCalledWith()
  })

  it('falls back to bare focus() when preventScroll throws', () => {
    const calls = []
    const el = {
      focus(opts) {
        calls.push(opts)
        if (opts && opts.preventScroll) throw new Error('unsupported')
      },
    }
    expect(g.focusElement(el, { preventScroll: true })).toBe(true)
    expect(calls).toEqual([{ preventScroll: true }, undefined])
  })
})

describe('blurActiveElement', () => {
  let g

  beforeEach(() => {
    g = loadHelpers()
    document.body.replaceChildren()
  })

  function withActiveElement(value, fn) {
    const originalDesc = Object.getOwnPropertyDescriptor(document, 'activeElement')
    Object.defineProperty(document, 'activeElement', { configurable: true, get: () => value })
    try { fn() } finally {
      if (originalDesc) Object.defineProperty(document, 'activeElement', originalDesc)
      else delete document.activeElement
    }
  }

  it('returns false when activeElement is null', () => {
    withActiveElement(null, () => {
      expect(g.blurActiveElement()).toBe(false)
    })
  })

  it('returns false when the active element has no blur method', () => {
    withActiveElement({}, () => {
      expect(g.blurActiveElement()).toBe(false)
    })
  })

  it('blurs the focused element and returns true', () => {
    const input = document.createElement('input')
    document.body.appendChild(input)
    input.focus()
    expect(document.activeElement).toBe(input)
    expect(g.blurActiveElement()).toBe(true)
    expect(document.activeElement).not.toBe(input)
  })
})
