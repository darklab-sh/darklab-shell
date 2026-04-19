import { vi, describe, it, beforeEach, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

// ui_disclosure.js composes on top of ui_pressable.js (both are IIFEs that
// install helpers on window). Each test fresh-loads both sources into jsdom
// so bindDisclosure is evaluated against the same global the pressable
// helper writes to.
const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../../..')
const UI_PRESSABLE_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/ui_pressable.js'),
  'utf8',
)
const UI_DISCLOSURE_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/ui_disclosure.js'),
  'utf8',
)

function loadHelpers({ refocusComposerAfterAction = null, loadPressable = true } = {}) {
  if (refocusComposerAfterAction) {
    window.refocusComposerAfterAction = refocusComposerAfterAction
  } else {
    delete window.refocusComposerAfterAction
  }
  delete window.bindPressable
  delete window.bindDisclosure
  if (loadPressable) new Function(UI_PRESSABLE_SRC)()
  new Function(UI_DISCLOSURE_SRC)()
  return window
}

function makeTrigger(tagName = 'button') {
  const el = document.createElement(tagName)
  if (tagName !== 'button') {
    el.setAttribute('role', 'button')
    el.setAttribute('tabindex', '0')
  }
  document.body.appendChild(el)
  return el
}

function makePanel(className = 'panel') {
  const el = document.createElement('div')
  el.className = className
  document.body.appendChild(el)
  return el
}

