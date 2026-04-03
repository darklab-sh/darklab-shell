import { test, expect } from '@playwright/test'
import { runCommand } from './helpers.js'

const CMD = 'curl http://localhost:5001/health'

test.describe('command execution', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('output appears in the terminal after running a command', async ({ page }) => {
    await runCommand(page, CMD)
    // curl against /health returns JSON containing "status"
    const output = page.locator('.tab-panel.active .output')
    await expect(output).toContainText('status')
  })

  test('status pill shows EXIT 0 and output has an exit-ok line', async ({ page }) => {
    await runCommand(page, CMD)
    await expect(page.locator('.status-pill')).toHaveText('EXIT 0')
    // The exit summary line has the exit-ok class
    await expect(page.locator('.tab-panel.active .output .exit-ok')).toBeVisible()
  })

  test('denied command shows [denied] in output and ERROR status', async ({ page }) => {
    // Shell operators are blocked client-side — no server round-trip needed
    await page.locator('#cmd').fill('ls -la && whoami')
    await page.keyboard.press('Enter')
    await expect(page.locator('.status-pill')).toHaveText('ERROR')
    await expect(page.locator('.tab-panel.active .output')).toContainText('[denied]')
  })

})

