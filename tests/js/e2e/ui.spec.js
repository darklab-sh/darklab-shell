import { test, expect } from '@playwright/test'
import { ensurePromptReady, runCommand } from './helpers.js'

test.describe('theme selector', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await ensurePromptReady(page)
  })

  test('clicking the theme button opens the theme selector', async ({ page }) => {
    await page.locator('.rail-nav [data-action="theme"]').click()
    await expect(page.locator('#theme-overlay')).toHaveClass(/open/)
    await expect(page.locator('#theme-select .theme-card-active')).toBeVisible()
  })

  test('selecting a theme applies it from the selector', async ({ page }) => {
    await page.locator('.rail-nav [data-action="theme"]').click()
    const optionLabels = await page
      .locator('#theme-select .theme-card-label')
      .evaluateAll((labels) => labels.map((label) => label.textContent))
    expect(optionLabels).toContain('Darklab Obsidian')
    expect(optionLabels).toContain('Charcoal Steel')
    const groupLabels = await page
      .locator('#theme-select .theme-picker-group-title')
      .evaluateAll((labels) => labels.map((label) => label.textContent))
    expect(groupLabels).toEqual([
      'Dark Neon',
      'Dark Neutral',
      'Dark Mid-tone',
      'Warm Light',
      'Cool Light',
      'Neutral Mid-tone',
      'Neutral Light',
    ])
    await page.locator('#theme-select [data-theme-name="charcoal_steel"]').click()
    await expect(page.locator('body')).toHaveAttribute('data-theme', 'charcoal_steel')

    await page.locator('#theme-select [data-theme-name="cobalt_obsidian"]').click()
    await expect(page.locator('body')).toHaveAttribute('data-theme', 'cobalt_obsidian')
  })

  test('falls back to the configured default theme when localStorage references a missing theme', async ({
    page,
  }) => {
    await page.evaluate(() => {
      localStorage.setItem('theme', 'theme_missing.yaml')
    })

    await page.reload()
    await page.locator('#cmd').waitFor()

    await expect(page.locator('body')).toHaveAttribute('data-theme', 'darklab_obsidian')
  })
})

test.describe('FAQ modal', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/allowed-commands', (route) => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          restricted: true,
          commands: ['ping', 'traceroute'],
          groups: [
            {
              name: 'Networking',
              commands: ['ping', 'traceroute'],
            },
          ],
        }),
      })
    })
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('FAQ button opens the overlay', async ({ page }) => {
    await expect(page.locator('#faq-overlay')).not.toHaveClass(/open/)
    await page.locator('.rail-nav [data-action="faq"]').click()
    await expect(page.locator('#faq-overlay')).toHaveClass(/open/)
  })

  test('close button inside the FAQ modal closes it', async ({ page }) => {
    await page.locator('.rail-nav [data-action="faq"]').click()
    await expect(page.locator('#faq-overlay')).toHaveClass(/open/)

    await page.locator('.faq-close').click()
    await expect(page.locator('#faq-overlay')).not.toHaveClass(/open/)
  })

  test('clicking the overlay backdrop closes the FAQ modal', async ({ page }) => {
    await page.locator('.rail-nav [data-action="faq"]').click()
    await expect(page.locator('#faq-overlay')).toHaveClass(/open/)

    // Click on the overlay element itself (outside the modal content box)
    await page.locator('#faq-overlay').click({ position: { x: 10, y: 10 } })
    await expect(page.locator('#faq-overlay')).not.toHaveClass(/open/)
  })

  test('renders backend-driven FAQ content and allowlist chips', async ({ page }) => {
    await page.locator('.rail-nav [data-action="faq"]').click()
    await expect(page.locator('#faq-overlay')).toHaveClass(/open/)

    await expect(page.locator('.faq-q')).toContainText([
      'What is this?',
      'What commands are allowed?',
    ])
    await expect(
      page.locator('.faq-a a[href*="gitlab.com/darklab.sh/darklab_shell"]').first(),
    ).toBeVisible()

    // The allowed-commands section is inside a collapsed accordion — expand it first
    await page.locator('.faq-q').filter({ hasText: 'What commands are allowed?' }).click()
    await expect(page.locator('#faq-allowed-text')).toBeVisible()
  })
})

