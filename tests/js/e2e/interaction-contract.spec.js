import { test, expect } from '@playwright/test'
import { ensurePromptReady } from './helpers.js'

// Assertions for the shared interaction contract exercised against real
// mounted UI rather than helper fixtures. Each helper has its own unit
// suite (`ui_pressable.test.js`, `ui_disclosure.test.js`,
// `ui_dismissible.test.js`, `ui_outside_click.test.js`,
// `ui_focus_helpers.test.js`); this file checks that the contracts those
// helpers encode actually hold end-to-end on the surfaces that compose them.

const OVERLAYS = [
  { name: 'FAQ',       id: '#faq-overlay',       open: 'openFaq',            close: '.faq-close' },
  { name: 'theme',     id: '#theme-overlay',     open: 'openThemeSelector',  close: '.theme-close' },
  { name: 'options',   id: '#options-overlay',   open: 'openOptions',        close: '.options-close' },
  { name: 'workflows', id: '#workflows-overlay', open: 'openWorkflows',      close: '.workflows-close' },
  { name: 'shortcuts', id: '#shortcuts-overlay', open: 'openShortcuts',      close: '.shortcuts-close' },
]

async function openOverlay(page, openFn, overlayId = null) {
  await page.locator('#cmd').focus()
  await page.waitForFunction((fn) => typeof window[fn] === 'function', openFn)
  await page.evaluate((fn) => window[fn](), openFn)
  if (overlayId) {
    await expect(page.locator(overlayId)).toHaveAttribute('data-interaction-ready', '1')
  }
}

test.describe('UI interaction contract — scrim overlays', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await ensurePromptReady(page)
  })

  for (const overlay of OVERLAYS) {
    test(`${overlay.name} overlay closes via button, backdrop, and Escape — each path refocuses the composer`, async ({ page }) => {
      // Close via explicit close button.
      await openOverlay(page, overlay.open, overlay.id)
      await expect(page.locator(overlay.id)).toHaveClass(/\bopen\b/)
      await page.locator(overlay.close).click()
      await expect(page.locator(overlay.id)).not.toHaveClass(/\bopen\b/)
      await expect(page.locator('#cmd')).toBeFocused()

      // Close via backdrop click (overlay element itself, outside the modal content box).
      await openOverlay(page, overlay.open, overlay.id)
      await expect(page.locator(overlay.id)).toHaveClass(/\bopen\b/)
      await page.locator(overlay.id).click({ position: { x: 10, y: 10 } })
      await expect(page.locator(overlay.id)).not.toHaveClass(/\bopen\b/)
      await expect(page.locator('#cmd')).toBeFocused()

      // Close via Escape (routes through closeTopmostDismissible).
      await openOverlay(page, overlay.open, overlay.id)
      await expect(page.locator(overlay.id)).toHaveClass(/\bopen\b/)
      await page.keyboard.press('Escape')
      await expect(page.locator(overlay.id)).not.toHaveClass(/\bopen\b/)
      await expect(page.locator('#cmd')).toBeFocused()
    })
  }
})

test.describe('UI interaction contract — disclosures', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await ensurePromptReady(page)
  })

  test('FAQ question disclosure keeps aria-expanded in sync with the .faq-open class', async ({ page }) => {
    await page.locator('.rail-nav [data-action="faq"]').click()
    await expect(page.locator('#faq-overlay')).toHaveClass(/\bopen\b/)

    // Scope to the FAQ modal — the share-redaction modal reuses the
    // `.faq-item` class name for one inline form field, so a bare
    // `.faq-item` selector would match that ahead of the real FAQ items.
    const firstQ = page.locator('#faq-overlay .faq-body .faq-q').first()
    const firstItem = page.locator('#faq-overlay .faq-body .faq-item').first()

    // First FAQ item is opened by default (faqHandles[0].open() after render).
    await expect(firstQ).toHaveAttribute('aria-expanded', 'true')
    await expect(firstItem).toHaveClass(/\bfaq-open\b/)

    // Collapse → aria-expanded and class both flip.
    await firstQ.click()
    await expect(firstQ).toHaveAttribute('aria-expanded', 'false')
    await expect(firstItem).not.toHaveClass(/\bfaq-open\b/)

    // Re-expand → both flip back together.
    await firstQ.click()
    await expect(firstQ).toHaveAttribute('aria-expanded', 'true')
    await expect(firstItem).toHaveClass(/\bfaq-open\b/)
  })

  test('desktop rail section header disclosure keeps aria-expanded in sync with the .closed class (panel: null caller-owns-visibility)', async ({ page }) => {
    // Workflows section defaults to expanded in the template.
    const header = page.locator('#rail-workflows-header')
    const section = page.locator('#rail-section-workflows')

    await expect(section).not.toHaveClass(/\bclosed\b/)
    await expect(header).toHaveAttribute('aria-expanded', 'true')

    await header.click()
    await expect(section).toHaveClass(/\bclosed\b/)
    await expect(header).toHaveAttribute('aria-expanded', 'false')

    await header.click()
    await expect(section).not.toHaveClass(/\bclosed\b/)
    await expect(header).toHaveAttribute('aria-expanded', 'true')
  })

})

