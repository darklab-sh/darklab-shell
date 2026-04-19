import { vi, describe, it, beforeEach, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

// ui_outside_click.js is an IIFE that installs bindOutsideClickClose on
// window. Each test reloads the source so there is no cross-test state.
const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../../..')
const UI_OUTSIDE_CLICK_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/ui_outside_click.js'),
  'utf8',
)

function loadHelper() {
  delete window.bindOutsideClickClose
  new Function(UI_OUTSIDE_CLICK_SRC)()
  return window
}

function dispatchClick(target) {
  target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
}

function makeDiv(parent) {
  const el = document.createElement('div')
  ;(parent || document.body).appendChild(el)
  return el
}

describe('bindOutsideClickClose', () => {
  let g

  beforeEach(() => {
    g = loadHelper()
    document.body.replaceChildren()
  })

  describe('guards', () => {
    it('accepts a null panel and exempts purely via triggers/selectors', () => {
      const onClose = vi.fn()
      const handle = g.bindOutsideClickClose(null, {
        exemptSelectors: ['.safe-zone'],
        isOpen: () => true,
        onClose,
      })
      expect(handle).not.toBeNull()
      const safe = makeDiv()
      safe.className = 'safe-zone'
      const outside = makeDiv()
      dispatchClick(safe)
      expect(onClose).not.toHaveBeenCalled()
      dispatchClick(outside)
      expect(onClose).toHaveBeenCalledTimes(1)
    })

    it('returns null when opts is missing', () => {
      expect(g.bindOutsideClickClose(makeDiv())).toBeNull()
    })

    it('returns null when isOpen is not a function', () => {
      expect(
        g.bindOutsideClickClose(makeDiv(), { onClose: () => {} }),
      ).toBeNull()
    })

    it('returns null when onClose is not a function', () => {
      expect(
        g.bindOutsideClickClose(makeDiv(), { isOpen: () => true }),
      ).toBeNull()
    })

    it('returns a handle with dispose()', () => {
      const handle = g.bindOutsideClickClose(makeDiv(), {
        isOpen: () => true,
        onClose: () => {},
      })
      expect(handle).not.toBeNull()
      expect(typeof handle.dispose).toBe('function')
    })
  })

  describe('outside-click dismissal', () => {
    it('closes when click lands outside the panel', () => {
      const panel = makeDiv()
      const outside = makeDiv()
      const onClose = vi.fn()
      g.bindOutsideClickClose(panel, { isOpen: () => true, onClose })
      dispatchClick(outside)
      expect(onClose).toHaveBeenCalledTimes(1)
    })

    it('does not close when click lands inside the panel', () => {
      const panel = makeDiv()
      const inner = makeDiv(panel)
      const onClose = vi.fn()
      g.bindOutsideClickClose(panel, { isOpen: () => true, onClose })
      dispatchClick(inner)
      expect(onClose).not.toHaveBeenCalled()
    })

    it('does not close when click lands on the panel element itself', () => {
      const panel = makeDiv()
      const onClose = vi.fn()
      g.bindOutsideClickClose(panel, { isOpen: () => true, onClose })
      dispatchClick(panel)
      expect(onClose).not.toHaveBeenCalled()
    })

    it('does not close when isOpen() returns false', () => {
      const panel = makeDiv()
      const outside = makeDiv()
      const onClose = vi.fn()
      let open = false
      g.bindOutsideClickClose(panel, { isOpen: () => open, onClose })
      dispatchClick(outside)
      expect(onClose).not.toHaveBeenCalled()
      open = true
      dispatchClick(outside)
      expect(onClose).toHaveBeenCalledTimes(1)
    })
  })

  describe('trigger exemption', () => {
    it('does not close when click lands on a registered trigger', () => {
      const panel = makeDiv()
      const trigger = makeDiv()
      const outside = makeDiv()
      const onClose = vi.fn()
      g.bindOutsideClickClose(panel, {
        triggers: trigger,
        isOpen: () => true,
        onClose,
      })
      dispatchClick(trigger)
      expect(onClose).not.toHaveBeenCalled()
      dispatchClick(outside)
      expect(onClose).toHaveBeenCalledTimes(1)
    })

    it('does not close when click lands inside a registered trigger', () => {
      const panel = makeDiv()
      const trigger = makeDiv()
      const innerSpan = document.createElement('span')
      trigger.appendChild(innerSpan)
      const onClose = vi.fn()
      g.bindOutsideClickClose(panel, {
        triggers: trigger,
        isOpen: () => true,
        onClose,
      })
      dispatchClick(innerSpan)
      expect(onClose).not.toHaveBeenCalled()
    })

    it('accepts an array of triggers and exempts each one', () => {
      const panel = makeDiv()
      const t1 = makeDiv()
      const t2 = makeDiv()
      const outside = makeDiv()
      const onClose = vi.fn()
      g.bindOutsideClickClose(panel, {
        triggers: [t1, t2],
        isOpen: () => true,
        onClose,
      })
      dispatchClick(t1)
      dispatchClick(t2)
      expect(onClose).not.toHaveBeenCalled()
      dispatchClick(outside)
      expect(onClose).toHaveBeenCalledTimes(1)
    })

    it('ignores falsy entries in the triggers array', () => {
      const panel = makeDiv()
      const t1 = makeDiv()
      const outside = makeDiv()
      const onClose = vi.fn()
      g.bindOutsideClickClose(panel, {
        triggers: [null, undefined, t1],
        isOpen: () => true,
        onClose,
      })
      dispatchClick(t1)
      expect(onClose).not.toHaveBeenCalled()
      dispatchClick(outside)
      expect(onClose).toHaveBeenCalledTimes(1)
    })
  })

  describe('exempt selectors', () => {
    it('does not close when the click target matches an exempt selector', () => {
      const panel = makeDiv()
      const outside = makeDiv()
      outside.className = 'hist-chip-overflow'
      const onClose = vi.fn()
      g.bindOutsideClickClose(panel, {
        exemptSelectors: ['.hist-chip-overflow'],
        isOpen: () => true,
        onClose,
      })
      dispatchClick(outside)
      expect(onClose).not.toHaveBeenCalled()
    })

    it('does not close when the click target is nested inside an exempt selector', () => {
      const panel = makeDiv()
      const outer = makeDiv()
      outer.setAttribute('data-action', 'history')
      const inner = document.createElement('span')
      outer.appendChild(inner)
      const onClose = vi.fn()
      g.bindOutsideClickClose(panel, {
        exemptSelectors: ['[data-action="history"]'],
        isOpen: () => true,
        onClose,
      })
      dispatchClick(inner)
      expect(onClose).not.toHaveBeenCalled()
    })

    it('accepts an array of exempt selectors', () => {
      const panel = makeDiv()
      const chip = makeDiv()
      chip.className = 'hist-chip-overflow'
      const action = makeDiv()
      action.setAttribute('data-action', 'history')
      const outside = makeDiv()
      const onClose = vi.fn()
      g.bindOutsideClickClose(panel, {
        exemptSelectors: ['.hist-chip-overflow', '[data-action="history"]'],
        isOpen: () => true,
        onClose,
      })
      dispatchClick(chip)
      dispatchClick(action)
      expect(onClose).not.toHaveBeenCalled()
      dispatchClick(outside)
      expect(onClose).toHaveBeenCalledTimes(1)
    })
  })

  describe('scope override', () => {
    it('only fires when clicks land inside the scope', () => {
      const scope = makeDiv()
      const panel = makeDiv(scope)
      const insideScope = makeDiv(scope)
      const outsideScope = makeDiv()
      const onClose = vi.fn()
      g.bindOutsideClickClose(panel, {
        scope,
        isOpen: () => true,
        onClose,
      })
      dispatchClick(outsideScope)
      expect(onClose).not.toHaveBeenCalled()
      dispatchClick(insideScope)
      expect(onClose).toHaveBeenCalledTimes(1)
    })
  })

  describe('handle API', () => {
    it('dispose() removes the listener so further clicks do not close', () => {
      const panel = makeDiv()
      const outside = makeDiv()
      const onClose = vi.fn()
      const handle = g.bindOutsideClickClose(panel, {
        isOpen: () => true,
        onClose,
      })
      dispatchClick(outside)
      expect(onClose).toHaveBeenCalledTimes(1)
      handle.dispose()
      dispatchClick(outside)
      expect(onClose).toHaveBeenCalledTimes(1)
    })

    it('dispose() on a scope-override handle removes the listener from that scope', () => {
      const scope = makeDiv()
      const panel = makeDiv(scope)
      const insideScope = makeDiv(scope)
      const onClose = vi.fn()
      const handle = g.bindOutsideClickClose(panel, {
        scope,
        isOpen: () => true,
        onClose,
      })
      dispatchClick(insideScope)
      expect(onClose).toHaveBeenCalledTimes(1)
      handle.dispose()
      dispatchClick(insideScope)
      expect(onClose).toHaveBeenCalledTimes(1)
    })
  })
})
