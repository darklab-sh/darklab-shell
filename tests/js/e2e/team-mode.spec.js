// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { test, expect } from '@playwright/test'
import {
  ensurePromptReady,
  openRailAction,
  runCommand,
} from './helpers.js'

const PERSONAL_COMMAND = 'hostname'
const TEAM_COMMAND = 'date'
const INVITED_MEMBER_COMMAND = 'whoami'

async function issueSessionToken(page) {
  return page.evaluate(async () => {
    const resp = await apiFetch('/session/token/generate')
    if (!resp.ok) throw new Error(`token generate failed: ${resp.status}`)
    const data = await resp.json()
    return data.session_token
  })
}

async function activateSessionToken(page, token) {
  await page.evaluate((sessionToken) => {
    localStorage.setItem('session_token', sessionToken)
  }, token)
  await page.reload({ waitUntil: 'domcontentloaded' })
  await ensurePromptReady(page, { timeout: 30_000 })
  await expect.poll(() => page.evaluate(() => SESSION_ID), { timeout: 15_000 }).toBe(token)
}

async function openTeamsOptions(page) {
  await openRailAction(page, 'options')
  await expect(page.locator('#options-overlay')).toHaveClass(/\bopen\b/)
  await page.locator('#options-tab-teams').click()
  await expect(page.locator('#options-panel-teams')).toBeVisible()
  await expect(page.locator('#options-panel-teams')).toHaveAttribute('data-teams-panel-bound', '1', {
    timeout: 15_000,
  })
  await expect(page.locator('#options-team-create-btn')).toBeEnabled({ timeout: 15_000 })
}

async function closeOptions(page) {
  const overlay = page.locator('#options-overlay')
  if (await overlay.evaluate((node) => node.classList.contains('open')).catch(() => false)) {
    await page.locator('.options-close').click()
    await expect(overlay).not.toHaveClass(/\bopen\b/)
  }
}

async function createTeamFromOptions(page, { name, slug, displayName }) {
  await openTeamsOptions(page)
  await page.locator('#options-team-create-btn').click()
  const form = page.locator('[data-team-form="create"]')
  await expect(form).toBeVisible()
  await form.locator('[name="name"]').fill(name)
  await form.locator('[name="slug"]').fill(slug)
  await form.locator('[name="display_name"]').fill(displayName)
  await form.locator('button[type="submit"]').click()
  await expect(page.locator('#options-team-detail')).toContainText('Recovery code', {
    timeout: 15_000,
  })
  await expect(page.locator('#options-team-detail')).toContainText(name)
  return page.evaluate(async (teamSlug) => {
    const resp = await apiFetch('/session/teams', { cache: 'no-store' })
    if (!resp.ok) throw new Error(`team list failed: ${resp.status}`)
    const data = await resp.json()
    const team = (data.teams || []).find((item) => item.slug === teamSlug)
    if (!team) throw new Error(`created team not found: ${teamSlug}`)
    return team.id
  }, slug)
}

async function createInviteFromOpenTeamDetail(page) {
  const inviteForm = page.locator('[data-team-invite-form]')
  await expect(inviteForm).toBeVisible()
  await inviteForm.locator('[name="label"]').fill('Playwright invite')
  await inviteForm.locator('[name="role"]').selectOption('operator')
  await inviteForm.locator('[name="max_uses"]').fill('1')
  await inviteForm.locator('button[type="submit"]').click()
  await expect(page.locator('.options-team-code code')).toHaveText(/^tinv_/, { timeout: 15_000 })
  return (await page.locator('.options-team-code code').textContent()) || ''
}

async function joinTeamFromOptions(page, { code, displayName, teamName }) {
  await openTeamsOptions(page)
  await page.locator('#options-team-join-btn').click()
  const form = page.locator('[data-team-form="join"]')
  await expect(form).toBeVisible()
  await form.locator('[name="code"]').fill(code)
  await form.locator('[name="display_name"]').fill(displayName)
  await form.locator('button[type="submit"]').click()
  await expect(page.locator('#options-teams-list')).toContainText(teamName, { timeout: 15_000 })
  await expect(page.locator('#options-team-detail')).toContainText(teamName)
}

async function switchScopeFromSelector(page, teamId = '') {
  const menu = page.locator('#team-scope-menu')
  const selector = teamId
    ? `[data-team-scope-menu-option="${teamId}"]`
    : '[data-team-scope-menu-option="personal"]'
  let lastError = null

  for (let attempt = 0; attempt < 4; attempt += 1) {
    await page.locator('#team-scope-trigger').click()
    await expect(menu).toBeVisible()
    const option = menu.locator(selector)
    await expect(option).toBeVisible({ timeout: 10_000 })
    try {
      await option.click({ timeout: 5_000 })
      lastError = null
      break
    } catch (err) {
      lastError = err
      const currentScope = await page.evaluate(() => {
        const sessionId = typeof SESSION_ID === 'string' && SESSION_ID ? SESSION_ID : 'anonymous'
        return localStorage.getItem(`active_team_id:${sessionId}`) || ''
      }).catch(() => null)
      if (currentScope === teamId) {
        lastError = null
        break
      }
      if (await menu.isVisible().catch(() => false)) {
        await page.keyboard.press('Escape').catch(() => {})
      }
    }
  }

  if (lastError) throw lastError
  await expect(menu).toBeHidden()
  await expect.poll(() => page.evaluate(() => {
    const sessionId = typeof SESSION_ID === 'string' && SESSION_ID ? SESSION_ID : 'anonymous'
    return localStorage.getItem(`active_team_id:${sessionId}`) || ''
  })).toBe(teamId)
}

