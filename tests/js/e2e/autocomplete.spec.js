import { test, expect } from '@playwright/test'

test.describe('autocomplete', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('Tab expands to the shared prefix and Enter accepts a reselected suggestion', async ({ page }) => {
    const input = page.locator('#cmd')
    await input.fill('nmap')

    const dropdown = page.locator('#ac-dropdown')
    await expect(dropdown).toBeVisible()
    await expect(dropdown).toContainText('nmap -h')
    await expect(dropdown).not.toContainText('man nmap')

    await page.keyboard.press('ArrowDown')
    await expect(dropdown.locator('.ac-item.ac-active').first()).toContainText('nmap -h')

    await page.keyboard.press('Tab')
    await expect(input).toHaveValue('nmap -')
    await expect(dropdown).toBeVisible()

    await page.keyboard.press('ArrowDown')
    await expect(dropdown.locator('.ac-item.ac-active').first()).toContainText('nmap -h')

    await page.keyboard.press('Enter')
    await expect(input).toHaveValue('nmap -h')
    await expect(dropdown).toBeHidden()
  })

  test('clicking outside the prompt hides autocomplete without changing the input', async ({ page }) => {
    const input = page.locator('#cmd')
    await input.fill('whois')

    const dropdown = page.locator('#ac-dropdown')
    await expect(dropdown).toBeVisible()
    await expect(dropdown).toContainText('whois 8.8.8.8')

    await page.locator('header').click({ position: { x: 16, y: 16 } })

    await expect(dropdown).toBeHidden()
    await expect(input).toHaveValue('whois')
  })
})