describe('bindDisclosure', () => {
  let g
  let refocus

  beforeEach(() => {
    refocus = vi.fn()
    g = loadHelpers({ refocusComposerAfterAction: refocus })
    document.body.replaceChildren()
  })

  it('initializes aria-expanded=false when closed and does not set openClass on the panel', () => {
    const trigger = makeTrigger()
    const panel = makePanel()
    g.bindDisclosure(trigger, { panel })
    expect(trigger.getAttribute('aria-expanded')).toBe('false')
    expect(panel.classList.contains('open')).toBe(false)
  })

  it('initializes aria-expanded=true and sets openClass when initialOpen=true', () => {
    const trigger = makeTrigger()
    const panel = makePanel()
    g.bindDisclosure(trigger, { panel, initialOpen: true })
    expect(trigger.getAttribute('aria-expanded')).toBe('true')
    expect(panel.classList.contains('open')).toBe(true)
  })

  it('toggles aria-expanded and openClass on click', () => {
    const trigger = makeTrigger()
    const panel = makePanel()
    g.bindDisclosure(trigger, { panel })
    trigger.click()
    expect(trigger.getAttribute('aria-expanded')).toBe('true')
    expect(panel.classList.contains('open')).toBe(true)
    trigger.click()
    expect(trigger.getAttribute('aria-expanded')).toBe('false')
    expect(panel.classList.contains('open')).toBe(false)
  })

  it('supports a custom openClass (e.g. faq-open)', () => {
    const trigger = makeTrigger('div')
    const panel = makePanel('faq-item')
    g.bindDisclosure(trigger, { panel, openClass: 'faq-open' })
    trigger.click()
    expect(panel.classList.contains('faq-open')).toBe(true)
    expect(panel.classList.contains('open')).toBe(false)
  })

  it('supports hiddenClass (inverse) for u-hidden-style panels', () => {
    const trigger = makeTrigger()
    const panel = makePanel()
    panel.classList.add('u-hidden')
    g.bindDisclosure(trigger, { panel, openClass: null, hiddenClass: 'u-hidden' })
    // Initial sync: closed → hiddenClass added (already present, idempotent)
    expect(panel.classList.contains('u-hidden')).toBe(true)
    trigger.click()
    expect(panel.classList.contains('u-hidden')).toBe(false)
    trigger.click()
    expect(panel.classList.contains('u-hidden')).toBe(true)
  })

  it('does NOT touch panel classes when panel is null (caller owns visibility)', () => {
    const trigger = makeTrigger()
    const externalPanel = makePanel()
    externalPanel.classList.add('closed')
    g.bindDisclosure(trigger, { panel: null })
    trigger.click()
    expect(externalPanel.classList.contains('closed')).toBe(true)
  })

  it('emits onToggle only on user transitions, not on initial sync', () => {
    const trigger = makeTrigger()
    const panel = makePanel()
    const onToggle = vi.fn()
    g.bindDisclosure(trigger, { panel, onToggle })
    expect(onToggle).not.toHaveBeenCalled()
    trigger.click()
    expect(onToggle).toHaveBeenCalledTimes(1)
    expect(onToggle.mock.calls[0][0]).toBe(true)
    trigger.click()
    expect(onToggle).toHaveBeenCalledTimes(2)
    expect(onToggle.mock.calls[1][0]).toBe(false)
  })

  it('passes { trigger, panel } to onToggle', () => {
    const trigger = makeTrigger()
    const panel = makePanel()
    const onToggle = vi.fn()
    g.bindDisclosure(trigger, { panel, onToggle })
    trigger.click()
    expect(onToggle.mock.calls[0][1]).toEqual({ trigger, panel })
  })

  it('returned handle exposes isOpen/open/close/toggle', () => {
    const trigger = makeTrigger()
    const panel = makePanel()
    const h = g.bindDisclosure(trigger, { panel })
    expect(h.isOpen()).toBe(false)
    h.open()
    expect(h.isOpen()).toBe(true)
    expect(panel.classList.contains('open')).toBe(true)
    h.close()
    expect(h.isOpen()).toBe(false)
    expect(panel.classList.contains('open')).toBe(false)
    h.toggle()
    expect(h.isOpen()).toBe(true)
  })

  it('open() is a no-op when already open (no onToggle fire)', () => {
    const trigger = makeTrigger()
    const onToggle = vi.fn()
    const h = g.bindDisclosure(trigger, { initialOpen: true, onToggle })
    h.open()
    expect(onToggle).not.toHaveBeenCalled()
  })

  it('close() is a no-op when already closed (no onToggle fire)', () => {
    const trigger = makeTrigger()
    const onToggle = vi.fn()
    const h = g.bindDisclosure(trigger, { onToggle })
    h.close()
    expect(onToggle).not.toHaveBeenCalled()
  })

  it('imperative open()/close()/toggle() DO emit onToggle when state changes', () => {
    const trigger = makeTrigger()
    const onToggle = vi.fn()
    const h = g.bindDisclosure(trigger, { onToggle })
    h.open()
    expect(onToggle).toHaveBeenCalledTimes(1)
    h.close()
    expect(onToggle).toHaveBeenCalledTimes(2)
    h.toggle()
    expect(onToggle).toHaveBeenCalledTimes(3)
  })

  it('is idempotent — second bindDisclosure on the same trigger is a no-op', () => {
    const trigger = makeTrigger()
    const panel = makePanel()
    const first = g.bindDisclosure(trigger, { panel })
    const second = g.bindDisclosure(trigger, { panel })
    expect(second).toBeNull()
    trigger.click()
    // Single binding → one toggle per click
    expect(panel.classList.contains('open')).toBe(true)
    expect(first.isOpen()).toBe(true)
  })

  it('stopPropagation:true stops click bubbling to document', () => {
    const trigger = makeTrigger()
    const docListener = vi.fn()
    document.addEventListener('click', docListener)
    g.bindDisclosure(trigger, { stopPropagation: true })
    trigger.click()
    expect(docListener).not.toHaveBeenCalled()
    document.removeEventListener('click', docListener)
  })

  it('stopPropagation:false (default) lets click bubble to document', () => {
    const trigger = makeTrigger()
    const docListener = vi.fn()
    document.addEventListener('click', docListener)
    g.bindDisclosure(trigger, {})
    trigger.click()
    expect(docListener).toHaveBeenCalledTimes(1)
    document.removeEventListener('click', docListener)
  })

  it('returns null when trigger is falsy', () => {
    expect(g.bindDisclosure(null, {})).toBeNull()
    expect(g.bindDisclosure(undefined, {})).toBeNull()
  })

  it('returns null when opts is falsy', () => {
    const trigger = makeTrigger()
    expect(g.bindDisclosure(trigger, null)).toBeNull()
  })

  it('returns null when bindPressable is not on the global', () => {
    const trigger = makeTrigger()
    // Reload with bindPressable missing
    delete window.bindPressable
    new Function(UI_DISCLOSURE_SRC)()
    expect(window.bindDisclosure(trigger, {})).toBeNull()
  })

  it('does not refocus the composer by default (disclosures keep focus on trigger)', () => {
    const trigger = makeTrigger()
    g.bindDisclosure(trigger, {})
    trigger.click()
    expect(refocus).not.toHaveBeenCalled()
  })

  it('refocusComposer:true is forwarded to bindPressable', () => {
    const trigger = makeTrigger()
    g.bindDisclosure(trigger, { refocusComposer: true })
    trigger.click()
    expect(refocus).toHaveBeenCalledTimes(1)
  })

  it('clearPressStyle:true is forwarded to bindPressable (data-attr lifecycle)', () => {
    const trigger = makeTrigger('div')
    g.bindDisclosure(trigger, { clearPressStyle: true })
    trigger.click()
    // bindPressable sets data-pressable-clearing synchronously
    expect(trigger.dataset.pressableClearing).toBe('1')
  })

  it('Enter/Space activates disclosure on role="button" divs (inherits from pressable)', () => {
    const trigger = makeTrigger('div')
    const panel = makePanel()
    g.bindDisclosure(trigger, { panel })
    trigger.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
    expect(panel.classList.contains('open')).toBe(true)
    trigger.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', bubbles: true }))
    expect(panel.classList.contains('open')).toBe(false)
  })

  it('sets data-disclosure-bound marker on the trigger', () => {
    const trigger = makeTrigger()
    g.bindDisclosure(trigger, {})
    expect(trigger.dataset.disclosureBound).toBe('1')
  })
})