test.describe('UI interaction contract — modal focus trap', () => {
  const MODALS = [
    { name: 'FAQ',       overlay: '#faq-overlay',       modal: '#faq-modal',       open: 'openFaq' },
    { name: 'theme',     overlay: '#theme-overlay',     modal: '#theme-modal',     open: 'openThemeSelector' },
    { name: 'options',   overlay: '#options-overlay',   modal: '#options-modal',   open: 'openOptions' },
    { name: 'workflows', overlay: '#workflows-overlay', modal: '#workflows-modal', open: 'openWorkflows' },
  ]

  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await ensurePromptReady(page)
  })

  test('each app-level modal card carries data-focus-trap-bound after startup wiring', async ({ page }) => {
    for (const modal of MODALS) {
      await expect(page.locator(modal.modal)).toHaveAttribute('data-focus-trap-bound', '1')
    }
  })

  for (const modal of MODALS) {
    test(`${modal.name} modal wraps Tab and Shift+Tab at its card boundary`, async ({ page }) => {
      await openOverlay(page, modal.open, modal.overlay)
      await expect(page.locator(modal.overlay)).toHaveClass(/\bopen\b/)

      // Content for FAQ and workflows loads async from /faq and /workflows
      // — wait for the card to have at least two focusable descendants
      // before running the boundary test so the test is independent of
      // network timing. Visibility filter mirrors ui_focus_trap.js so the
      // test and the trap agree on which element is "last": hidden
      // attribute, [hidden] ancestor, and display:none (via client-rect).
      await expect
        .poll(async () => {
          return page.evaluate((selector) => {
            const card = document.querySelector(selector)
            if (!card) return 0
            const SEL = 'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
            return Array.from(card.querySelectorAll(SEL))
              .filter((el) => !el.hidden
                && !(typeof el.closest === 'function' && el.closest('[hidden]'))
                && window.getComputedStyle(el).display !== 'none')
              .length
          }, modal.modal)
        })
        .toBeGreaterThanOrEqual(2)

      await page.evaluate((selector) => {
        const card = document.querySelector(selector)
        const SEL = 'button:not([disabled]), a[href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        const list = Array.from(card.querySelectorAll(SEL))
          .filter((el) => !el.hidden
            && !(typeof el.closest === 'function' && el.closest('[hidden]'))
            && window.getComputedStyle(el).display !== 'none')
        card.querySelectorAll('[data-focustest-first], [data-focustest-last]').forEach((el) => {
          delete el.dataset.focustestFirst
          delete el.dataset.focustestLast
        })
        const first = list[0]
        const last = list[list.length - 1]
        first.dataset.focustestFirst = '1'
        last.dataset.focustestLast = '1'
      }, modal.modal)

      const first = page.locator(`${modal.modal} [data-focustest-first="1"]`)
      const last = page.locator(`${modal.modal} [data-focustest-last="1"]`)

      await last.focus()
      await expect(last).toBeFocused()
      await page.keyboard.press('Tab')
      await expect(first).toBeFocused()

      await first.focus()
      await expect(first).toBeFocused()
      await page.keyboard.press('Shift+Tab')
      await expect(last).toBeFocused()
    })
  }
})

