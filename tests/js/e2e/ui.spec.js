import { test, expect } from '@playwright/test'

test.describe('theme selector', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('clicking theme-btn opens the theme selector', async ({ page }) => {
    await page.locator('#theme-btn').click()
    await expect(page.locator('#theme-overlay')).toHaveClass(/open/)
    await expect(page.locator('#theme-select .theme-card-active')).toBeFocused()
  })

  test('selecting a theme applies it from the selector', async ({ page }) => {
    await page.locator('#theme-btn').click()
    const optionLabels = await page.locator('#theme-select .theme-card-label').evaluateAll(labels => labels.map(label => label.textContent))
    expect(optionLabels).toContain('Darklab Obsidian')
    expect(optionLabels).toContain('Charcoal Steel')
    const groupLabels = await page.locator('#theme-select .theme-picker-group-title').evaluateAll(labels => labels.map(label => label.textContent))
    expect(groupLabels).toEqual(['Dark Neon', 'Dark Neutral', 'Warm Light', 'Cool Light', 'Neutral Light'])
    await page.locator('#theme-select [data-theme-name="charcoal_steel"]').click()
    await expect(page.locator('body')).toHaveAttribute('data-theme', 'charcoal_steel')

    await page.locator('#theme-select [data-theme-name="cobalt_obsidian"]').click()
    await expect(page.locator('body')).toHaveAttribute('data-theme', 'cobalt_obsidian')
  })

  test('falls back to the configured default theme when localStorage references a missing theme', async ({ page }) => {
    await page.evaluate(() => {
      localStorage.setItem('theme', 'theme_missing.yaml')
    })

    await page.reload()
    await page.locator('#cmd').waitFor()

    await expect(page.locator('body')).toHaveAttribute('data-theme', 'darklab_obsidian')
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
    await expect(page.locator('.faq-a a[href*="darklab-shell#darklab-shell"]').first()).toBeVisible()
    await expect(page.locator('#faq-allowed-text')).toBeVisible()
  })
})

test.describe('options modal', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('persists theme, timestamps, and line number preferences across reload', async ({ page }) => {
    await page.locator('#theme-btn').click()
    await expect(page.locator('#theme-overlay')).toHaveClass(/open/)
    await page.locator('#theme-select [data-theme-name="blue_paper"]').click()
    await page.locator('.theme-close').click()

    await page.locator('#options-btn').click()
    await expect(page.locator('#options-overlay')).toHaveClass(/open/)
    await page.locator('#options-ts-select').selectOption('elapsed')
    await page.locator('#options-ln-toggle').check()
    await page.locator('.options-close').click()

    await expect(page.locator('body')).toHaveAttribute('data-theme', 'blue_paper')
    await expect(page.locator('#ts-btn')).toHaveText('timestamps: elapsed')
    await expect(page.locator('#ln-btn')).toHaveText('line numbers: on')

    await page.reload()
    await page.locator('#cmd').waitFor()

    await expect(page.locator('body')).toHaveAttribute('data-theme', 'blue_paper')
    await expect(page.locator('#ts-btn')).toHaveText('timestamps: elapsed')
    await expect(page.locator('#ln-btn')).toHaveText('line numbers: on')
  })
})
