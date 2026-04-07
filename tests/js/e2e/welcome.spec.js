import { test, expect } from '@playwright/test'
import { runCommand, makeTestIp } from './helpers.js'

const CMD = 'curl http://localhost:5001/health'
const TEST_IP = makeTestIp(68)

test.describe('welcome animation', () => {
  test.beforeEach(async ({ page }) => {
    await page.setExtraHTTPHeaders({ 'X-Forwarded-For': TEST_IP })
    await page.route('**/welcome', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([
          {
            cmd: 'echo ready',
            group: 'basics',
            featured: true,
            out: 'welcome should disappear if the user starts typing',
          },
          {
            cmd: 'dig darklab.sh A',
            out: 'second sample should appear instantly when welcome settles',
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
    await page.route('**/welcome/ascii-mobile', route => {
      route.fulfill({
        status: 200,
        contentType: 'text/plain',
        body: [
          '.----[ shell.darklab.sh :: mobile console ]----.',
          '|                                              |',
          '|   __  __   ___   ___   ___   ___   ___       |',
          "|  |  \\/  | / _ \\ / _ \\ / _ \\ / _ \\ / _ \\      |",
          '|  | |\\/| || (_) | (_) | (_) | (_) | (_) |     |',
          '|  |_|  |_| \\___/ \\___/ \\___/ \\___/ \\___/      |',
          '|                                              |',
          "'----[ status: ready ]----[ prompt: anon@shell.darklab.sh:~$ ]----'",
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
    await expect(page.locator('.welcome-command').first()).toContainText('echo ready')

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
    await expect(page.locator('.welcome-section-header').first()).toContainText('Recommended commands')
    await expect(page.locator('.welcome-command').nth(0)).toContainText('echo ready')
    await expect(page.locator('.welcome-command-featured')).toHaveCount(0)
    await expect(page.locator('.welcome-command-badge')).toContainText('try this first')
    await expect(page.locator('.welcome-section-header').nth(1)).toContainText('Helpful hints')
    await expect(page.locator('.line.welcome-hint')).toContainText('Use the history panel to reopen saved runs.')
  })

  test('clicking a sampled welcome command text loads it into the prompt', async ({ page }) => {
    const sample = page.locator('.welcome-command').nth(0).locator('.welcome-command-text.welcome-command-loadable')
    await expect(sample).toContainText('echo ready', { timeout: 15000 })

    await sample.click()

    await expect(page.locator('#cmd')).toHaveValue('echo ready')
    await expect(page.locator('#cmd')).toBeFocused()
  })

  test('pressing Enter on a sampled welcome command text loads it into the prompt', async ({ page }) => {
    const sample = page.locator('.welcome-command').nth(0).locator('.welcome-command-text.welcome-command-loadable')
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

  test('typing into the prompt settles the remaining welcome intro immediately', async ({ page }) => {
    await page.waitForFunction(() => {
      const text = document.querySelector('.wlc-command-text')?.textContent || ''
      return text.length >= 5
    })

    await page.locator('#cmd').fill('dig ')

    await expect(page.locator('.welcome-status-loaded')).toHaveCount(5)
    await expect(page.locator('.welcome-command').nth(0)).toContainText('echo ready')
    await expect(page.locator('.welcome-command').nth(1)).toContainText('dig darklab.sh A')
    await expect(page.locator('.line.welcome-hint')).toContainText('Use the history panel to reopen saved runs.')
    await expect(page.locator('#cmd')).toHaveValue('dig ')
  })

  test('pressing Space in the prompt settles the remaining welcome intro immediately', async ({ page }) => {
    await page.waitForFunction(() => {
      const text = document.querySelector('.wlc-command-text')?.textContent || ''
      return text.length >= 5
    })

    await page.locator('#cmd').press(' ')

    await expect(page.locator('.welcome-status-loaded')).toHaveCount(5)
    await expect(page.locator('.welcome-command').nth(0)).toContainText('echo ready')
    await expect(page.locator('.welcome-command').nth(1)).toContainText('dig darklab.sh A')
    await expect(page.locator('.line.welcome-hint')).toContainText('Use the history panel to reopen saved runs.')
    await expect(page.locator('#cmd')).toHaveValue('')
  })

  test('pressing Escape in the prompt settles welcome without changing input text', async ({ page }) => {
    await page.waitForFunction(() => {
      const text = document.querySelector('.wlc-command-text')?.textContent || ''
      return text.length >= 5
    })

    await page.locator('#cmd').press('Escape')

    await expect(page.locator('.welcome-status-loaded')).toHaveCount(5)
    await expect(page.locator('.welcome-command').nth(0)).toContainText('echo ready')
    await expect(page.locator('.welcome-command').nth(1)).toContainText('dig darklab.sh A')
    await expect(page.locator('.line.welcome-hint')).toContainText('Use the history panel to reopen saved runs.')
    await expect(page.locator('#cmd')).toHaveValue('')
    await expect(page.locator('#cmd')).toBeFocused()
  })

  test('pressing Ctrl+C while welcome is active settles the intro without opening kill confirmation', async ({ page }) => {
    await page.waitForFunction(() => {
      const text = document.querySelector('.wlc-command-text')?.textContent || ''
      return text.length >= 5
    })

    const beforePromptEchoCount = await page.locator('.tab-panel.active .output .line.prompt-echo').count()
    await page.locator('#cmd').press('Control+C')

    await expect(page.locator('.welcome-status-loaded')).toHaveCount(5)
    await expect(page.locator('.welcome-command').nth(0)).toContainText('echo ready')
    await expect(page.locator('.welcome-command').nth(1)).toContainText('dig darklab.sh A')
    await expect(page.locator('#kill-overlay')).toBeHidden()
    await expect(page.locator('.tab-panel.active .output .line.prompt-echo')).toHaveCount(beforePromptEchoCount + 1)
    await expect(page.locator('#cmd')).toHaveValue('')
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

  test.describe('mobile view', () => {
    test.use({ hasTouch: true })

    test('switches to the mobile welcome path with the mobile banner', async ({ page }) => {
      await page.setViewportSize({ width: 390, height: 844 })
      await page.reload()
      await page.locator('#mobile-cmd').waitFor()

      await expect(page.locator('.welcome-ascii-art')).toContainText('mobile console')
      await expect(page.locator('.welcome-status-loaded')).toHaveCount(5, { timeout: 15_000 })
      await expect(page.locator('.welcome-command')).toHaveCount(0)
      await expect(page.locator('.welcome-section-header')).toContainText('Helpful hints')
      await expect(page.locator('.line.welcome-hint')).toContainText(/Tap the prompt|Use the mobile menu|helper row|Rotate the device|Long runs/)
      await expect(page.locator('#mobile-run-btn')).toBeVisible()
    })
  })
})
