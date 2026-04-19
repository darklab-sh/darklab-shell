import { test, expect } from '@playwright/test'

// Phase 6 of the UI Interaction Helper Refactor: assertions for the
// shared interaction contract exercised against real mounted UI rather
// than helper fixtures. Each phase ships its own per-helper unit suite
// (`ui_pressable.test.js`, `ui_disclosure.test.js`, `ui_dismissible.test.js`,
// `ui_outside_click.test.js`, `ui_focus_helpers.test.js`); this file
// checks that the contracts those helpers encode actually hold end-to-end
// on the surfaces that compose them.

const OVERLAYS = [
  { name: 'FAQ',       id: '#faq-overlay',       open: 'openFaq',            close: '.faq-close' },
  { name: 'theme',     id: '#theme-overlay',     open: 'openThemeSelector',  close: '.theme-close' },
  { name: 'options',   id: '#options-overlay',   open: 'openOptions',        close: '.options-close' },
  { name: 'workflows', id: '#workflows-overlay', open: 'openWorkflows',      close: '.workflows-close' },
  { name: 'shortcuts', id: '#shortcuts-overlay', open: 'openShortcuts',      close: '.shortcuts-close' },
]

async function openOverlay(page, openFn) {
  await page.locator('#cmd').focus()
  await page.evaluate((fn) => window[fn]?.(), openFn)
}

test.describe('UI interaction contract — scrim overlays', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  for (const overlay of OVERLAYS) {
    test(`${overlay.name} overlay closes via button, backdrop, and Escape — each path refocuses the composer`, async ({ page }) => {
      // Close via explicit close button.
      await openOverlay(page, overlay.open)
      await expect(page.locator(overlay.id)).toHaveClass(/\bopen\b/)
      await page.locator(overlay.close).click()
      await expect(page.locator(overlay.id)).not.toHaveClass(/\bopen\b/)
      await expect(page.locator('#cmd')).toBeFocused()

      // Close via backdrop click (overlay element itself, outside the modal content box).
      await openOverlay(page, overlay.open)
      await expect(page.locator(overlay.id)).toHaveClass(/\bopen\b/)
      await page.locator(overlay.id).click({ position: { x: 10, y: 10 } })
      await expect(page.locator(overlay.id)).not.toHaveClass(/\bopen\b/)
      await expect(page.locator('#cmd')).toBeFocused()

      // Close via Escape (routes through closeTopmostDismissible).
      await openOverlay(page, overlay.open)
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
    await page.locator('#cmd').waitFor()
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
    // Workflows section defaults to .closed in the template.
    const header = page.locator('#rail-workflows-header')
    const section = page.locator('#rail-section-workflows')

    await expect(section).toHaveClass(/\bclosed\b/)
    await expect(header).toHaveAttribute('aria-expanded', 'false')

    await header.click()
    await expect(section).not.toHaveClass(/\bclosed\b/)
    await expect(header).toHaveAttribute('aria-expanded', 'true')

    await header.click()
    await expect(section).toHaveClass(/\bclosed\b/)
    await expect(header).toHaveAttribute('aria-expanded', 'false')
  })

})

test.describe('UI interaction contract — ambient outside-click', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.locator('#cmd').waitFor()
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
