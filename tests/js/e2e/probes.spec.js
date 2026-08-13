// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { expect, test } from '@playwright/test'

import { ensurePromptReady, runCommand } from './helpers.js'


async function createActiveProbeProject(page) {
  const targetValue = `probe-${Date.now()}.example.com`
  return page.evaluate(async (value) => {
    const createdResponse = await apiFetch('/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: `Probe Planner ${Date.now()}` }),
    })
    if (!createdResponse.ok) throw new Error(`project create failed: ${createdResponse.status}`)
    const project = (await createdResponse.json()).project
    const activeResponse = await apiFetch('/projects/active', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: project.id }),
    })
    if (!activeResponse.ok) throw new Error(`active project failed: ${activeResponse.status}`)
    const targetResponse = await apiFetch(`/projects/${encodeURIComponent(project.id)}/targets`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: 'domain', value }),
    })
    if (!targetResponse.ok) throw new Error(`target create failed: ${targetResponse.status}`)
    return { project, target: (await targetResponse.json()).target }
  }, targetValue)
}


test.describe('Project probe terminal', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
    await page.locator('#cmd').waitFor()
    await ensurePromptReady(page)
  })

  test('lazy-loads and previews a Project target without a run', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    const fixture = await createActiveProbeProject(page)
    await runCommand(
      page,
      `probe plan ping ${fixture.target.value} --project ${fixture.project.id}`,
    )

    const output = page.locator('.tab-panel.active .output')
    await expect(output).toContainText('Probe plan: Ping')
    await expect(output).toContainText(`Target: ${fixture.target.value}`)
    await expect(output).toContainText(`Command: ping -c 4 -W 2 ${fixture.target.value}`)
    await expect(output).toContainText('Credentials: none')
    await expect(page.locator('#hud-last-exit')).toHaveText('0')

    const resources = await page.evaluate(() => performance.getEntriesByType('resource').map(entry => entry.name))
    expect(resources.some(name => /probe[-_]terminal/.test(name))).toBe(true)
  })

  test('keeps the plan in the origin tab and launches nothing when declined', async ({ page }) => {
    const fixture = await createActiveProbeProject(page)
    let launchRequests = 0
    page.on('request', request => {
      if (request.method() === 'POST' && /\/probes\/run$/.test(request.url())) {
        launchRequests += 1
      }
    })
    await runCommand(
      page,
      `probe run ping ${fixture.target.value} --project ${fixture.project.id}`,
    )

    const output = page.locator('.tab-panel.active .output')
    await expect(output).toContainText('Probe plan: Ping')
    await expect(output).toContainText('Run this probe? Type yes or no.')
    const tabId = await page.evaluate(() => window.APP_STATE_API.getActiveTabId())
    const input = page.locator('#cmd')
    await input.fill('no')
    await input.press('Enter')
    await expect(output).toContainText('Probe launch canceled.')
    expect(await page.evaluate(() => window.APP_STATE_API.getActiveTabId())).toBe(tabId)
    expect(launchRequests).toBe(0)
  })
})
