// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { expect, test } from '@playwright/test'

import { ensurePromptReady, runCommand, waitForHistoryRuns } from './helpers.js'


async function createActiveProbeProject(
  page,
  { targetType = 'domain', targetValue = `probe-${Date.now()}.example.com` } = {},
) {
  return page.evaluate(async ({ type, value }) => {
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
      body: JSON.stringify({ type, value }),
    })
    if (!targetResponse.ok) throw new Error(`target create failed: ${targetResponse.status}`)
    return { project, target: (await targetResponse.json()).target }
  }, { type: targetType, value: targetValue })
}

async function projectRunLinkIds(page, projectId) {
  return page.evaluate(async (id) => {
    const response = await apiFetch(`/projects/${encodeURIComponent(id)}/links`, {
      cache: 'no-store',
    })
    if (!response.ok) throw new Error(`project links failed: ${response.status}`)
    const data = await response.json()
    return (Array.isArray(data.links) ? data.links : [])
      .filter(link => link?.entity_type === 'run')
      .map(link => String(link.entity_id || ''))
  }, projectId)
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
    await expect(output.getByText('Probe plan: Ping', { exact: true })).toHaveCount(1)
    await expect(output.getByText('Run this probe? Type yes or no.', { exact: true })).toHaveCount(1)
    expect(await page.evaluate(() => window.APP_STATE_API.getActiveTabId())).toBe(tabId)
    expect(launchRequests).toBe(0)
  })

  test('does not retain a probe approval across a page reload', async ({ page }) => {
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
    await expect(page.locator('.tab-panel.active .output')).toContainText(
      'Run this probe? Type yes or no.',
    )

    await page.reload()
    await page.locator('#cmd').waitFor()
    await ensurePromptReady(page)
    const input = page.locator('#cmd')
    await input.fill('yes')
    await input.press('Enter')
    await page.waitForTimeout(300)

    expect(launchRequests).toBe(0)
    expect(await page.evaluate(() => window.APP_STATE_API.getActiveTab()?.runId || '')).toBe('')
  })

  test('confirms, streams, saves, and links a probe in the origin tab', async ({ page }) => {
    const fixture = await createActiveProbeProject(page, {
      targetType: 'ip',
      targetValue: '8.8.8.8',
    })
    const originTabId = await page.evaluate(() => window.APP_STATE_API.getActiveTabId())
    const tabCount = await page.locator('.tab').count()
    const command = `probe run ping --entity-id ${fixture.target.id} --project ${fixture.project.id}`
    await runCommand(page, command)

    const output = page.locator('.tab-panel.active .output')
    await expect(output).toContainText('Probe plan: Ping')
    await expect(output).toContainText('Command: ping -c 4 -W 2 8.8.8.8')
    await expect(output).toContainText('Run this probe? Type yes or no.')

    const launchedResponse = page.waitForResponse(response => (
      response.request().method() === 'POST'
      && /\/probes\/run$/.test(response.url())
      && response.status() === 202
    ))
    const input = page.locator('#cmd')
    await input.fill('yes')
    await input.press('Enter')
    const launched = await (await launchedResponse).json()
    const runId = String(launched.run?.run_id || '')
    expect(runId).not.toBe('')

    await page.waitForFunction(() => {
      const tab = window.APP_STATE_API?.getActiveTab?.()
      return tab && (tab.st === 'ok' || tab.st === 'fail') && !tab.runId
    }, undefined, { timeout: 30_000 })
    await expect(output).toContainText('Probe plan: Ping')
    await expect(output).toContainText('[process exited with code')
    await expect(output.getByText('Probe plan: Ping', { exact: true })).toHaveCount(1)
    await expect(output.getByText('Run this probe? Type yes or no.', { exact: true })).toHaveCount(1)
    await expect(page.locator('.tab')).toHaveCount(tabCount)
    expect(await page.evaluate(() => window.APP_STATE_API.getActiveTabId())).toBe(originTabId)

    const runs = await waitForHistoryRuns(page, 1)
    const saved = runs.find(run => String(run.id || '') === runId)
    expect(saved?.command).toBe('ping -c 4 -W 2 8.8.8.8')
    expect(await projectRunLinkIds(page, fixture.project.id)).toContain(runId)
  })
})
