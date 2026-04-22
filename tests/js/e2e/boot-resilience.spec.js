import { test, expect } from '@playwright/test'

test.describe('boot resilience', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/allowed-commands', (route) => route.abort('failed'))
    await page.route('**/faq', (route) => route.abort('failed'))
    await page.route('**/autocomplete', (route) => route.abort('failed'))

    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('the app still boots and core controls still work when startup fetches fail', async ({
    page,
  }) => {
    await expect(page.locator('.rail-wordmark-title')).toHaveText(/darklab_shell/)

    await page.locator('.rail-nav [data-action="theme"]').click()
    await expect(page.locator('#theme-overlay')).toHaveClass(/open/)
    await expect(page.locator('#theme-select .theme-card-active')).toBeFocused()
    await page.locator('.theme-close').click()

    await page.locator('#search-toggle-btn').click()
    await expect(page.locator('#search-bar')).toBeVisible()

    await page.locator('.rail-nav [data-action="faq"]').click()
    await expect(page.locator('#faq-overlay')).toHaveClass(/open/)
  })

  test('the shell does not request external font assets on load', async ({ page }) => {
    const externalFonts = []
    page.on('request', (request) => {
      const url = request.url()
      if (url.includes('fonts.googleapis.com') || url.includes('fonts.gstatic.com')) {
        externalFonts.push(url)
      }
    })

    await page.goto('/')
    await page.locator('#cmd').waitFor()

    expect(externalFonts).toEqual([])
  })
})