async function historyCommands(page) {
  return page.evaluate(async () => {
    const resp = await apiFetch('/history?page_size=50&type=runs', { cache: 'no-store' })
    if (!resp.ok) throw new Error(`history failed: ${resp.status}`)
    const data = await resp.json()
    return (data.runs || []).map(run => run.command)
  })
}

async function createProject(page, name) {
  return page.evaluate(async (projectName) => {
    const resp = await apiFetch('/projects', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: projectName }),
    })
    if (!resp.ok) throw new Error(`project create failed: ${resp.status}`)
    const data = await resp.json()
    return data.project?.id || ''
  }, name)
}

async function projectNames(page) {
  return page.evaluate(async () => {
    const resp = await apiFetch('/projects', { cache: 'no-store' })
    if (!resp.ok) throw new Error(`projects failed: ${resp.status}`)
    const data = await resp.json()
    return (data.projects || []).map(project => project.name)
  })
}

test.describe('team mode browser flow', () => {
  test('creates a team, redeems an invite, switches scope, and shares team history', async ({
    page,
    browser,
  }) => {
    test.setTimeout(120_000)
    await page.goto('/', { waitUntil: 'domcontentloaded' })
    await ensurePromptReady(page, { timeout: 30_000 })

    const ownerToken = await issueSessionToken(page)
    await activateSessionToken(page, ownerToken)

    await runCommand(page, PERSONAL_COMMAND)
    await expect.poll(async () => historyCommands(page), { timeout: 20_000 })
      .toContain(PERSONAL_COMMAND)

    const suffix = Date.now().toString(36)
    const teamName = `Playwright Team ${suffix}`
    const teamSlug = `playwright-team-${suffix}`
    const teamId = await createTeamFromOptions(page, {
      name: teamName,
      slug: teamSlug,
      displayName: 'Owner',
    })
    const inviteCode = await createInviteFromOpenTeamDetail(page)
    expect(inviteCode).toMatch(/^tinv_/)
    await closeOptions(page)

    await switchScopeFromSelector(page, teamId)
    await expect(page.locator('#team-scope-label')).toHaveText(teamName)
    await page.setViewportSize({ width: 390, height: 844 })
    await expect(page.locator('#mobile-team-scope-label')).toHaveText(teamName)
    await page.reload({ waitUntil: 'domcontentloaded' })
    await ensurePromptReady(page, { timeout: 30_000 })
    await expect(page.locator('#mobile-team-scope-label')).toHaveText(teamName)
    await page.setViewportSize({ width: 1280, height: 720 })
    await expect(page.locator('#team-scope-label')).toHaveText(teamName)

    const runRequest = page.waitForRequest((request) => {
      const url = new URL(request.url())
      return request.method() === 'POST'
        && url.pathname === '/runs'
        && request.headers()['x-team-id'] === teamId
    })
    await runCommand(page, TEAM_COMMAND)
    await runRequest
    await expect.poll(async () => historyCommands(page), { timeout: 20_000 })
      .toContain(TEAM_COMMAND)
    expect(await historyCommands(page)).not.toContain(PERSONAL_COMMAND)
    const projectName = `Team Project ${suffix}`
    await expect(createProject(page, projectName)).resolves.toBeTruthy()

    await switchScopeFromSelector(page)
    await expect(page.locator('#team-scope-label')).toHaveText('Personal')
    await expect.poll(async () => historyCommands(page), { timeout: 20_000 })
      .toContain(PERSONAL_COMMAND)
    expect(await historyCommands(page)).not.toContain(TEAM_COMMAND)
    await switchScopeFromSelector(page, teamId)
    await expect(page.locator('#team-scope-label')).toHaveText(teamName)

    const invitedToken = await issueSessionToken(page)
    const context = await browser.newContext()
    const invitedPage = await context.newPage()
    try {
      await invitedPage.addInitScript((sessionToken) => {
        localStorage.setItem('session_token', sessionToken)
      }, invitedToken)
      await invitedPage.goto('/', { waitUntil: 'domcontentloaded' })
      await ensurePromptReady(invitedPage, { timeout: 30_000 })
      await joinTeamFromOptions(invitedPage, {
        code: inviteCode,
        displayName: 'Invited operator',
        teamName,
      })
      await closeOptions(invitedPage)
      await switchScopeFromSelector(invitedPage, teamId)
      await expect(invitedPage.locator('#team-scope-label')).toHaveText(teamName)
      await expect.poll(async () => historyCommands(invitedPage), { timeout: 20_000 })
        .toContain(TEAM_COMMAND)
      await expect.poll(async () => projectNames(invitedPage), { timeout: 20_000 })
        .toContain(projectName)

      await runCommand(invitedPage, INVITED_MEMBER_COMMAND)
      await expect.poll(async () => historyCommands(page), { timeout: 20_000 })
        .toContain(INVITED_MEMBER_COMMAND)
    } finally {
      await context.close()
    }
  })
})