test.describe('workspace modal', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('creates, views, edits, downloads, and consumes session files', async ({ page }) => {
    await expect(page.locator('.rail-nav [data-action="workspace"] .rail-nav-label')).toHaveText('files')
    await page.locator('.rail-nav [data-action="workspace"]').click()

    await expect(page.locator('#workspace-overlay')).toHaveClass(/open/)
    await expect(page.locator('#workspace-modal .faq-title')).toHaveText('FILES')
    await expect(page.locator('#workspace-summary')).toContainText('0 / 100 files')
    await expect(page.locator('#workspace-refresh-btn')).toHaveAttribute('aria-label', 'Refresh files')
    await expect(page.locator('#workspace-editor')).not.toBeVisible()
    await expect(page.locator('label[for="workspace-path-input"]')).toHaveText('File Name')

    await page.locator('#workspace-new-btn').click()
    await expect(page.locator('#workspace-editor')).toBeVisible()
    const pathInput = page.locator('#workspace-path-input')
    const textInput = page.locator('#workspace-text-input')
    await expect(pathInput).toBeVisible()
    await expect(textInput).toBeVisible()
    await pathInput.fill('targets.txt')
    await expect(pathInput).toHaveValue('targets.txt')
    await textInput.click()
    await textInput.fill('darklab.sh\n')
    await expect(textInput).toHaveValue('darklab.sh\n')
    await page.locator('#workspace-save-btn').click()
    await expect(page.locator('#workspace-editor')).not.toBeVisible()

    const row = page.locator('.workspace-file-row').filter({ hasText: 'targets.txt' })
    await expect(row).toBeVisible()
    await expect(page.locator('#workspace-summary')).toContainText('1 / 100 files')

    await row.locator('[data-workspace-action="view"]').click()
    await expect(page.locator('#workspace-viewer')).toBeVisible()
    await expect(page.locator('#workspace-viewer-title')).toHaveText('targets.txt')
    await expect(page.locator('#workspace-viewer-text .workspace-line-text').first()).toHaveText('darklab.sh')

    await page.locator('#workspace-close-viewer-btn').click()
    await expect(page.locator('#workspace-viewer')).not.toBeVisible()
    await row.locator('[data-workspace-action="edit"]').click()
    await expect(page.locator('#workspace-editor')).toBeVisible()
    await page.locator('#workspace-text-input').fill('darklab.sh\nip.darklab.sh\n')
    await page.locator('#workspace-save-btn').click()
    await expect(page.locator('#workspace-editor')).not.toBeVisible()
    await row.locator('[data-workspace-action="view"]').click()
    await expect(page.locator('#workspace-viewer-text')).toContainText('ip.darklab.sh')

    await page.locator('#workspace-close-viewer-btn').click()
    await expect(page.locator('#workspace-viewer')).not.toBeVisible()
    const [download] = await Promise.all([
      page.waitForEvent('download'),
      row.locator('[data-workspace-action="download"]').click(),
    ])
    expect(download.suggestedFilename()).toBe('targets.txt')

    await page.locator('.workspace-close').click()
    await expect(page.locator('#workspace-overlay')).not.toHaveClass(/open/)

    await runCommand(page, 'cat targets.txt')
    await expect(page.locator('.tab-panel.active .output')).toContainText('darklab.sh')
    await expect(page.locator('.tab-panel.active .output')).toContainText('ip.darklab.sh')
  })

  test('navigates nested file output folders and exposes viewer actions', async ({ page }) => {
    await page.locator('.rail-nav [data-action="workspace"]').click()
    await expect(page.locator('#workspace-overlay')).toHaveClass(/open/)

    await page.locator('#workspace-new-folder-btn').click()
    await page.locator('#confirm-host .form-input').fill('reports')
    await page.locator('#confirm-host [data-confirm-action-id="create"]').click()
    await expect(page.locator('#workspace-breadcrumbs')).toContainText('Files/reports')
    await expect(page.locator('.workspace-empty')).toHaveText('This folder is empty.')

    await page.locator('#workspace-new-btn').click()
    await expect(page.locator('#workspace-path-input')).toHaveValue('')
    await page.locator('#workspace-cancel-edit-btn').click()

    await page.locator('.workspace-folder-row').filter({ hasText: '..' }).locator('[data-workspace-action="open-folder"]').click()
    await expect(page.locator('#workspace-breadcrumbs')).toHaveText('Files')
    await expect(page.locator('.workspace-folder-row').filter({ hasText: 'reports' })).toBeVisible()

    await page.locator('.workspace-folder-row').filter({ hasText: 'reports' }).locator('.workspace-file-name').click()
    await expect(page.locator('#workspace-breadcrumbs')).toContainText('Files/reports')

    await page.locator('#workspace-breadcrumbs [data-workspace-dir=""]').click()
    await expect(page.locator('.workspace-folder-row').filter({ hasText: 'reports' })).toBeVisible()

    await page.locator('#workspace-new-btn').click()
    await page.locator('#workspace-path-input').fill('amass-viz/amass.html')
    await page.locator('#workspace-text-input').fill('<html>amass viz</html>\n')
    await page.locator('#workspace-save-btn').click()
    await expect(page.locator('#workspace-editor')).not.toBeVisible()

    const folder = page.locator('.workspace-folder-row').filter({ hasText: 'amass-viz' })
    await expect(folder).toBeVisible()
    await expect(page.locator('.workspace-file-row').filter({ hasText: 'amass.html' })).toHaveCount(0)

    await folder.locator('.workspace-file-name').click()
    await expect(page.locator('#workspace-breadcrumbs')).toContainText('Files/amass-viz')

    const file = page.locator('.workspace-file-row').filter({ hasText: 'amass.html' })
    await expect(file).toBeVisible()
    await file.locator('[data-workspace-action="view"]').click()

    await expect(page.locator('#workspace-viewer')).toBeVisible()
    await expect(page.locator('#workspace-viewer-title')).toHaveText('amass-viz/amass.html')
    await expect(page.locator('#workspace-viewer-text')).toContainText('amass viz')
    await expect(page.locator('#workspace-viewer [data-workspace-viewer-action="edit"]')).toBeVisible()
    await expect(page.locator('#workspace-viewer [data-workspace-viewer-action="download"]')).toBeVisible()
    await expect(page.locator('#workspace-viewer [data-workspace-viewer-action="delete"]')).toBeVisible()

    await page.locator('#workspace-close-viewer-btn').click()
    await expect(page.locator('#workspace-viewer')).not.toBeVisible()
    await page.locator('#workspace-breadcrumbs [data-workspace-dir=""]').click()
    await expect(folder).toBeVisible()
  })
})

