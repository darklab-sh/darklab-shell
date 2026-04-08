import { test, expect } from '@playwright/test'

test.describe('theme toggle', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('clicking theme-btn switches to light mode', async ({ page }) => {
    // Start in dark mode (no "light" class)
    await expect(page.locator('body')).not.toHaveClass(/\blight\b/)

    await page.locator('#theme-btn').click()
    await expect(page.locator('body')).toHaveClass(/\blight\b/)
  })

  test('clicking theme-btn twice returns to dark mode', async ({ page }) => {
    await page.locator('#theme-btn').click()
    await expect(page.locator('body')).toHaveClass(/\blight\b/)

    await page.locator('#theme-btn').click()
    await expect(page.locator('body')).not.toHaveClass(/\blight\b/)
  })
})

test.describe('FAQ modal', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/allowed-commands', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          restricted: true,
          commands: ['ping', 'traceroute'],
          groups: [
            {
              name: 'Networking',
              commands: ['ping', 'traceroute'],
            },
          ],
        }),
      })
    })
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('FAQ button opens the overlay', async ({ page }) => {
    await expect(page.locator('#faq-overlay')).not.toHaveClass(/open/)
    await page.locator('#faq-btn').click()
    await expect(page.locator('#faq-overlay')).toHaveClass(/open/)
  })

  test('close button inside the FAQ modal closes it', async ({ page }) => {
    await page.locator('#faq-btn').click()
    await expect(page.locator('#faq-overlay')).toHaveClass(/open/)

    await page.locator('.faq-close').click()
    await expect(page.locator('#faq-overlay')).not.toHaveClass(/open/)
  })

  test('clicking the overlay backdrop closes the FAQ modal', async ({ page }) => {
    await page.locator('#faq-btn').click()
    await expect(page.locator('#faq-overlay')).toHaveClass(/open/)

    // Click on the overlay element itself (outside the modal content box)
    await page.locator('#faq-overlay').click({ position: { x: 10, y: 10 } })
    await expect(page.locator('#faq-overlay')).not.toHaveClass(/open/)
  })

  test('renders backend-driven FAQ content and allowlist chips', async ({ page }) => {
    await page.locator('#faq-btn').click()
    await expect(page.locator('#faq-overlay')).toHaveClass(/open/)

    await expect(page.locator('.faq-q')).toContainText(['What is this?', 'What commands are allowed?'])
    await expect(page.locator('.faq-a').filter({ hasText: 'README on GitLab' }).first()).toBeVisible()
    await expect(page.locator('#faq-allowed-text')).toBeVisible()
  })
})

test.describe('options modal', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('persists theme, timestamps, and line number preferences across reload', async ({ page }) => {
    await page.locator('#options-btn').click()
    await expect(page.locator('#options-overlay')).toHaveClass(/open/)

    await page.locator('input[name="theme-pref"][value="light"]').check()
    await page.locator('#options-ts-select').selectOption('elapsed')
    await page.locator('#options-ln-toggle').check()
    await page.locator('.options-close').click()

    await expect(page.locator('body')).toHaveClass(/\blight\b/)
    await expect(page.locator('#ts-btn')).toHaveText('timestamps: elapsed')
    await expect(page.locator('#ln-btn')).toHaveText('line numbers: on')

    await page.reload()
    await page.locator('#cmd').waitFor()

    await expect(page.locator('body')).toHaveClass(/\blight\b/)
    await expect(page.locator('#ts-btn')).toHaveText('timestamps: elapsed')
    await expect(page.locator('#ln-btn')).toHaveText('line numbers: on')
  })
})
