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
const UI_FOCUS_TRAP_SRC = readFileSync(resolve(REPO_ROOT, 'app/static/js/ui_focus_trap.js'), 'utf8')
const UI_CONFIRM_SRC = readFileSync(resolve(REPO_ROOT, 'app/static/js/ui_confirm.js'), 'utf8')

function mountHost() {
  document.body.innerHTML = `
    <div id="confirm-host" class="modal-overlay u-hidden">
      <div class="modal-card modal-card-compact" data-confirm-card>
        <div class="modal-copy" data-confirm-body></div>
        <div class="modal-confirm-content" data-confirm-content></div>
        <div class="modal-actions modal-actions-wrap" data-confirm-actions></div>
      </div>
    </div>
  `
}

function loadHelpers() {
  delete window.bindPressable
  delete window.bindDismissible
  delete window.bindFocusTrap
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
  new Function(UI_FOCUS_TRAP_SRC)()
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

  describe('content slot', () => {
    it('renders a single Node into the content slot', async () => {
      const input = document.createElement('input')
      input.type = 'text'
      input.id = 'session-token-set-input'
      const promise = g.showConfirm({ content: input, actions: KILL_ACTIONS })
      const slot = document.querySelector('[data-confirm-content]')
      expect(slot.children.length).toBe(1)
      expect(slot.querySelector('#session-token-set-input')).toBe(input)
      g.cancelConfirm()
      await promise
    })

    it('renders an array of Nodes into the content slot in order', async () => {
      const a = document.createElement('span')
      a.textContent = 'first'
      const b = document.createElement('span')
      b.textContent = 'second'
      const promise = g.showConfirm({ content: [a, b], actions: KILL_ACTIONS })
      const slot = document.querySelector('[data-confirm-content]')
      expect(slot.children.length).toBe(2)
      expect(slot.children[0].textContent).toBe('first')
      expect(slot.children[1].textContent).toBe('second')
      g.cancelConfirm()
      await promise
    })

    it('skips non-Node items in an array silently', async () => {
      const node = document.createElement('span')
      node.textContent = 'only me'
      const promise = g.showConfirm({
        content: [null, undefined, 'strings-are-ignored', node],
        actions: KILL_ACTIONS,
      })
      const slot = document.querySelector('[data-confirm-content]')
      expect(slot.children.length).toBe(1)
      expect(slot.children[0]).toBe(node)
      g.cancelConfirm()
      await promise
    })

    it('clears the content slot on resolve', async () => {
      const node = document.createElement('div')
      node.textContent = 'slot content'
      const promise = g.showConfirm({ content: node, actions: KILL_ACTIONS })
      const slot = document.querySelector('[data-confirm-content]')
      expect(slot.children.length).toBe(1)
      g.cancelConfirm()
      await promise
      expect(slot.children.length).toBe(0)
      expect(slot.innerHTML).toBe('')
    })

    it('clears stale content between opens', async () => {
      const first = document.createElement('span')
      first.textContent = 'first open'
      const p1 = g.showConfirm({ content: first, actions: KILL_ACTIONS })
      g.cancelConfirm()
      await p1
      const p2 = g.showConfirm({ actions: KILL_ACTIONS })
      const slot = document.querySelector('[data-confirm-content]')
      expect(slot.innerHTML).toBe('')
      g.cancelConfirm()
      await p2
    })
  })

  describe('onActivate gating', () => {
    it('keeps the modal open when onActivate returns false (sync)', async () => {
      const onActivate = vi.fn(() => false)
      const promise = g.showConfirm({
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'apply', label: 'Apply', role: 'primary', onActivate },
        ],
      })
      document.querySelector('[data-confirm-action-id="apply"]').click()
      // Flush microtasks so the click handler's await resolves.
      await Promise.resolve()
      await Promise.resolve()
      expect(onActivate).toHaveBeenCalledTimes(1)
      expect(g.isConfirmOpen()).toBe(true)
      // Cleanup: dismiss so later tests start clean.
      g.cancelConfirm()
      await expect(promise).resolves.toBeNull()
    })

    it('closes and resolves when onActivate returns true', async () => {
      const onActivate = vi.fn(() => true)
      const promise = g.showConfirm({
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'apply', label: 'Apply', role: 'primary', onActivate },
        ],
      })
      document.querySelector('[data-confirm-action-id="apply"]').click()
      await expect(promise).resolves.toBe('apply')
      expect(onActivate).toHaveBeenCalledTimes(1)
      expect(g.isConfirmOpen()).toBe(false)
    })

    it('keeps the modal open while an async onActivate is pending', async () => {
      let resolveGate
      const onActivate = vi.fn(
        () => new Promise((r) => { resolveGate = r }),
      )
      const promise = g.showConfirm({
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'apply', label: 'Apply', role: 'primary', onActivate },
        ],
      })
      document.querySelector('[data-confirm-action-id="apply"]').click()
      await Promise.resolve()
      await Promise.resolve()
      expect(onActivate).toHaveBeenCalledTimes(1)
      expect(g.isConfirmOpen()).toBe(true)
      resolveGate(false)
      // Resolved to false — modal should remain open after the microtask flush.
      await Promise.resolve()
      await Promise.resolve()
      expect(g.isConfirmOpen()).toBe(true)
      g.cancelConfirm()
      await expect(promise).resolves.toBeNull()
    })

    it('closes and resolves when an async onActivate resolves truthy', async () => {
      const onActivate = vi.fn(() => Promise.resolve('ok'))
      const promise = g.showConfirm({
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'apply', label: 'Apply', role: 'primary', onActivate },
        ],
      })
      document.querySelector('[data-confirm-action-id="apply"]').click()
      await expect(promise).resolves.toBe('apply')
      expect(g.isConfirmOpen()).toBe(false)
    })

    it('keeps the modal open when onActivate throws synchronously', async () => {
      const onActivate = vi.fn(() => { throw new Error('boom') })
      const promise = g.showConfirm({
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'apply', label: 'Apply', role: 'primary', onActivate },
        ],
      })
      document.querySelector('[data-confirm-action-id="apply"]').click()
      await Promise.resolve()
      await Promise.resolve()
      expect(onActivate).toHaveBeenCalledTimes(1)
      expect(g.isConfirmOpen()).toBe(true)
      g.cancelConfirm()
      await expect(promise).resolves.toBeNull()
    })

    it('keeps the modal open when an async onActivate rejects', async () => {
      const onActivate = vi.fn(() => Promise.reject(new Error('fail')))
      const promise = g.showConfirm({
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'apply', label: 'Apply', role: 'primary', onActivate },
        ],
      })
      document.querySelector('[data-confirm-action-id="apply"]').click()
      await Promise.resolve()
      await Promise.resolve()
      await Promise.resolve()
      expect(g.isConfirmOpen()).toBe(true)
      g.cancelConfirm()
      await expect(promise).resolves.toBeNull()
    })
  })

  describe('defaultFocus Node', () => {
    it('focuses an explicit Node passed as defaultFocus, overriding role:cancel', async () => {
      const input = document.createElement('input')
      input.type = 'text'
      input.id = 'focus-target-input'
      // jsdom only allows focus on elements actually attached to the
      // document, which happens when the primitive appends content.
      const promise = g.showConfirm({
        content: input,
        defaultFocus: input,
        actions: KILL_ACTIONS,
      })
      expect(document.activeElement).toBe(input)
      g.cancelConfirm()
      await promise
    })
  })

  describe('focus trap', () => {
    it('wraps Tab from the last action back to the first', async () => {
      const promise = g.showConfirm({ actions: KILL_ACTIONS })
      const card = document.querySelector('[data-confirm-card]')
      const cancelBtn = card.querySelector('[data-confirm-action-id="cancel"]')
      const confirmBtn = card.querySelector('[data-confirm-action-id="confirm"]')
      confirmBtn.focus()
      expect(document.activeElement).toBe(confirmBtn)
      const ev = new KeyboardEvent('keydown', { key: 'Tab', bubbles: true, cancelable: true })
      card.dispatchEvent(ev)
      expect(ev.defaultPrevented).toBe(true)
      expect(document.activeElement).toBe(cancelBtn)
      g.cancelConfirm()
      await promise
    })

    it('wraps Shift+Tab from the first action back to the last', async () => {
      const promise = g.showConfirm({ actions: KILL_ACTIONS })
      const card = document.querySelector('[data-confirm-card]')
      const cancelBtn = card.querySelector('[data-confirm-action-id="cancel"]')
      const confirmBtn = card.querySelector('[data-confirm-action-id="confirm"]')
      cancelBtn.focus()
      expect(document.activeElement).toBe(cancelBtn)
      const ev = new KeyboardEvent('keydown', {
        key: 'Tab',
        shiftKey: true,
        bubbles: true,
        cancelable: true,
      })
      card.dispatchEvent(ev)
      expect(ev.defaultPrevented).toBe(true)
      expect(document.activeElement).toBe(confirmBtn)
      g.cancelConfirm()
      await promise
    })

    it('cycles confirm actions with ArrowRight/ArrowDown and ArrowLeft/ArrowUp', async () => {
      const promise = g.showConfirm({ actions: KILL_ACTIONS })
      const card = document.querySelector('[data-confirm-card]')
      const cancelBtn = card.querySelector('[data-confirm-action-id="cancel"]')
      const confirmBtn = card.querySelector('[data-confirm-action-id="confirm"]')

      cancelBtn.focus()
      const right = new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true, cancelable: true })
      card.dispatchEvent(right)
      expect(right.defaultPrevented).toBe(true)
      expect(document.activeElement).toBe(confirmBtn)

      const down = new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true, cancelable: true })
      card.dispatchEvent(down)
      expect(down.defaultPrevented).toBe(true)
      expect(document.activeElement).toBe(cancelBtn)

      const left = new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true, cancelable: true })
      card.dispatchEvent(left)
      expect(left.defaultPrevented).toBe(true)
      expect(document.activeElement).toBe(confirmBtn)

      const up = new KeyboardEvent('keydown', { key: 'ArrowUp', bubbles: true, cancelable: true })
      card.dispatchEvent(up)
      expect(up.defaultPrevented).toBe(true)
      expect(document.activeElement).toBe(cancelBtn)

      g.cancelConfirm()
      await promise
    })
  })
})
