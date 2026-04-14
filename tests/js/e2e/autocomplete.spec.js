import { test, expect } from '@playwright/test'
import { ensurePromptReady, setComposerValueForTest } from './helpers.js'

test.describe('autocomplete', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.locator('#cmd').waitFor()
    await ensurePromptReady(page)
  })

  test('Tab expands to the shared prefix and Enter accepts a reselected suggestion', async ({ page }) => {
    const input = page.locator('#cmd')
    // Start with a partial flag so contextual suggestions are visible
    await setComposerValueForTest(page, 'nmap -')

    const dropdown = page.locator('#ac-dropdown')
    await expect.poll(async () => ({
      hidden: await dropdown.evaluate(node => node.classList.contains('u-hidden')),
      text: (await dropdown.textContent()) || '',
    })).toEqual(expect.objectContaining({
      hidden: false,
      text: expect.stringContaining('-sT'),
    }))
    await expect(dropdown).not.toContainText('man nmap')

    await page.keyboard.press('ArrowDown')
    await expect(dropdown.locator('.ac-item.ac-active').first()).toContainText('-h')

    // Tab tries shared prefix expansion; prefix is already '-' so it cycles
    // the selection forward by one to -sT instead
    await page.keyboard.press('Tab')
    await expect(input).toHaveValue('nmap -')
    await expect(dropdown).toBeVisible()
    await expect(dropdown.locator('.ac-item.ac-active').first()).toContainText('-sT')

    // Accept the reselected suggestion
    await page.keyboard.press('Enter')
    await expect(input).toHaveValue('nmap -sT')
    await expect(dropdown).toBeHidden()
  })

  test('clicking outside the prompt hides autocomplete without changing the input', async ({ page }) => {
    const input = page.locator('#cmd')
    await setComposerValueForTest(page, 'whoi')

    const dropdown = page.locator('#ac-dropdown')
    await expect.poll(async () => ({
      hidden: await dropdown.evaluate(node => node.classList.contains('u-hidden')),
      text: (await dropdown.textContent()) || '',
    })).toEqual(expect.objectContaining({
      hidden: false,
      text: expect.stringContaining('whois'),
    }))

    await page.mouse.click(8, 8)

    await expect(dropdown).toBeHidden()
    await expect(input).toHaveValue('whoi')
  })

  test('context-aware autocomplete replaces only the active token for command flags', async ({ page }) => {
    const input = page.locator('#cmd')
    const dropdown = page.locator('#ac-dropdown')

    await setComposerValueForTest(page, 'nmap -')
    await expect.poll(async () => ({
      hidden: await dropdown.evaluate(node => node.classList.contains('u-hidden')),
      text: (await dropdown.textContent()) || '',
    })).toEqual(expect.objectContaining({
      hidden: false,
      text: expect.stringContaining('-sV'),
    }))
    await expect(dropdown).toContainText('Service/version detection')
    await expect(dropdown).not.toContainText('man nmap')

    await page.keyboard.press('ArrowDown')
    await page.keyboard.press('ArrowDown')
    await expect(dropdown.locator('.ac-item.ac-active').first()).toContainText('-sT')

    await page.keyboard.press('Enter')
    await expect(input).toHaveValue('nmap -sT')
    await expect(dropdown).toBeHidden()
  })

  test('context-aware autocomplete shows positional hints alongside flags after a known command root', async ({ page }) => {
    const input = page.locator('#cmd')
    const dropdown = page.locator('#ac-dropdown')

    await input.pressSequentially('nmap ')
    await expect.poll(async () => ({
      hidden: await dropdown.evaluate(node => node.classList.contains('u-hidden')),
      text: (await dropdown.textContent()) || '',
    })).toEqual(expect.objectContaining({
      hidden: false,
      text: expect.stringContaining('<target>'),
    }))
    await expect(dropdown).toContainText('-sV')
    await expect(dropdown).toContainText('-sT')
    await expect(dropdown).toContainText('<target>')
    await expect(dropdown).toContainText('Hostname, IP, or CIDR')
  })

  test('built-in pipe support suggests the supported pipe commands after a pipe', async ({ page }) => {
    const input = page.locator('#cmd')
    const dropdown = page.locator('#ac-dropdown')

    await setComposerValueForTest(page, 'help | ')
    await expect.poll(async () => ({
      hidden: await dropdown.evaluate(node => node.classList.contains('u-hidden')),
      text: (await dropdown.textContent()) || '',
    })).toEqual(expect.objectContaining({
      hidden: false,
      text: expect.stringContaining('wc -l'),
    }))
    await expect(dropdown).toContainText('grep')
    await expect(dropdown).toContainText('head')
    await expect(dropdown).toContainText('tail')
    await expect(dropdown).toContainText('wc -l')
  })
})
