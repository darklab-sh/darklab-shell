import { test, expect } from '@playwright/test'

test.describe('boot resilience', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/allowed-commands', route => route.abort('failed'))
    await page.route('**/faq', route => route.abort('failed'))
    await page.route('**/autocomplete', route => route.abort('failed'))

    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('the app still boots and core controls still work when startup fetches fail', async ({ page }) => {
    await expect(page.locator('header h1')).toHaveText(/shell\.darklab\.sh/)

    await page.locator('#theme-btn').click()
    await expect(page.locator('body')).toHaveClass(/\blight\b/)

    await page.locator('#search-toggle-btn').click()
    await expect(page.locator('#search-bar')).toBeVisible()

    await page.locator('#faq-btn').click()
    await expect(page.locator('#faq-overlay')).toHaveClass(/open/)
  })
})
