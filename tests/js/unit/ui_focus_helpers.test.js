// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { vi, describe, it, beforeEach, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'
import { stripEsmExports } from './helpers/extract.js'

// focusElement + blurActiveElement live inside ui_helpers.js's IIFE, which
// needs state.js's getAppState() at load time. Bundle both and install the
// IIFE into window per test so there is no cross-test global leakage.
const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../../..')
const STATE_SRC = stripEsmExports(readFileSync(resolve(REPO_ROOT, 'app/static/js/core/state.js'), 'utf8'))
const UI_HELPERS_SRC = stripEsmExports(readFileSync(resolve(REPO_ROOT, 'app/static/js/ui/ui_helpers.js'), 'utf8'))

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

describe('app-native select enhancement', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <select id="demo-select" class="form-select" aria-label="Demo select">
        <option value="one">One</option>
        <option value="two">Two</option>
      </select>
    `
  })

  it('keeps the native select as state while rendering a themed trigger', () => {
    const g = loadHelpers()
    const select = document.getElementById('demo-select')
    const trigger = document.querySelector('.app-select-trigger')

    expect(select.classList.contains('app-select-native')).toBe(true)
    expect(trigger).not.toBeNull()
    expect(trigger.textContent).toContain('One')

    select.value = 'two'
    g.syncAppSelect(select)
    expect(trigger.textContent).toContain('Two')
  })

  it('dispatches normal change events when choosing an app-native option', () => {
    document.getElementById('demo-select').dataset.portalMenu = 'true'
    const originalScrollHeight = Object.getOwnPropertyDescriptor(window.HTMLElement.prototype, 'scrollHeight')
    Object.defineProperty(window.HTMLElement.prototype, 'scrollHeight', {
      configurable: true,
      get() {
        return this.classList?.contains('app-select-menu') ? 120 : 0
      },
    })
    loadHelpers()
    const select = document.getElementById('demo-select')
    const onChange = vi.fn()
    select.addEventListener('change', onChange)
    const trigger = document.querySelector('.app-select-trigger')
    trigger.getBoundingClientRect = () => ({
      top: 530,
      bottom: 564,
      left: 24,
      right: 224,
      width: 200,
      height: 34,
      x: 24,
      y: 530,
    })
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 600 })
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 390 })
    Object.defineProperty(window, 'visualViewport', {
      configurable: true,
      value: { offsetTop: 0, offsetLeft: 0, width: 390, height: 500 },
    })

    try {
      trigger.click()
      const menu = document.querySelector('.app-select-menu')
      expect(menu.parentElement).toBe(document.body)
      expect(menu.classList.contains('dropdown-up')).toBe(true)
      expect(menu.style.maxHeight).toBe('320px')
      expect(menu.style.top).toBe('410px')
      document.querySelector('.app-select-menu [data-value="two"]').click()
    } finally {
      if (originalScrollHeight) {
        Object.defineProperty(window.HTMLElement.prototype, 'scrollHeight', originalScrollHeight)
      } else {
        delete window.HTMLElement.prototype.scrollHeight
      }
    }

    expect(select.value).toBe('two')
    expect(onChange).toHaveBeenCalledTimes(1)
  })

  it('portals modal selects so menus escape clipped dialog bodies', () => {
    document.body.innerHTML = `
      <div role="dialog" aria-modal="true">
        <select id="demo-select" class="form-select" aria-label="Dialog select">
          <option value="name">Name</option>
          <option value="modified">Modified</option>
          <option value="size">Size</option>
        </select>
      </div>
    `
    const originalScrollHeight = Object.getOwnPropertyDescriptor(window.HTMLElement.prototype, 'scrollHeight')
    Object.defineProperty(window.HTMLElement.prototype, 'scrollHeight', {
      configurable: true,
      get() {
        return this.classList?.contains('app-select-menu') ? 120 : 0
      },
    })
    loadHelpers()
    const trigger = document.querySelector('.app-select-trigger')
    trigger.getBoundingClientRect = () => ({
      top: 530,
      bottom: 564,
      left: 260,
      right: 356,
      width: 96,
      height: 34,
      x: 260,
      y: 530,
    })
    Object.defineProperty(window, 'innerHeight', { configurable: true, value: 600 })
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: 390 })
    Object.defineProperty(window, 'visualViewport', {
      configurable: true,
      value: { offsetTop: 0, offsetLeft: 0, width: 390, height: 500 },
    })

    try {
      trigger.click()
      const menu = document.querySelector('.app-select-menu')
      expect(menu.parentElement).toBe(document.body)
      expect(menu.classList.contains('dropdown-up')).toBe(true)
      expect(menu.style.position).toBe('fixed')
      expect(menu.style.top).toBe('410px')
      expect(menu.style.width).toBe('144px')
      expect(menu.style.left).toBe('212px')
      expect([...menu.querySelectorAll('[role="option"]')].map(option => option.textContent))
        .toEqual(['Name', 'Modified', 'Size'])
    } finally {
      if (originalScrollHeight) {
        Object.defineProperty(window.HTMLElement.prototype, 'scrollHeight', originalScrollHeight)
      } else {
        delete window.HTMLElement.prototype.scrollHeight
      }
    }
  })

  it('refreshes custom menu options when native select options change', () => {
    const g = loadHelpers()
    const select = document.getElementById('demo-select')
    const option = document.createElement('option')
    option.value = 'three'
    option.textContent = 'Three'
    select.appendChild(option)

    g.syncAppSelect(select)

    expect([...document.querySelectorAll('.app-select-menu [role="option"]')].map(btn => btn.textContent)).toEqual([
      'One',
      'Two',
      'Three',
    ])
  })

  it('enhances form-select controls inserted after startup', async () => {
    loadHelpers()
    document.body.replaceChildren()

    const select = document.createElement('select')
    select.className = 'form-select'
    select.setAttribute('aria-label', 'Dynamic select')
    const option = document.createElement('option')
    option.value = 'dynamic'
    option.textContent = 'Dynamic'
    select.appendChild(option)

    document.body.appendChild(select)
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(select.classList.contains('app-select-native')).toBe(true)
    expect(select.nextElementSibling?.classList.contains('app-select')).toBe(true)
    expect(select.nextElementSibling?.querySelector('.app-select-trigger')?.textContent).toContain('Dynamic')
  })
})
