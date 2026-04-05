import { test, expect } from '@playwright/test'
import { runCommand } from './helpers.js'

const CMD = 'curl http://localhost:5001/health'

test.describe('timestamp toggle', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('clicking ts-btn cycles through elapsed → clock → off modes', async ({ page }) => {
    // Default state: no timestamp class on body
    await expect(page.locator('body')).not.toHaveClass(/ts-elapsed|ts-clock/)

    // First click → elapsed mode
    await page.locator('#ts-btn').click()
    await expect(page.locator('body')).toHaveClass(/ts-elapsed/)

    // Second click → clock mode
    await page.locator('#ts-btn').click()
    await expect(page.locator('body')).toHaveClass(/ts-clock/)

    // Third click → off (neither class present)
    await page.locator('#ts-btn').click()
    await expect(page.locator('body')).not.toHaveClass(/ts-elapsed|ts-clock/)
  })

  test('ts-btn has active class when timestamps are enabled', async ({ page }) => {
    await expect(page.locator('#ts-btn')).not.toHaveClass(/active/)

    await page.locator('#ts-btn').click()
    await expect(page.locator('#ts-btn')).toHaveClass(/active/)
  })

  test('output lines have timestamp data attributes after running a command', async ({ page }) => {
    await page.locator('#ts-btn').click() // enable timestamps
    await runCommand(page, CMD)

    // Every line gets data-ts-c (clock time).
    const firstLine = page.locator('.tab-panel.active .output .line').first()
    await expect(firstLine).toHaveAttribute('data-ts-c', /.+/)

    // data-ts-e (elapsed) is only set on lines appended while the run is active,
    // so the echoed command line won't have it. At least one server-output line
    // should carry the elapsed attribute.
    const elapsedLine = page.locator('.tab-panel.active .output .line[data-ts-e]')
    await expect(elapsedLine.first()).toBeVisible()
  })

  test('line numbers work with timestamps and typing continues after toggling display modes', async ({ page }) => {
    await page.locator('#ln-btn').click()
    await expect(page.locator('body')).toHaveClass(/ln-on/)

    await page.locator('#ts-btn').click()
    await expect(page.locator('body')).toHaveClass(/ts-elapsed/)

    await page.keyboard.type(CMD)
    await page.keyboard.press('Enter')

    await expect(page.locator('#status')).toHaveText('EXIT 0')

    const prefixedLine = page.locator('.tab-panel.active .output .line[data-prefix]').first()
    await expect(prefixedLine).toHaveAttribute('data-prefix', /^\d+(\s+\+\d+\.\ds)?$/)
    await expect(page.locator('#shell-prompt-wrap')).toHaveAttribute('data-prefix', /^\d+$/)
  })
})
