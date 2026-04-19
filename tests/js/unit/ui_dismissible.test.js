import { vi, describe, it, beforeEach, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

// ui_dismissible.js composes on top of ui_pressable.js (both are IIFEs
// that install helpers on window). Each test reloads both sources so
// the dismissible registry starts empty and binds against a known
// bindPressable global.
const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../../..')
const UI_PRESSABLE_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/ui_pressable.js'),
  'utf8',
)
const UI_DISMISSIBLE_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/ui_dismissible.js'),
  'utf8',
)

function loadHelpers({ loadPressable = true } = {}) {
  delete window.bindPressable
  delete window.bindDismissible
  delete window.closeTopmostDismissible
  if (loadPressable) new Function(UI_PRESSABLE_SRC)()
  new Function(UI_DISMISSIBLE_SRC)()
  return window
}

function makeOverlay(tag = 'div') {
  const el = document.createElement(tag)
  document.body.appendChild(el)
  return el
}

function dispatchClick(target) {
  target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
}

describe('bindDismissible', () => {
  let g

  beforeEach(() => {
    g = loadHelpers()
    document.body.replaceChildren()
  })

  describe('guards', () => {
    it('returns null when el is missing', () => {
      expect(g.bindDismissible(null, { level: 'panel', onClose: () => {} })).toBeNull()
    })

    it('returns null when opts is missing', () => {
      expect(g.bindDismissible(makeOverlay())).toBeNull()
    })

    it('returns null for unknown level', () => {
      expect(
        g.bindDismissible(makeOverlay(), { level: 'toast', onClose: () => {} }),
      ).toBeNull()
    })

    it('returns null when onClose is not a function', () => {
      expect(g.bindDismissible(makeOverlay(), { level: 'panel' })).toBeNull()
    })

    it('is idempotent via data-dismissible-bound', () => {
      const el = makeOverlay()
      const onClose = vi.fn()
      const first = g.bindDismissible(el, { level: 'panel', isOpen: () => true, onClose })
      const second = g.bindDismissible(el, { level: 'panel', isOpen: () => true, onClose })
      expect(first).not.toBeNull()
      expect(second).toBeNull()
      dispatchClick(el)
      expect(onClose).toHaveBeenCalledTimes(1)
    })
  })

  describe('backdrop click', () => {
    it('closes when click target is the overlay itself', () => {
      const el = makeOverlay()
      const onClose = vi.fn()
      g.bindDismissible(el, { level: 'panel', isOpen: () => true, onClose })
      dispatchClick(el)
      expect(onClose).toHaveBeenCalledTimes(1)
    })

    it('does not close when click target is a child', () => {
      const el = makeOverlay()
      const child = document.createElement('button')
      el.appendChild(child)
      const onClose = vi.fn()
      g.bindDismissible(el, { level: 'panel', isOpen: () => true, onClose })
      dispatchClick(child)
      expect(onClose).not.toHaveBeenCalled()
    })

    it('skips backdrop wiring when closeOnBackdrop is false', () => {
      const el = makeOverlay()
      const onClose = vi.fn()
      g.bindDismissible(el, {
        level: 'panel',
        isOpen: () => true,
        onClose,
        closeOnBackdrop: false,
      })
      dispatchClick(el)
      expect(onClose).not.toHaveBeenCalled()
    })

    it('does not call onClose when isOpen returns false', () => {
      const el = makeOverlay()
      const onClose = vi.fn()
      g.bindDismissible(el, { level: 'panel', isOpen: () => false, onClose })
      dispatchClick(el)
      expect(onClose).not.toHaveBeenCalled()
    })

    it('uses backdropEl override instead of el', () => {
      const el = makeOverlay()
      const scrim = makeOverlay()
      const onClose = vi.fn()
      g.bindDismissible(el, {
        level: 'sheet',
        backdropEl: scrim,
        isOpen: () => true,
        onClose,
      })
      dispatchClick(el)
      expect(onClose).not.toHaveBeenCalled()
      dispatchClick(scrim)
      expect(onClose).toHaveBeenCalledTimes(1)
    })

    it('backdropEl: null disables backdrop wiring entirely', () => {
      const el = makeOverlay()
      const onClose = vi.fn()
      g.bindDismissible(el, {
        level: 'sheet',
        backdropEl: null,
        isOpen: () => true,
        onClose,
      })
      dispatchClick(el)
      expect(onClose).not.toHaveBeenCalled()
    })
  })

  describe('close buttons', () => {
    it('wires a single close button', () => {
      const el = makeOverlay()
      const btn = document.createElement('button')
      document.body.appendChild(btn)
      const onClose = vi.fn()
      g.bindDismissible(el, {
        level: 'panel',
        isOpen: () => true,
        onClose,
        closeButtons: btn,
      })
      dispatchClick(btn)
      expect(onClose).toHaveBeenCalledTimes(1)
    })

    it('wires an array of close buttons', () => {
      const el = makeOverlay()
      const btn1 = document.createElement('button')
      const btn2 = document.createElement('button')
      document.body.append(btn1, btn2)
      const onClose = vi.fn()
      g.bindDismissible(el, {
        level: 'panel',
        isOpen: () => true,
        onClose,
        closeButtons: [btn1, btn2],
      })
      dispatchClick(btn1)
      dispatchClick(btn2)
      expect(onClose).toHaveBeenCalledTimes(2)
    })

    it('ignores falsy entries in the closeButtons array', () => {
      const el = makeOverlay()
      const btn = document.createElement('button')
      document.body.appendChild(btn)
      const onClose = vi.fn()
      expect(() =>
        g.bindDismissible(el, {
          level: 'panel',
          isOpen: () => true,
          onClose,
          closeButtons: [null, btn, undefined],
        }),
      ).not.toThrow()
      dispatchClick(btn)
      expect(onClose).toHaveBeenCalledTimes(1)
    })

    it('does not call onClose when surface is closed', () => {
      const el = makeOverlay()
      const btn = document.createElement('button')
      document.body.appendChild(btn)
      const onClose = vi.fn()
      g.bindDismissible(el, {
        level: 'panel',
        isOpen: () => false,
        onClose,
        closeButtons: btn,
      })
      dispatchClick(btn)
      expect(onClose).not.toHaveBeenCalled()
    })

    it('uses bindPressable when available so Enter activates the close button', () => {
      const el = makeOverlay()
      const btn = document.createElement('button')
      document.body.appendChild(btn)
      const onClose = vi.fn()
      g.bindDismissible(el, {
        level: 'panel',
        isOpen: () => true,
        onClose,
        closeButtons: btn,
      })
      expect(btn.dataset.pressableBound).toBe('1')
      dispatchClick(btn)
      expect(onClose).toHaveBeenCalledTimes(1)
    })

    it('falls back to plain click listener when bindPressable is unavailable', () => {
      delete window.bindPressable
      // Reload dismissible so it captures the missing pressable
      delete window.bindDismissible
      delete window.closeTopmostDismissible
      new Function(UI_DISMISSIBLE_SRC)()

      const el = makeOverlay()
      const btn = document.createElement('button')
      document.body.appendChild(btn)
      const onClose = vi.fn()
      window.bindDismissible(el, {
        level: 'panel',
        isOpen: () => true,
        onClose,
        closeButtons: btn,
      })
      expect(btn.dataset.pressableBound).toBeUndefined()
      dispatchClick(btn)
      expect(onClose).toHaveBeenCalledTimes(1)
    })

    it('respects a pre-existing pressable binding on the close button', () => {
      const el = makeOverlay()
      const btn = document.createElement('button')
      document.body.appendChild(btn)
      // Pretend something else already bound this button.
      btn.dataset.pressableBound = '1'
      const onClose = vi.fn()
      g.bindDismissible(el, {
        level: 'panel',
        isOpen: () => true,
        onClose,
        closeButtons: btn,
      })
      // Falls back to a plain click listener — still closes on click.
      dispatchClick(btn)
      expect(onClose).toHaveBeenCalledTimes(1)
    })
  })

  describe('handle API', () => {
    it('isOpen() mirrors the supplied isOpen fn', () => {
      let open = true
      const handle = g.bindDismissible(makeOverlay(), {
        level: 'panel',
        isOpen: () => open,
        onClose: () => {},
      })
      expect(handle.isOpen()).toBe(true)
      open = false
      expect(handle.isOpen()).toBe(false)
    })

    it('close() calls onClose when open', () => {
      const onClose = vi.fn()
      const handle = g.bindDismissible(makeOverlay(), {
        level: 'panel',
        isOpen: () => true,
        onClose,
      })
      handle.close()
      expect(onClose).toHaveBeenCalledTimes(1)
    })

    it('close() is a no-op when closed', () => {
      const onClose = vi.fn()
      const handle = g.bindDismissible(makeOverlay(), {
        level: 'panel',
        isOpen: () => false,
        onClose,
      })
      handle.close()
      expect(onClose).not.toHaveBeenCalled()
    })

    it('dispose() removes the entry from the registry', () => {
      const onClose = vi.fn()
      const handle = g.bindDismissible(makeOverlay(), {
        level: 'panel',
        isOpen: () => true,
        onClose,
      })
      handle.dispose()
      expect(g.closeTopmostDismissible()).toBe(false)
      expect(onClose).not.toHaveBeenCalled()
    })

    it('dispose() clears the bound marker so the element can rebind', () => {
      const el = makeOverlay()
      const handle = g.bindDismissible(el, {
        level: 'panel',
        isOpen: () => true,
        onClose: () => {},
      })
      expect(el.dataset.dismissibleBound).toBe('1')
      handle.dispose()
      expect(el.dataset.dismissibleBound).toBeUndefined()
      const rebound = g.bindDismissible(el, {
        level: 'panel',
        isOpen: () => true,
        onClose: () => {},
      })
      expect(rebound).not.toBeNull()
    })
  })

  describe('closeTopmostDismissible', () => {
    it('returns false and does nothing when nothing is open', () => {
      const onClose = vi.fn()
      g.bindDismissible(makeOverlay(), {
        level: 'panel',
        isOpen: () => false,
        onClose,
      })
      expect(g.closeTopmostDismissible()).toBe(false)
      expect(onClose).not.toHaveBeenCalled()
    })

    it('modal beats sheet beats panel', () => {
      const panelClose = vi.fn()
      const sheetClose = vi.fn()
      const modalClose = vi.fn()
      g.bindDismissible(makeOverlay(), { level: 'panel', isOpen: () => true, onClose: panelClose })
      g.bindDismissible(makeOverlay(), { level: 'sheet', isOpen: () => true, onClose: sheetClose })
      g.bindDismissible(makeOverlay(), { level: 'modal', isOpen: () => true, onClose: modalClose })
      expect(g.closeTopmostDismissible()).toBe(true)
      expect(modalClose).toHaveBeenCalledTimes(1)
      expect(sheetClose).not.toHaveBeenCalled()
      expect(panelClose).not.toHaveBeenCalled()
    })

    it('sheet wins over panel when no modal is open', () => {
      const panelClose = vi.fn()
      const sheetClose = vi.fn()
      g.bindDismissible(makeOverlay(), { level: 'panel', isOpen: () => true, onClose: panelClose })
      g.bindDismissible(makeOverlay(), { level: 'sheet', isOpen: () => true, onClose: sheetClose })
      expect(g.closeTopmostDismissible()).toBe(true)
      expect(sheetClose).toHaveBeenCalledTimes(1)
      expect(panelClose).not.toHaveBeenCalled()
    })

    it('most recently registered wins within the same level', () => {
      const firstClose = vi.fn()
      const secondClose = vi.fn()
      g.bindDismissible(makeOverlay(), { level: 'panel', isOpen: () => true, onClose: firstClose })
      g.bindDismissible(makeOverlay(), { level: 'panel', isOpen: () => true, onClose: secondClose })
      g.closeTopmostDismissible()
      expect(secondClose).toHaveBeenCalledTimes(1)
      expect(firstClose).not.toHaveBeenCalled()
    })

    it('skips entries that report closed', () => {
      const closedPanel = vi.fn()
      const openPanel = vi.fn()
      g.bindDismissible(makeOverlay(), {
        level: 'panel',
        isOpen: () => false,
        onClose: closedPanel,
      })
      g.bindDismissible(makeOverlay(), {
        level: 'panel',
        isOpen: () => true,
        onClose: openPanel,
      })
      g.closeTopmostDismissible()
      expect(openPanel).toHaveBeenCalledTimes(1)
      expect(closedPanel).not.toHaveBeenCalled()
    })

    it('closes only one surface per call', () => {
      const firstClose = vi.fn()
      const secondClose = vi.fn()
      g.bindDismissible(makeOverlay(), { level: 'panel', isOpen: () => true, onClose: firstClose })
      g.bindDismissible(makeOverlay(), { level: 'panel', isOpen: () => true, onClose: secondClose })
      g.closeTopmostDismissible()
      expect(firstClose).not.toHaveBeenCalled()
      expect(secondClose).toHaveBeenCalledTimes(1)
    })
  })
})
