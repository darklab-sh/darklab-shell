// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { test, expect } from '@playwright/test'
import { ensurePromptReady, openRailAction } from './helpers.js'

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

    await openRailAction(page, 'theme')
    await expect(page.locator('#theme-overlay')).toHaveClass(/open/)
    await expect(page.locator('#theme-select .theme-card-active')).toBeVisible()
    await page.locator('.theme-close').click()

    await page.locator('#search-toggle-btn').click()
    await expect(page.locator('#search-bar')).toBeVisible()

    await openRailAction(page, 'faq')
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

for (const width of [1280, 390]) {
  test.describe(`theme previews at width ${width}`, () => {
    test.use({ viewport: { width, height: 900 }, isMobile: width < 600, hasTouch: width < 600 })
    test(`theme previews load on demand and recover from failure at width ${width}`, async ({ page }) => {
      let attempts = 0
      let release
      const pending = new Promise(resolve => { release = resolve })
      await page.route('**/themes', async route => {
        attempts += 1
        if (attempts === 1) {
          await pending
          await route.fulfill({ status: 503, contentType: 'application/json', body: '{}' })
        } else await route.continue()
      })
      await page.goto('/')
      await ensurePromptReady(page)
      const initial = await page.locator('body').getAttribute('data-theme')
      expect(attempts).toBe(0)
      if (width < 600) {
        await page.locator('#hamburger-btn').click()
        await page.locator('#mobile-menu-sheet [data-menu-action="theme"]').click()
      } else await openRailAction(page, 'theme')
      await expect(page.getByRole('status').filter({ hasText: 'Loading themes' })).toBeVisible()
      await expect(page.locator('body')).toHaveAttribute('data-theme', initial)
      release()
      await page.getByRole('button', { name: 'Retry loading themes' }).click()
      await expect(page.locator('#theme-select .theme-card-active')).toBeVisible()
      await page.locator('#theme-select .theme-card:not(.theme-card-active)').first().click()
      await expect(page.locator('body')).not.toHaveAttribute('data-theme', initial)
      expect(attempts).toBe(2)
    })
  })
}

for (const width of [1280, 390]) {
  test.describe(`startup ordering at width ${width}`, () => {
    test.use({ viewport: { width, height: 900 }, isMobile: width < 600, hasTouch: width < 600 })
    test('preferences guard the first tab while failed recall preserves typed input', async ({ page }) => {
      let releasePreferences, releaseHistory
      let preferencesRequested = false, historyRequested = false
      const preferences = new Promise(resolve => { releasePreferences = resolve })
      const history = new Promise(resolve => { releaseHistory = resolve })
      await page.route('**/session/preferences', async route => {
        if (route.request().method() !== 'GET') return route.continue()
        preferencesRequested = true
        await preferences
        await route.continue()
      })
      await page.route('**/history/commands?*', async route => {
        historyRequested = true
        await history
        await route.fulfill({ status: 503, contentType: 'application/json', body: '{}' })
      })
      try {
        await page.goto('/', { waitUntil: 'domcontentloaded' })
        await expect.poll(() => preferencesRequested && historyRequested).toBe(true)
        expect(await page.evaluate(() => window.APP_STATE_API?.getActiveTab?.())).toBeFalsy()
        // An explicit panel open can load its catalog before preferences finish.
        if (width < 600) {
          await page.locator('#hamburger-btn').click()
          await page.locator('#mobile-menu-sheet [data-menu-action="faq"]').click()
        } else await openRailAction(page, 'faq')
        await expect(page.locator('#faq-overlay .faq-body')).toContainText('Getting started')
        if (width < 600) await page.locator('#faq-overlay').click({ position: { x: 5, y: 5 } })
        else await page.locator('.faq-close').click()
        await expect(page.locator('#faq-overlay')).not.toHaveClass(/open/)
        releasePreferences()
        await ensurePromptReady(page)
        const input = page.locator(width < 600 ? '#mobile-cmd' : '#cmd')
        await input.fill('unfinished command')
        const completed = page.waitForResponse('**/history/commands?*')
        releaseHistory()
        await completed
        await expect(input).toHaveValue('unfinished command')
      } finally {
        releasePreferences()
        releaseHistory()
      }
    })
  })
}