test.describe('UI interaction contract — confirmation dialog', () => {
  // Integration coverage for the Confirmation Dialog Contract documented in
  // ARCHITECTURE § Frontend Design System. The per-helper unit suite in
  // ui_confirm.test.js already covers every rule against a stubbed host; the
  // cases below re-exercise the same rules against the *real* mounted
  // #confirm-host so the wiring (showModalOverlay, refocusComposerAfterAction,
  // the real closeTopmostDismissible, the real matchMedia) is also pinned.
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await ensurePromptReady(page)
  })

  test('showConfirm focuses the role:cancel action by default so Enter defaults to cancel', async ({ page }) => {
    await page.evaluate(() => {
      window.__confirmPromise = window.showConfirm({
        body: 'Continue?',
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'confirm', label: 'Continue', role: 'primary' },
        ],
      })
    })
    await page.locator('#confirm-host').waitFor({ state: 'visible' })
    await expect(page.locator('#confirm-host [data-confirm-action-id="cancel"]')).toBeFocused()

    // Clean up — resolve the promise so later cases start fresh.
    await page.keyboard.press('Escape')
    await expect(page.locator('#confirm-host')).toBeHidden()
  })

  test('Escape dismisses the dialog and resolves with null via closeTopmostDismissible', async ({ page }) => {
    await page.evaluate(() => {
      window.__confirmResult = 'PENDING'
      window.showConfirm({
        body: 'Continue?',
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'confirm', label: 'Continue', role: 'primary' },
        ],
      }).then((value) => { window.__confirmResult = value })
    })
    await page.locator('#confirm-host').waitFor({ state: 'visible' })

    await page.keyboard.press('Escape')

    await expect(page.locator('#confirm-host')).toBeHidden()
    // The promise resolves on the next microtask — poll briefly so the
    // assertion is independent of scheduling.
    await expect.poll(() => page.evaluate(() => window.__confirmResult)).toBeNull()
  })

  test('stacks actions when the viewport narrows to <=480px', async ({ page }) => {
    // The reactive matchMedia listener keeps stacking in sync with viewport
    // changes while the modal is open; resize *after* the open call so the
    // listener path is also exercised (not just the initial apply).
    await page.setViewportSize({ width: 1024, height: 768 })
    await page.evaluate(() => {
      window.showConfirm({
        body: 'Continue?',
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'confirm', label: 'Continue', role: 'primary' },
        ],
      })
    })
    await page.locator('#confirm-host').waitFor({ state: 'visible' })

    const actions = page.locator('#confirm-host [data-confirm-actions]')
    await expect(actions).not.toHaveClass(/\bmodal-actions-stacked\b/)

    await page.setViewportSize({ width: 390, height: 844 })
    await expect(actions).toHaveClass(/\bmodal-actions-stacked\b/)

    // Clean up.
    await page.keyboard.press('Escape')
    await expect(page.locator('#confirm-host')).toBeHidden()
  })

  test('stacks actions when there are 3 or more actions regardless of viewport', async ({ page }) => {
    await page.setViewportSize({ width: 1024, height: 768 })
    await page.evaluate(() => {
      window.showConfirm({
        body: 'Pick a branch.',
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          { id: 'skip', label: 'Skip', role: 'secondary' },
          { id: 'confirm', label: 'Continue', role: 'primary' },
        ],
      })
    })
    await page.locator('#confirm-host').waitFor({ state: 'visible' })

    const actions = page.locator('#confirm-host [data-confirm-actions]')
    await expect(actions).toHaveClass(/\bmodal-actions-stacked\b/)

    // Clean up.
    await page.keyboard.press('Escape')
    await expect(page.locator('#confirm-host')).toBeHidden()
  })

  test('onActivate keeps the dialog open when the callback returns false', async ({ page }) => {
    await page.evaluate(() => {
      window.__onActivateCount = 0
      window.showConfirm({
        body: 'Confirm with gated validation.',
        actions: [
          { id: 'cancel', label: 'Cancel', role: 'cancel' },
          {
            id: 'confirm',
            label: 'Continue',
            role: 'primary',
            onActivate: () => { window.__onActivateCount += 1; return false },
          },
        ],
      })
    })
    await page.locator('#confirm-host').waitFor({ state: 'visible' })

    const confirmBtn = page.locator('#confirm-host [data-confirm-action-id="confirm"]')
    await confirmBtn.click()
    await confirmBtn.click()

    // Modal still visible and the onActivate callback ran twice — the
    // primitive respects the gate and does not close on a falsy return.
    await expect(page.locator('#confirm-host')).toBeVisible()
    expect(await page.evaluate(() => window.__onActivateCount)).toBe(2)

    // Clean up.
    await page.keyboard.press('Escape')
    await expect(page.locator('#confirm-host')).toBeHidden()
  })
})

test.describe('UI interaction contract — ambient outside-click', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await ensurePromptReady(page)
    // HUD save-menu lives on the active tab panel; make sure a tab is ready.
    await expect(page.locator('.tab-panel.active')).toBeVisible()
  })

  test('HUD save-menu: trigger toggles, inside-panel click stays open, outside click closes', async ({ page }) => {
    const wrap = page.locator('.hud-save-wrap').first()
    const trigger = wrap.locator('[data-action="save-menu"]')

    // Closed at rest.
    await expect(wrap).not.toHaveClass(/\bopen\b/)

    // Trigger click opens.
    await trigger.click()
    await expect(wrap).toHaveClass(/\bopen\b/)

    // Inside-panel click (on the .save-menu container itself, not on an action
    // button) must NOT close — the bindOutsideClickClose helper treats clicks
    // inside the panel as "inside" via .contains().
    await page.evaluate(() => {
      const menu = document.querySelector('.hud-save-wrap.open .save-menu')
      menu?.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await expect(wrap).toHaveClass(/\bopen\b/)

    // Trigger click again toggles closed — exercises the trigger-exemption
    // contract: the trigger is registered in `triggers` so the handler
    // treats the click as "inside the surface", and the disclosure's own
    // toggle handler flips the .open class off.
    await trigger.click()
    await expect(wrap).not.toHaveClass(/\bopen\b/)

    // Reopen, then click clearly outside — dispatch at document.body so the
    // click is unambiguously outside both the panel and the trigger and
    // does not depend on any particular element being in the viewport.
    await trigger.click()
    await expect(wrap).toHaveClass(/\bopen\b/)
    await page.evaluate(() => {
      document.body.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    })
    await expect(wrap).not.toHaveClass(/\bopen\b/)
  })
})
