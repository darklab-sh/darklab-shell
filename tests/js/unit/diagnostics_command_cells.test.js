// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { initialize } from '../../../app/static/js/features/diagnostics/command_cells.js'

let listeners
beforeAll(() => {
  const registration = vi.spyOn(document, 'addEventListener')
  initialize()
  listeners = [...registration.mock.calls]
  registration.mockRestore()
})
afterAll(() => {
  for (const [type, listener, options] of listeners) document.removeEventListener(type, listener, options)
})
beforeEach(() => {
  // Refresh replaces the cells after the document-level handlers are installed.
  document.body.innerHTML = '<table><tbody><tr><td class="diag-cmd-cell" tabindex="0" role="button" aria-expanded="false"><span>echo keyboard-fixture</span></td></tr></tbody></table>'
})

describe('diagnostics command cells', () => {
  it.each(['click', 'Enter', ' '])('toggles refreshed cells with %j', action => {
    const cell = document.querySelector('.diag-cmd-cell')
    const dispatch = () => {
      const event = action === 'click'
        ? new MouseEvent('click', { bubbles: true, cancelable: true })
        : new KeyboardEvent('keydown', { key: action, bubbles: true, cancelable: true })
      cell.querySelector('span').dispatchEvent(event)
      if (action !== 'click') expect(event.defaultPrevented).toBe(true)
    }
    dispatch()
    expect(cell.classList.contains('expanded')).toBe(true)
    expect(cell.getAttribute('aria-expanded')).toBe('true')
    dispatch()
    expect(cell.classList.contains('expanded')).toBe(false)
    expect(cell.getAttribute('aria-expanded')).toBe('false')
  })

  it('leaves unrelated keys alone', () => {
    const cell = document.querySelector('.diag-cmd-cell')
    const event = new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true, cancelable: true })
    cell.dispatchEvent(event)
    expect(event.defaultPrevented).toBe(false)
    expect(cell.getAttribute('aria-expanded')).toBe('false')
    expect(cell.classList.contains('expanded')).toBe(false)
  })
})
