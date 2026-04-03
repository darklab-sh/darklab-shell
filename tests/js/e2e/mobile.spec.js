import { test, expect } from '@playwright/test'

const MOBILE = { width: 375, height: 812 }

test.describe('mobile menu', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize(MOBILE)
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('hamburger button is visible and desktop header buttons are hidden at mobile width', async ({ page }) => {
    await expect(page.locator('#hamburger-btn')).toBeVisible()
    await expect(page.locator('#header-btns')).toBeHidden()
  })

  test('clicking the hamburger opens the mobile menu', async ({ page }) => {
    await page.locator('#hamburger-btn').click()
    await expect(page.locator('#mobile-menu')).toHaveClass(/open/)
  })

  test('mobile menu contains history and theme action buttons', async ({ page }) => {
    await page.locator('#hamburger-btn').click()
    const menu = page.locator('#mobile-menu')
    await expect(menu.locator('[data-action="history"]')).toBeVisible()
    await expect(menu.locator('[data-action="theme"]')).toBeVisible()
  })

  test('clicking outside the menu closes it', async ({ page }) => {
    await page.locator('#hamburger-btn').click()
    await expect(page.locator('#mobile-menu')).toHaveClass(/open/)

    // Click somewhere neutral — the command input area
    await page.locator('#cmd').click()
    await expect(page.locator('#mobile-menu')).not.toHaveClass(/open/)
  })
})