test.describe('workflows modal', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  async function openWorkflowsModal(page) {
    await page.keyboard.press('Alt+g')
    await expect(page.locator('#workflows-overlay')).toHaveClass(/\bopen\b/)
    const firstCard = page.locator('.workflow-card').first()
    await expect(firstCard).toBeVisible()
    await expect(firstCard.locator('.workflow-input-control')).toBeVisible()
    return firstCard
  }

  test('input-driven workflows render prefilled form fields and runnable rendered steps', async ({ page }) => {
    const firstCard = await openWorkflowsModal(page)
    const input = firstCard.locator('.workflow-input-control')
    await expect(input).toHaveCount(1)
    await expect(input).toHaveValue('darklab.sh')
    const firstStep = firstCard.locator('.workflow-step').first()
    await expect(firstStep.locator('.workflow-step-cmd')).toBeVisible()
    const runBtn = firstStep.locator('.workflow-step-run')
    await expect(runBtn).toBeVisible()
    await expect(runBtn).toHaveText('▶')
    await expect(runBtn).toBeEnabled()
    await expect(firstCard.locator('.workflow-run-all')).toBeEnabled()
    await expect(firstStep.locator('.workflow-step-cmd')).toContainText('dig darklab.sh A')
  })

  test('step layout is a two-row grid with chip on row 1 and note on row 2', async ({ page }) => {
    const firstCard = await openWorkflowsModal(page)
    const firstStep = firstCard.locator('.workflow-step').first()
    const layout = await firstStep.evaluate((el) => ({
      display: getComputedStyle(el).display,
      children: Array.from(el.children).map((c) => c.className),
    }))
    expect(layout.display).toBe('grid')
    expect(layout.children[0]).toContain('workflow-step-main')
    expect(layout.children[1]).toContain('workflow-step-note')
  })

  test('clearing a required workflow input disables step actions until the value is restored', async ({ page }) => {
    const firstCard = await openWorkflowsModal(page)
    const input = firstCard.locator('.workflow-input-control')
    const runBtn = firstCard.locator('.workflow-step').first().locator('.workflow-step-run')
    const runAllBtn = firstCard.locator('.workflow-run-all')
    await input.fill('')
    await expect(runBtn).toBeDisabled()
    await expect(runAllBtn).toBeDisabled()
    await expect(firstCard.locator('.workflow-step').first().locator('.workflow-step-cmd')).toContainText('{{domain}}')
    await input.fill('example.com')
    await expect(runBtn).toBeEnabled()
    await expect(runAllBtn).toBeEnabled()
  })

  test('editing workflow inputs rerenders steps and step run submits the rendered command', async ({ page }) => {
    const firstCard = await openWorkflowsModal(page)
    const input = firstCard.locator('.workflow-input-control')
    await input.fill('example.com')
    await expect(input).toHaveValue('example.com')
    const runBtn = firstCard.locator('.workflow-step').first().locator('.workflow-step-run')
    await expect(runBtn).toBeEnabled()
    const cmd = await runBtn.getAttribute('data-workflow-step-cmd')
    expect(cmd).toBe('dig example.com A')
    await runBtn.click()
    await expect(page.locator('#workflows-overlay')).not.toHaveClass(/\bopen\b/)
    await expect(page.locator('body')).toContainText(cmd)
  })

  test('rendered workflow chips load interpolated commands into the prompt', async ({ page }) => {
    const firstCard = await openWorkflowsModal(page)
    const input = firstCard.locator('.workflow-input-control')
    await input.fill('example.com')
    await expect(input).toHaveValue('example.com')
    const chip = firstCard.locator('.workflow-step').nth(1).locator('.workflow-step-cmd')
    await expect(chip).toContainText('dig example.com NS')
    await expect(chip).toHaveAttribute('data-faq-command', 'dig example.com NS')
    await chip.click()
    await expect(page.locator('#cmd')).toHaveValue('dig example.com NS ')
  })

  test('workflow inputs persist when the workflow modal is reopened', async ({ page }) => {
    const firstCard = await openWorkflowsModal(page)
    const input = firstCard.locator('.workflow-input-control')
    await input.fill('persist.example')
    await page.locator('.workflows-close').click()
    await expect(page.locator('#workflows-overlay')).not.toHaveClass(/\bopen\b/)
    await openWorkflowsModal(page)
    await expect(page.locator('.workflow-card').first().locator('.workflow-input-control')).toHaveValue('persist.example')
    await expect(page.locator('.workflow-card').first().locator('.workflow-step').first().locator('.workflow-step-cmd')).toContainText('dig persist.example A')
  })

  test('run all executes rendered workflow steps sequentially in the same tab', async ({ page }) => {
    const postedCommands = []
    await page.route('**/run', async (route) => {
      const payload = JSON.parse(route.request().postData() || '{}')
      const command = String(payload.command || '')
      postedCommands.push(command)
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: [
          `data: {"type":"started","run_id":"workflow-${postedCommands.length}"}\n\n`,
          `data: {"type":"output","text":"mock output for ${command}\\n"}\n\n`,
          'data: {"type":"exit","code":0,"elapsed":0.01}\n\n',
        ].join(''),
      })
    })

    await ensurePromptReady(page)
    await openWorkflowsModal(page)
    const workflowCard = page.locator('.workflow-card', { hasText: 'Subdomain HTTP Triage' })
    await expect(workflowCard).toBeVisible()
    const input = workflowCard.locator('.workflow-input-control')
    await input.fill('example.com')
    await expect(input).toHaveValue('example.com')
    await expect(workflowCard.locator('.workflow-run-all')).toBeEnabled()
    await workflowCard.locator('.workflow-run-all').click()
    await expect(page.locator('#workflows-overlay')).not.toHaveClass(/\bopen\b/)
    await expect(page.locator('.tab')).toHaveCount(1)
    await expect(page.locator('body')).toContainText('[workflow] Running 3 steps sequentially in this tab.')
    await expect(page.locator('body')).toContainText('subfinder -d example.com -silent -o subdomains.txt')
    await expect(page.locator('body')).toContainText('pd-httpx -l subdomains.txt -silent -o live-urls.txt')
    await expect(page.locator('body')).toContainText(
      'pd-httpx -l live-urls.txt -status-code -title -tech-detect -o http-summary.txt',
    )
    await expect(page.locator('body')).toContainText('[workflow] Completed all queued steps.')
    await expect.poll(() => postedCommands).toEqual([
      'subfinder -d example.com -silent -o subdomains.txt',
      'pd-httpx -l subdomains.txt -silent -o live-urls.txt',
      'pd-httpx -l live-urls.txt -status-code -title -tech-detect -o http-summary.txt',
    ])
  })

  test('clicking a rail workflow opens the scoped modal without collapsing the rail list', async ({ page }) => {
    const section = page.locator('#rail-section-workflows')
    if (await section.evaluate((node) => node.classList.contains('closed'))) {
      await page.locator('#rail-workflows-header').click()
    }
    const railItems = page.locator('#rail-workflows-list .rail-item')
    await expect(railItems.first()).toBeVisible()
    const beforeCount = await railItems.count()
    expect(beforeCount).toBeGreaterThan(1)

    await railItems.first().click()

    await expect(page.locator('#workflows-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#workflows-modal .workflow-card')).toHaveCount(1)
    await expect(page.locator('#rail-workflows-list .rail-item')).toHaveCount(beforeCount)
  })
})

