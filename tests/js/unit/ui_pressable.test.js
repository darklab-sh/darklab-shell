import { vi, describe, it, beforeEach, afterEach, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

// ui_pressable.js is an IIFE that installs `bindPressable` on its argument
// (window in the browser). Evaluate it with a scoped `global` param so each
// test can hand in a fresh stub and inspect the installed function without
// polluting window between tests.
const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../../..')
const UI_PRESSABLE_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/ui_pressable.js'),
  'utf8',
)

function loadPressable({ refocusComposerAfterAction = null } = {}) {
  // ui_pressable.js is an IIFE that installs bindPressable on its argument,
  // which resolves to `window` under jsdom. Set/clear the helper hook on
  // window and execute the source in the page context; return a reference to
  // window so tests can read bindPressable off it.
  if (refocusComposerAfterAction) {
    window.refocusComposerAfterAction = refocusComposerAfterAction
  } else {
    delete window.refocusComposerAfterAction
  }
  new Function(UI_PRESSABLE_SRC)()
  return window
}

// A minimal element helper — jsdom provides real DOM semantics.
function makeEl(tagName = 'div', { role = null, tabindex = null } = {}) {
  const el = document.createElement(tagName)
  if (role) el.setAttribute('role', role)
  if (tabindex !== null) el.setAttribute('tabindex', String(tabindex))
  document.body.appendChild(el)
  return el
}

