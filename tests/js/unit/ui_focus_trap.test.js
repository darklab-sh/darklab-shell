import { describe, it, beforeEach, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../../..')
const UI_FOCUS_TRAP_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/ui_focus_trap.js'),
  'utf8',
)

function loadFocusTrap() {
  new Function(UI_FOCUS_TRAP_SRC)()
  return window
}

function makeCard({ buttons = 0, include = [] } = {}) {
  const card = document.createElement('div')
  for (let i = 0; i < buttons; i += 1) {
    const btn = document.createElement('button')
    btn.textContent = `btn-${i}`
    btn.dataset.idx = String(i)
    card.appendChild(btn)
  }
  include.forEach((el) => card.appendChild(el))
  document.body.appendChild(card)
  return card
}

function tabEvent({ shift = false } = {}) {
  return new KeyboardEvent('keydown', {
    key: 'Tab',
    shiftKey: shift,
    bubbles: true,
    cancelable: true,
  })
}

function arrowEvent(key) {
  return new KeyboardEvent('keydown', {
    key,
    bubbles: true,
    cancelable: true,
  })
}

describe('bindFocusTrap', () => {
  let g

  beforeEach(() => {
    g = loadFocusTrap()
    document.body.replaceChildren()
  })

  it('wraps Tab from the last focusable back to the first', () => {
    const card = makeCard({ buttons: 3 })
    const [first, , last] = card.querySelectorAll('button')
    g.bindFocusTrap(card)
    last.focus()
    expect(document.activeElement).toBe(last)
    const ev = tabEvent()
    card.dispatchEvent(ev)
    expect(ev.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(first)
  })

  it('wraps Shift+Tab from the first focusable back to the last', () => {
    const card = makeCard({ buttons: 3 })
    const [first, , last] = card.querySelectorAll('button')
    g.bindFocusTrap(card)
    first.focus()
    expect(document.activeElement).toBe(first)
    const ev = tabEvent({ shift: true })
    card.dispatchEvent(ev)
    expect(ev.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(last)
  })

  it('does not preventDefault when Tab moves between middle focusables', () => {
    const card = makeCard({ buttons: 3 })
    const [, middle] = card.querySelectorAll('button')
    g.bindFocusTrap(card)
    middle.focus()
    const ev = tabEvent()
    card.dispatchEvent(ev)
    expect(ev.defaultPrevented).toBe(false)
  })

  it('is a no-op when the container has no focusable children', () => {
    const card = document.createElement('div')
    card.innerHTML = '<p>text only</p>'
    document.body.appendChild(card)
    g.bindFocusTrap(card)
    const ev = tabEvent()
    card.dispatchEvent(ev)
    expect(ev.defaultPrevented).toBe(false)
  })

  it('returns null on a re-bind to the same container (idempotent)', () => {
    const card = makeCard({ buttons: 2 })
    const first = g.bindFocusTrap(card)
    const second = g.bindFocusTrap(card)
    expect(first).not.toBeNull()
    expect(second).toBeNull()
  })

  it('dispose removes the keydown handler and clears the bound flag', () => {
    const card = makeCard({ buttons: 2 })
    const [firstBtn, lastBtn] = card.querySelectorAll('button')
    const handle = g.bindFocusTrap(card)
    expect(card.dataset.focusTrapBound).toBe('1')
    handle.dispose()
    expect(card.dataset.focusTrapBound).toBeUndefined()
    lastBtn.focus()
    const ev = tabEvent()
    card.dispatchEvent(ev)
    expect(ev.defaultPrevented).toBe(false)
    // sanity: the buttons still exist and are usable for subsequent binds
    expect(firstBtn.isConnected).toBe(true)
  })

  it('skips hidden focusables inside the container', () => {
    const hiddenBtn = document.createElement('button')
    hiddenBtn.textContent = 'hidden'
    hiddenBtn.hidden = true
    const card = makeCard({ buttons: 2, include: [hiddenBtn] })
    const [first, last] = card.querySelectorAll('button:not([hidden])')
    g.bindFocusTrap(card)
    last.focus()
    const ev = tabEvent()
    card.dispatchEvent(ev)
    expect(ev.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(first)
  })

  it('skips focusables with inline display:none (options-modal session-token buttons pattern)', () => {
    // Matches the real options-modal scenario: a button later in DOM order
    // is toggled to style="display:none" by app code, and the trap must
    // treat the *visible* last button as the boundary. Without this filter,
    // Tab from the actual last visible button would not match `active ===
    // last`, the handler would no-op, and focus would leak out of the card.
    const card = makeCard({ buttons: 2 })
    const trailingHidden = document.createElement('button')
    trailingHidden.textContent = 'trailing-hidden'
    trailingHidden.style.display = 'none'
    card.appendChild(trailingHidden)
    const [first, last] = card.querySelectorAll('button:not([style*="display: none"])')
    g.bindFocusTrap(card)
    last.focus()
    const ev = tabEvent()
    card.dispatchEvent(ev)
    expect(ev.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(first)
  })

  it('does not intercept arrow keys unless explicitly enabled', () => {
    const card = makeCard({ buttons: 2 })
    const [first] = card.querySelectorAll('button')
    g.bindFocusTrap(card)
    first.focus()
    const ev = arrowEvent('ArrowRight')
    card.dispatchEvent(ev)
    expect(ev.defaultPrevented).toBe(false)
    expect(document.activeElement).toBe(first)
  })

  it('cycles forward with ArrowRight and ArrowDown when arrow keys are enabled', () => {
    const card = makeCard({ buttons: 3 })
    const [first, middle, last] = card.querySelectorAll('button')
    g.bindFocusTrap(card, { arrowKeys: true })
    first.focus()

    const right = arrowEvent('ArrowRight')
    card.dispatchEvent(right)
    expect(right.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(middle)

    const down = arrowEvent('ArrowDown')
    card.dispatchEvent(down)
    expect(down.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(last)
  })

  it('cycles backward with ArrowLeft and ArrowUp when arrow keys are enabled', () => {
    const card = makeCard({ buttons: 3 })
    const [first, middle, last] = card.querySelectorAll('button')
    g.bindFocusTrap(card, { arrowKeys: true })
    middle.focus()

    const left = arrowEvent('ArrowLeft')
    card.dispatchEvent(left)
    expect(left.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(first)

    const up = arrowEvent('ArrowUp')
    card.dispatchEvent(up)
    expect(up.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(last)
  })

  it('wraps arrow-key navigation when arrow keys are enabled', () => {
    const card = makeCard({ buttons: 2 })
    const [first, last] = card.querySelectorAll('button')
    g.bindFocusTrap(card, { arrowKeys: true })
    last.focus()

    const forward = arrowEvent('ArrowRight')
    card.dispatchEvent(forward)
    expect(forward.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(first)

    const backward = arrowEvent('ArrowLeft')
    card.dispatchEvent(backward)
    expect(backward.defaultPrevented).toBe(true)
    expect(document.activeElement).toBe(last)
  })
})