test.describe('options modal', () => {
  // The HUD clock "local" mode formats using the browser's local timezone.
  // CI runners are typically in UTC, which makes `not.toContainText('UTC')`
  // fail even after switching to local mode (local = UTC on that machine).
  // Pin a non-UTC zone so the assertion is environment-independent.
  test.use({ timezoneId: 'America/New_York' })

  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.locator('#cmd').waitFor()
  })

  test('persists theme, timestamps, line number, and HUD clock preferences across reload', async ({
    page,
  }) => {
    await page.locator('.rail-nav [data-action="theme"]').click()
    await expect(page.locator('#theme-overlay')).toHaveClass(/open/)
    await page.locator('#theme-select [data-theme-name="apricot_sand"]').click()
    await page.locator('.theme-close').click()

    await page.locator('.rail-nav [data-action="options"]').click()
    await expect(page.locator('#options-overlay')).toHaveClass(/open/)
    await page.locator('#options-ts-select').selectOption('elapsed')
    await page.locator('#options-ln-toggle').check()
    await Promise.all([
      page.waitForResponse((response) => {
        if (!response.url().endsWith('/session/preferences')) return false
        if (response.request().method() !== 'POST') return false
        try {
          const payload = JSON.parse(response.request().postData() || '{}')
          return payload?.preferences?.pref_hud_clock === 'local'
        } catch {
          return false
        }
      }),
      page.locator('#options-hud-clock-select').selectOption('local'),
    ])
    await page.locator('.options-close').click()

    await expect(page.locator('body')).toHaveAttribute('data-theme', 'apricot_sand')
    await expect(page.locator('#ts-btn')).toHaveText('timestamps: elapsed')
    await expect(page.locator('#ln-btn')).toHaveText('line numbers: on')
    await expect(page.locator('#hud-clock')).not.toContainText('UTC')
    await expect(page.locator('#hud-clock')).toHaveAttribute('title', /local time/i)

    await page.reload()
    await page.locator('#cmd').waitFor()

    await expect(page.locator('body')).toHaveAttribute('data-theme', 'apricot_sand')
    await expect(page.locator('#ts-btn')).toHaveText('timestamps: elapsed')
    await expect(page.locator('#ln-btn')).toHaveText('line numbers: on')
    await expect(page.locator('#hud-clock')).not.toContainText('UTC')
    await expect(page.locator('#hud-clock')).toHaveAttribute('title', /local time/i)
  })
})