describe('bindPressable', () => {
  let g
  let refocus

  beforeEach(() => {
    refocus = vi.fn()
    g = loadPressable({ refocusComposerAfterAction: refocus })
    document.body.replaceChildren()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('invokes onActivate on click for a native <button>', () => {
    const btn = makeEl('button')
    const onActivate = vi.fn()
    g.bindPressable(btn, { onActivate })
    btn.click()
    expect(onActivate).toHaveBeenCalledTimes(1)
  })

  it('invokes onActivate on Enter for role="button" div', () => {
    const div = makeEl('div', { role: 'button', tabindex: 0 })
    const onActivate = vi.fn()
    g.bindPressable(div, { onActivate })
    const ev = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true })
    div.dispatchEvent(ev)
    expect(onActivate).toHaveBeenCalledTimes(1)
    expect(ev.defaultPrevented).toBe(true)
  })

  it('invokes onActivate on Space for role="button" div', () => {
    const div = makeEl('div', { role: 'button', tabindex: 0 })
    const onActivate = vi.fn()
    g.bindPressable(div, { onActivate })
    div.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', bubbles: true, cancelable: true }))
    expect(onActivate).toHaveBeenCalledTimes(1)
  })

  it('ignores other keys', () => {
    const div = makeEl('div', { role: 'button', tabindex: 0 })
    const onActivate = vi.fn()
    g.bindPressable(div, { onActivate })
    div.dispatchEvent(new KeyboardEvent('keydown', { key: 'a' }))
    div.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(onActivate).not.toHaveBeenCalled()
  })

  it('does NOT add keydown listener for native <button> (browser handles Enter/Space)', () => {
    const btn = makeEl('button')
    const onActivate = vi.fn()
    g.bindPressable(btn, { onActivate })
    // Dispatching a keydown should NOT trigger our handler. The browser's own
    // activation is what fires click() for native buttons — we only want our
    // helper to add keyboard activation to NON-button elements so we don't
    // double-fire when the native implementation also dispatches click.
    btn.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
    expect(onActivate).not.toHaveBeenCalled()
  })

  it('is idempotent — second bind is a no-op', () => {
    const btn = makeEl('button')
    const onActivateA = vi.fn()
    const onActivateB = vi.fn()
    g.bindPressable(btn, { onActivate: onActivateA })
    g.bindPressable(btn, { onActivate: onActivateB })
    btn.click()
    expect(onActivateA).toHaveBeenCalledTimes(1)
    expect(onActivateB).not.toHaveBeenCalled()
  })

  it('blurs the element if it owns focus after activation', () => {
    const btn = makeEl('button')
    btn.focus()
    expect(document.activeElement).toBe(btn)
    g.bindPressable(btn, { onActivate: () => {} })
    btn.click()
    expect(document.activeElement).not.toBe(btn)
  })

  it('calls refocusComposerAfterAction by default', () => {
    const btn = makeEl('button')
    g.bindPressable(btn, { onActivate: () => {} })
    btn.click()
    expect(refocus).toHaveBeenCalledTimes(1)
    expect(refocus).toHaveBeenCalledWith({ preventScroll: true, defer: false })
  })

  it('skips refocus when refocusComposer: false', () => {
    const btn = makeEl('button')
    g.bindPressable(btn, { onActivate: () => {}, refocusComposer: false })
    btn.click()
    expect(refocus).not.toHaveBeenCalled()
  })

  it('passes defer through to refocus', () => {
    const btn = makeEl('button')
    g.bindPressable(btn, { onActivate: () => {}, defer: true })
    btn.click()
    expect(refocus).toHaveBeenCalledWith({ preventScroll: true, defer: true })
  })

  it('passes preventScroll: false through to refocus', () => {
    const btn = makeEl('button')
    g.bindPressable(btn, { onActivate: () => {}, preventScroll: false })
    btn.click()
    expect(refocus).toHaveBeenCalledWith({ preventScroll: false, defer: false })
  })

  it('runs refocus even if onActivate throws', () => {
    // The DOM event dispatcher reports errors from listeners rather than
    // rethrowing, so we swallow the window 'error' event to keep the test
    // runner from treating it as an unhandled exception.
    const swallow = (ev) => ev.preventDefault()
    window.addEventListener('error', swallow)
    try {
      const btn = makeEl('button')
      g.bindPressable(btn, { onActivate: () => { throw new Error('boom') } })
      btn.click()
      expect(refocus).toHaveBeenCalledTimes(1)
    } finally {
      window.removeEventListener('error', swallow)
    }
  })

  it('preventFocusTheft blocks pointerdown default (primary button only)', () => {
    const btn = makeEl('button')
    g.bindPressable(btn, { onActivate: () => {}, preventFocusTheft: true })
    const primary = new PointerEvent('pointerdown', { button: 0, cancelable: true, bubbles: true })
    btn.dispatchEvent(primary)
    expect(primary.defaultPrevented).toBe(true)

    const secondary = new PointerEvent('pointerdown', { button: 2, cancelable: true, bubbles: true })
    btn.dispatchEvent(secondary)
    expect(secondary.defaultPrevented).toBe(false)
  })

  it('preventFocusTheft: false does not add pointerdown listener', () => {
    const btn = makeEl('button')
    g.bindPressable(btn, { onActivate: () => {} })
    const ev = new PointerEvent('pointerdown', { button: 0, cancelable: true, bubbles: true })
    btn.dispatchEvent(ev)
    expect(ev.defaultPrevented).toBe(false)
  })

  it('clearPressStyle sets data-pressable-clearing then removes it', async () => {
    vi.useFakeTimers()
    const div = makeEl('div', { role: 'button', tabindex: 0 })
    g.bindPressable(div, { onActivate: () => {}, clearPressStyle: true })
    div.click()
    expect(div.dataset.pressableClearing).toBe('1')
    // requestAnimationFrame double-tick; jsdom's rAF is a setTimeout(~16ms)
    await vi.advanceTimersByTimeAsync(64)
    expect(div.dataset.pressableClearing).toBeUndefined()
  })

  it('clearPressStyle opt-out leaves no data attribute', () => {
    const div = makeEl('div', { role: 'button', tabindex: 0 })
    g.bindPressable(div, { onActivate: () => {} })
    div.click()
    expect(div.dataset.pressableClearing).toBeUndefined()
  })

  it('does nothing when onActivate is missing', () => {
    const btn = makeEl('button')
    expect(() => g.bindPressable(btn, {})).not.toThrow()
    expect(btn.dataset.pressableBound).toBeUndefined()
    btn.click()
    expect(refocus).not.toHaveBeenCalled()
  })

  it('does nothing when el is null', () => {
    expect(() => g.bindPressable(null, { onActivate: () => {} })).not.toThrow()
  })

  it('sets data-pressable-bound guard on successful bind', () => {
    const btn = makeEl('button')
    g.bindPressable(btn, { onActivate: () => {} })
    expect(btn.dataset.pressableBound).toBe('1')
  })

  it('tolerates missing refocusComposerAfterAction on global', () => {
    const isolated = loadPressable({}) // no refocus helper
    const btn = makeEl('button')
    const onActivate = vi.fn()
    isolated.bindPressable(btn, { onActivate })
    expect(() => btn.click()).not.toThrow()
    expect(onActivate).toHaveBeenCalledTimes(1)
  })

  describe('dispose', () => {
    it('returns a handle exposing dispose() on successful bind', () => {
      const btn = makeEl('button')
      const handle = g.bindPressable(btn, { onActivate: () => {} })
      expect(handle).not.toBeNull()
      expect(typeof handle.dispose).toBe('function')
    })

    it('returns null on guard-fail paths (missing onActivate, missing el, already bound)', () => {
      expect(g.bindPressable(null, { onActivate: () => {} })).toBeNull()
      expect(g.bindPressable(makeEl('button'), {})).toBeNull()
      const btn = makeEl('button')
      g.bindPressable(btn, { onActivate: () => {} })
      expect(g.bindPressable(btn, { onActivate: () => {} })).toBeNull()
    })

    it('dispose() removes the click listener', () => {
      const btn = makeEl('button')
      const onActivate = vi.fn()
      const handle = g.bindPressable(btn, { onActivate })
      handle.dispose()
      btn.click()
      expect(onActivate).not.toHaveBeenCalled()
    })

    it('dispose() removes the keydown listener for non-native buttons', () => {
      const div = makeEl('div', { role: 'button', tabindex: 0 })
      const onActivate = vi.fn()
      const handle = g.bindPressable(div, { onActivate })
      handle.dispose()
      div.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter' }))
      expect(onActivate).not.toHaveBeenCalled()
    })

    it('dispose() removes the pointerdown listener when preventFocusTheft was on', () => {
      const btn = makeEl('button')
      const handle = g.bindPressable(btn, { onActivate: () => {}, preventFocusTheft: true })
      handle.dispose()
      const ev = new MouseEvent('pointerdown', { button: 0, cancelable: true })
      btn.dispatchEvent(ev)
      expect(ev.defaultPrevented).toBe(false)
    })

    it('dispose() clears the data-pressable-bound marker so the element can rebind', () => {
      const btn = makeEl('button')
      const handle = g.bindPressable(btn, { onActivate: () => {} })
      expect(btn.dataset.pressableBound).toBe('1')
      handle.dispose()
      expect(btn.dataset.pressableBound).toBeUndefined()
      const onActivate = vi.fn()
      const rebound = g.bindPressable(btn, { onActivate })
      expect(rebound).not.toBeNull()
      btn.click()
      expect(onActivate).toHaveBeenCalledTimes(1)
    })
  })
})
