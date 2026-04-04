import { test, expect } from '@playwright/test'
import { runCommand } from './helpers.js'

const CMD = 'curl http://localhost:5001/health'

test.describe('welcome animation', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/welcome', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            cmd: 'echo ready',
            out: 'welcome should disappear if the user starts typing',
          },
        ]),
      })
    })
    await page.route('**/welcome/ascii', route => {
      route.fulfill({
        status: 200,
        contentType: 'text/plain',
        body: [
          '           /$$                 /$$ /$$           /$$                     /$$       /$$           /$$                    /$$      ',
          '          | $$                | $$| $$          | $$                    | $$      | $$          | $$                   | $$      ',
        ].join('\n'),
      })
    })
    await page.route('**/welcome/hints', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          items: ['Use the history panel to reopen saved runs.'],
        }),
      })
    })
    await page.route('**/run', route => {
      route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: [
          'data: {"type":"started","run_id":"welcome-test-run"}\n\n',
          'data: {"type":"output","text":"status\\n"}\n\n',
          'data: {"type":"exit","code":0,"elapsed":0.1}\n\n',
        ].join(''),
      })
    })
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('running a command cancels the welcome animation and clears partial output', async ({ page }) => {
    await expect(page.locator('.welcome-ascii-art')).toContainText('/$$')
    await expect(page.locator('.welcome-status-loaded')).toHaveCount(5)
    await expect(page.locator('.welcome-command').first()).toContainText('anon@shell.darklab.sh:~$')

    await page.waitForFunction(() => {
      const text = document.querySelector('.wlc-command-text')?.textContent || ''
      return text.length >= 5
    })

    await runCommand(page, CMD)

    const output = page.locator('.tab-panel.active .output')
    await expect(output).toContainText('status')
    await expect(output).not.toContainText('welcome should disappear')
    await expect(page.locator('.welcome-banner')).toHaveCount(0)
    await expect(page.locator('.welcome-command')).toHaveCount(0)
    await expect(page.locator('.wlc-cursor')).toHaveCount(0)
  })

  test('welcome finishes with a hint row after the intro and command blocks', async ({ page }) => {
    await expect(page.locator('.welcome-ascii-art')).toContainText('/$$')
    await expect(page.locator('.welcome-status-loaded')).toHaveCount(5)
    await expect(page.locator('.welcome-command').nth(1)).toContainText('echo ready')
    await expect(page.locator('.welcome-command-badge')).toContainText('try this first')
    await expect(page.locator('.line.welcome-hint')).toContainText('Use the history panel to reopen saved runs.')
  })

  test('clicking the decorative intro command does not load it into the prompt', async ({ page }) => {
    const intro = page.locator('.welcome-command').first().locator('.welcome-command-text')
    await expect(intro).toContainText('cat ~/.ascii-art.txt')

    await intro.click()

    await expect(page.locator('#cmd')).toHaveValue('')
  })

  test('clicking a sampled welcome command text loads it into the prompt', async ({ page }) => {
    const sample = page.locator('.welcome-command').nth(1).locator('.welcome-command-text.welcome-command-loadable')
    await expect(sample).toContainText('echo ready', { timeout: 15000 })

    await sample.click()

    await expect(page.locator('#cmd')).toHaveValue('echo ready')
    await expect(page.locator('#cmd')).toBeFocused()
    await expect(page.locator('.welcome-command').nth(1)).toHaveClass(/welcome-command-loaded/)
    await expect(page.locator('.prompt-wrap')).toHaveClass(/prompt-wrap-loaded/)
  })

  test('pressing Enter on a sampled welcome command text loads it into the prompt', async ({ page }) => {
    const sample = page.locator('.welcome-command').nth(1).locator('.welcome-command-text.welcome-command-loadable')
    await expect(sample).toContainText('echo ready', { timeout: 15000 })

    await sample.focus()
    await sample.evaluate(el => {
      el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
    })

    await expect(page.locator('#cmd')).toHaveValue('echo ready')
    await expect(page.locator('#cmd')).toBeFocused()
  })

  test('clicking the try this first badge loads the featured command into the prompt', async ({ page }) => {
    const badge = page.locator('.welcome-command-badge')
    await expect(badge).toContainText('try this first', { timeout: 15000 })

    await badge.click()

    await expect(page.locator('#cmd')).toHaveValue('echo ready')
    await expect(page.locator('#cmd')).toBeFocused()
  })

  test('pressing Space on the try this first badge loads the featured command into the prompt', async ({ page }) => {
    const badge = page.locator('.welcome-command-badge')
    await expect(badge).toContainText('try this first', { timeout: 15000 })

    await badge.focus()
    await badge.evaluate(el => {
      el.dispatchEvent(new KeyboardEvent('keydown', { key: ' ', bubbles: true }))
    })

    await expect(page.locator('#cmd')).toHaveValue('echo ready')
    await expect(page.locator('#cmd')).toBeFocused()
  })

  test('running a command in another tab does not tear down the original welcome tab', async ({ page }) => {
    await expect(page.locator('.line.welcome-hint')).toContainText('Use the history panel to reopen saved runs.', { timeout: 15000 })

    const originalTab = page.locator('.tab').first()
    await page.locator('#new-tab-btn').click()
    await runCommand(page, CMD)

    const activeOutput = page.locator('.tab-panel.active .output')
    await expect(activeOutput).toContainText('status')

    await originalTab.click()
    await expect(page.locator('.tab-panel.active .welcome-banner')).toHaveCount(1)
    await expect(page.locator('.tab-panel.active .line.welcome-hint')).toContainText('Use the history panel to reopen saved runs.')
  })

  test('clearing a non-welcome tab does not remove the original welcome UI', async ({ page }) => {
    await expect(page.locator('.line.welcome-hint')).toContainText('Use the history panel to reopen saved runs.', { timeout: 15000 })

    const originalTab = page.locator('.tab').first()
    await page.locator('#new-tab-btn').click()
    await page.locator('.tab-panel.active [data-action="clear"]').click()

    await originalTab.click()
    await expect(page.locator('.tab-panel.active .welcome-banner')).toHaveCount(1)
    await expect(page.locator('.tab-panel.active .line.welcome-hint')).toContainText('Use the history panel to reopen saved runs.')
  })

  test('mobile welcome layout keeps the prompt and featured badge horizontally readable', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.reload()
    await page.locator('#cmd').waitFor()

    const prompt = page.locator('.welcome-command').nth(1).locator('.wlc-prompt')
    const badge = page.locator('.welcome-command-badge')

    await expect(prompt).toContainText('anon@shell.darklab.sh:~$')
    await expect(badge).toContainText('try this first')

    const promptBox = await prompt.boundingBox()
    const badgeBox = await badge.boundingBox()

    expect(promptBox).not.toBeNull()
    expect(badgeBox).not.toBeNull()
    expect(promptBox.width).toBeGreaterThan(promptBox.height * 2)
    expect(badgeBox.width).toBeGreaterThan(badgeBox.height * 2)
  })
})
