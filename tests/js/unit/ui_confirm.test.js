import { vi, describe, it, beforeEach, afterEach, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

// ui_confirm.js composes on top of ui_pressable.js and ui_dismissible.js
// (both are IIFEs that install helpers on window). Each test reloads all
// three sources so the dismissible registry and the primitive's open
// state both start clean.
const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../../..')
const UI_PRESSABLE_SRC = readFileSync(resolve(REPO_ROOT, 'app/static/js/ui_pressable.js'), 'utf8')
const UI_DISMISSIBLE_SRC = readFileSync(resolve(REPO_ROOT, 'app/static/js/ui_dismissible.js'), 'utf8')
const UI_CONFIRM_SRC = readFileSync(resolve(REPO_ROOT, 'app/static/js/ui_confirm.js'), 'utf8')

function mountHost() {
  document.body.innerHTML = `
    <div id="confirm-host" class="modal-overlay u-hidden">
      <div class="modal-card modal-card-compact" data-confirm-card>
        <div class="modal-copy" data-confirm-body></div>
        <div class="modal-actions modal-actions-wrap" data-confirm-actions></div>
      </div>
    </div>
  `
}

function loadHelpers() {
  delete window.bindPressable
  delete window.bindDismissible
  delete window.closeTopmostDismissible
  delete window.showConfirm
  delete window.cancelConfirm
  delete window.isConfirmOpen
  delete window.refocusComposerAfterAction
  delete window.showModalOverlay
  delete window.hideModalOverlay
  delete window.bindMobileSheet
  // Stubs: ui_confirm.js calls showModalOverlay/hideModalOverlay on the
  // host and refocusComposerAfterAction after resolve. Provide minimal
  // stand-ins so the primitive can exercise its own flow without loading
  // the full ui_helpers bundle.
  window.showModalOverlay = (el, display = 'flex') => {
    if (el && el.style) el.style.display = display
  }
  window.hideModalOverlay = (el) => {
    if (el && el.style) el.style.display = 'none'
  }
  window.refocusComposerAfterAction = vi.fn()
  window.bindMobileSheet = vi.fn()
  new Function(UI_PRESSABLE_SRC)()
  new Function(UI_DISMISSIBLE_SRC)()
  new Function(UI_CONFIRM_SRC)()
  return window
}

const KILL_ACTIONS = [
  { id: 'cancel', label: 'Cancel', role: 'cancel' },
  { id: 'confirm', label: '■ Kill', role: 'primary', tone: 'danger' },
]

describe('showConfirm', () => {
  let g

  beforeEach(() => {
    // matchMedia is used by ui_confirm for the stacking breakpoint
    // listener; jsdom doesn't provide one.
    if (!window.matchMedia) {
      window.matchMedia = vi.fn((_q) => ({
        matches: false,
        addEventListener: () => {},
        removeEventListener: () => {},
        addListener: () => {},
        removeListener: () => {},
      }))
    }
    mountHost()
    g = loadHelpers()
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  describe('guards', () => {
    it('rejects when #confirm-host is not present', async () => {
      document.body.innerHTML = ''
      await expect(g.showConfirm({ actions: KILL_ACTIONS })).rejects.toThrow(/confirm-host/)
    })

    it('rejects when actions is empty', async () => {
      await expect(g.showConfirm({ actions: [] })).rejects.toThrow(/actions required/)
    })

    it('rejects when actions is missing', async () => {
      await expect(g.showConfirm({})).rejects.toThrow(/actions required/)
    })

    it('rejects a concurrent second call', async () => {
      const first = g.showConfirm({ actions: KILL_ACTIONS })
      await expect(g.showConfirm({ actions: KILL_ACTIONS })).rejects.toThrow(/already open/)
      // Resolve the first call so subsequent tests start clean.
      g.cancelConfirm()
      await first
    })
  })

  describe('resolution', () => {
    it('resolves with the clicked action id', async () => {
      const promise = g.showConfirm({ actions: KILL_ACTIONS })
      document.querySelector('[data-confirm-action-id="confirm"]').click()
      await expect(promise).resolves.toBe('confirm')
    })

    it('resolves null when the cancel action is clicked', async () => {
      // The role:'cancel' action still resolves with its id, not null.
      // The primitive treats cancel like any other action; "null" is
      // reserved for non-button dismissal (Escape / backdrop / mobile
      // drag / cancelConfirm).
      const promise = g.showConfirm({ actions: KILL_ACTIONS })
      document.querySelector('[data-confirm-action-id="cancel"]').click()
      await expect(promise).resolves.toBe('cancel')
    })

    it('resolves null on backdrop click', async () => {
      const promise = g.showConfirm({ actions: KILL_ACTIONS })
      const host = document.getElementById('confirm-host')
      host.dispatchEvent(new MouseEvent('click', { bubbles: true }))
      await expect(promise).resolves.toBeNull()
    })

    it('resolves null on Escape via closeTopmostDismissible', async () => {
      const promise = g.showConfirm({ actions: KILL_ACTIONS })
      expect(g.isConfirmOpen()).toBe(true)
      const closed = g.closeTopmostDismissible()
      expect(closed).toBe(true)
      await expect(promise).resolves.toBeNull()
      expect(g.isConfirmOpen()).toBe(false)
    })

    it('resolves null via cancelConfirm()', async () => {
      const promise = g.showConfirm({ actions: KILL_ACTIONS })
      g.cancelConfirm()
      await expect(promise).resolves.toBeNull()
    })

    it('hides the host and clears action markup after resolve', async () => {
      const promise = g.showConfirm({ actions: KILL_ACTIONS })
      const host = document.getElementById('confirm-host')
      const actionsEl = host.querySelector('[data-confirm-actions]')
      expect(actionsEl.children.length).toBe(2)
      document.querySelector('[data-confirm-action-id="cancel"]').click()
      await promise
      expect(host.style.display).toBe('none')
      expect(host.classList.contains('u-hidden')).toBe(true)
      expect(actionsEl.children.length).toBe(0)
    })

    it('refocuses the composer on resolve', async () => {
      const promise = g.showConfirm({ actions: KILL_ACTIONS })
      document.querySelector('[data-confirm-action-id="confirm"]').click()
      await promise
      expect(g.refocusComposerAfterAction).toHaveBeenCalledWith({ defer: true })
    })
  })

  describe('body rendering', () => {
    it('renders a plain string body', async () => {
      const promise = g.showConfirm({ body: 'plain message', actions: KILL_ACTIONS })
      expect(document.querySelector('[data-confirm-body]').textContent).toBe('plain message')
      g.cancelConfirm()
      await promise
    })

    it('renders {text, note} as text + <br> + .modal-copy-note span', async () => {
      const promise = g.showConfirm({
        body: { text: 'primary copy', note: 'secondary note' },
        actions: KILL_ACTIONS,
      })
      const body = document.querySelector('[data-confirm-body]')
      expect(body.textContent).toContain('primary copy')
      expect(body.textContent).toContain('secondary note')
      expect(body.querySelector('br')).not.toBeNull()
      const note = body.querySelector('.modal-copy-note')
      expect(note).not.toBeNull()
      expect(note.textContent).toBe('secondary note')
      g.cancelConfirm()
      await promise
    })

    it('renders a Node body directly', async () => {
      const node = document.createElement('em')
      node.textContent = 'italic'
      const promise = g.showConfirm({ body: node, actions: KILL_ACTIONS })
      const body = document.querySelector('[data-confirm-body]')
      expect(body.querySelector('em')).not.toBeNull()
      expect(body.textContent).toBe('italic')
      g.cancelConfirm()
      await promise
    })
  })

  describe('tone', () => {
    it('applies modal-card-danger when tone: danger', async () => {
      const promise = g.showConfirm({ tone: 'danger', actions: KILL_ACTIONS })
      expect(
        document.querySelector('[data-confirm-card]').classList.contains('modal-card-danger'),
      ).toBe(true)
      g.cancelConfirm()
      await promise
    })

    it('applies modal-card-warning when tone: warning', async () => {
      const promise = g.showConfirm({ tone: 'warning', actions: KILL_ACTIONS })
      expect(
        document.querySelector('[data-confirm-card]').classList.contains('modal-card-warning'),
      ).toBe(true)
      g.cancelConfirm()
      await promise
    })

    it('applies neither tone class when tone is omitted', async () => {
      const promise = g.showConfirm({ actions: KILL_ACTIONS })
      const card = document.querySelector('[data-confirm-card]')
      expect(card.classList.contains('modal-card-danger')).toBe(false)
      expect(card.classList.contains('modal-card-warning')).toBe(false)
      g.cancelConfirm()
      await promise
    })

    it('clears stale tone class between opens', async () => {
      const first = g.showConfirm({ tone: 'danger', actions: KILL_ACTIONS })
      g.cancelConfirm()
      await first
      const second = g.showConfirm({ tone: 'warning', actions: KILL_ACTIONS })
      const card = document.querySelector('[data-confirm-card]')
      expect(card.classList.contains('modal-card-danger')).toBe(false)
      expect(card.classList.contains('modal-card-warning')).toBe(true)
      g.cancelConfirm()
      await second
    })
  })

  describe('button classes', () => {
    it('maps role:primary + tone:danger to btn-primary btn-danger', async () => {
      const promise = g.showConfirm({ actions: KILL_ACTIONS })
      const btn = document.querySelector('[data-confirm-action-id="confirm"]')
      expect(btn.className).toBe('btn btn-primary btn-danger')
      g.cancelConfirm()
      await promise
    })

    it('maps role:cancel to btn-secondary', async () => {
      const promise = g.showConfirm({ actions: KILL_ACTIONS })
      const btn = document.querySelector('[data-confirm-action-id="cancel"]')
      expect(btn.className).toBe('btn btn-secondary')
      expect(btn.dataset.confirmRole).toBe('cancel')
      g.cancelConfirm()
      await promise
    })

    it('maps role:secondary + tone:warning to btn-secondary btn-warning', async () => {
      const promise = g.showConfirm({
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'soft', label: 'Soft', role: 'secondary', tone: 'warning' },
          { id: 'hard', label: 'Hard', role: 'primary', tone: 'warning' },
        ],
      })
      const soft = document.querySelector('[data-confirm-action-id="soft"]')
      expect(soft.className).toBe('btn btn-secondary btn-warning')
      g.cancelConfirm()
      await promise
    })
  })

  describe('default focus', () => {
    it('focuses the role:cancel button by default', async () => {
      const promise = g.showConfirm({ actions: KILL_ACTIONS })
      expect(document.activeElement.dataset.confirmActionId).toBe('cancel')
      g.cancelConfirm()
      await promise
    })

    it('honors defaultFocus when no cancel action is present', async () => {
      const promise = g.showConfirm({
        actions: [
          { id: 'later', label: 'Later', role: 'secondary' },
          { id: 'now', label: 'Now', role: 'primary' },
        ],
        defaultFocus: 'now',
      })
      expect(document.activeElement.dataset.confirmActionId).toBe('now')
      g.cancelConfirm()
      await promise
    })

    it('falls back to the first button when no cancel and no defaultFocus', async () => {
      const promise = g.showConfirm({
        actions: [
          { id: 'a', label: 'A', role: 'primary' },
          { id: 'b', label: 'B', role: 'secondary' },
        ],
      })
      expect(document.activeElement.dataset.confirmActionId).toBe('a')
      g.cancelConfirm()
      await promise
    })
  })

  describe('stacking', () => {
    it('stacks when there are 3+ actions regardless of viewport', async () => {
      window.matchMedia = vi.fn(() => ({
        matches: false,
        addEventListener: () => {},
        removeEventListener: () => {},
      }))
      const promise = g.showConfirm({
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'soft', label: 'Soft', role: 'secondary' },
          { id: 'hard', label: 'Hard', role: 'primary', tone: 'danger' },
        ],
      })
      expect(
        document
          .querySelector('[data-confirm-actions]')
          .classList.contains('modal-actions-stacked'),
      ).toBe(true)
      g.cancelConfirm()
      await promise
    })

    it('stacks when the viewport is <=480px even with 2 actions', async () => {
      window.matchMedia = vi.fn((q) => ({
        matches: q.includes('480'),
        addEventListener: () => {},
        removeEventListener: () => {},
      }))
      const promise = g.showConfirm({ actions: KILL_ACTIONS })
      expect(
        document
          .querySelector('[data-confirm-actions]')
          .classList.contains('modal-actions-stacked'),
      ).toBe(true)
      g.cancelConfirm()
      await promise
    })

    it('does not stack for 2 actions on wide viewports', async () => {
      window.matchMedia = vi.fn(() => ({
        matches: false,
        addEventListener: () => {},
        removeEventListener: () => {},
      }))
      const promise = g.showConfirm({ actions: KILL_ACTIONS })
      expect(
        document
          .querySelector('[data-confirm-actions]')
          .classList.contains('modal-actions-stacked'),
      ).toBe(false)
      g.cancelConfirm()
      await promise
    })
  })
})
