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
})
