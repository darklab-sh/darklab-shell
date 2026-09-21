// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { readFileSync } from 'fs'
import { resolve } from 'path'

import { test, expect } from '@playwright/test'

import { ensurePromptReady, keepBrowserWorkspace, openRailAction } from './helpers.js'

// Each case signs in, checks every protected surface, writes personal and Team
// data, and verifies recovery across navigations on the isolated CI servers.
test.setTimeout(120_000)

const protectedReads = [
  '/config', '/projects', '/atlas', '/history', '/workspace/files',
  '/watchers', '/schedules', '/workflows', '/session/secrets',
  '/session/notification-channels', '/session/notification-events',
]

function profileFor(projectName) {
  if (projectName.startsWith('chromium-restricted')) return 'token_required'
  if (projectName === 'chromium-oidc-required') return 'oidc_required'
  if (projectName.startsWith('chromium-oidc')) return 'mixed'
  return 'open'
}

function bootstrapCredential(profile) {
  const directory = process.env.PW_E2E_SECRET_DIR
  if (!directory) throw new Error('PW_E2E_SECRET_DIR is not set')
  const postgresSlot = Boolean(process.env.PW_E2E_POSTGRES_DSN)
  const slot = profile === 'token_required'
    ? (postgresSlot ? 'pg-restricted' : 'restricted-qualification')
    : (postgresSlot ? 'pg-mixed' : 'oidc-qualification')
  return readFileSync(resolve(directory, `${slot}.credential`), 'utf8').trim()
}

async function readStatuses(page) {
  return page.evaluate(async paths => {
    const entries = []
    for (const path of paths) entries.push([path, (await apiFetch(path)).status])
    return Object.fromEntries(entries)
  }, protectedReads)
}

async function logOutFromMenu(page) {
  const mobile = await page.locator('#hamburger-btn').isVisible();
  const trigger = page.locator(mobile ? '#hamburger-btn' : '#rail-more-btn');
  const action = page.locator(mobile
    ? '#mobile-menu-sheet [data-menu-action="logout"]'
    : '#rail-more-menu [data-action="logout"]');
  const open = async () => {
    if (mobile) {
      await trigger.click();
      await expect(action).toBeVisible();
      expect((await action.boundingBox()).height).toBeGreaterThanOrEqual(40);
      await action.click();
    } else {
      await trigger.focus();
      await page.keyboard.press('Enter');
      await expect(page.locator('#rail-more-menu [data-action="options"]')).toBeFocused();
      await page.keyboard.press('Tab');
      await expect(action).toBeFocused();
      await page.keyboard.press('Enter');
    }
    await expect(page.locator('#options-overlay')).not.toHaveClass(/\bopen\b/);
    await expect(page.locator('#confirm-host')).toContainText('Your workspace stays saved');
  };
  await open();
  await page.keyboard.press('Escape');
  await expect(trigger).toBeFocused();
  expect((await readStatuses(page))['/projects']).toBe(200);
  await open();
  await page.locator('#confirm-host').getByRole('button', { name: 'Log out', exact: true }).click();
}

async function qualifyPersonalAndTeamScope(page) {
  return page.evaluate(async () => {
    const suffix = crypto.randomUUID().slice(0, 8)
    const jsonHeaders = { 'Content-Type': 'application/json' }
    const personal = await apiFetch('/projects', {
      method: 'POST', headers: jsonHeaders,
      body: JSON.stringify({ name: `Profile personal ${suffix}` }),
    })
    if (personal.status !== 201) throw new Error(`personal project failed: ${personal.status}`)
    const personalId = (await personal.json()).project.id
    const assessments = await apiFetch(`/projects/${personalId}/assessments`)
    if (assessments.status !== 200) throw new Error(`assessment read failed: ${assessments.status}`)

    const path = `profile-${suffix}.txt`
    const written = await apiFetch('/workspace/files', {
      method: 'POST', headers: jsonHeaders,
      body: JSON.stringify({ path, text: 'profile qualification\n' }),
    })
    if (written.status !== 200) throw new Error(`workspace file write failed: ${written.status}`)
    const read = await apiFetch(`/workspace/files/read?path=${encodeURIComponent(path)}`)
    if (read.status !== 200 || (await read.json()).text !== 'profile qualification\n') {
      throw new Error(`workspace file read failed: ${read.status}`)
    }

    const createdTeam = await apiFetch('/session/teams', {
      method: 'POST', headers: jsonHeaders,
      body: JSON.stringify({
        name: `Profile team ${suffix}`, slug: `profile-team-${suffix}`, display_name: 'Qualification owner',
      }),
    })
    if (createdTeam.status !== 201) throw new Error(`team create failed: ${createdTeam.status}`)
    const teamId = (await createdTeam.json()).team.id
    const teamHeaders = { ...jsonHeaders, 'X-Team-ID': teamId }
    const teamProject = await apiFetch('/projects', {
      method: 'POST', headers: teamHeaders,
      body: JSON.stringify({ name: `Profile team project ${suffix}` }),
    })
    if (teamProject.status !== 201) throw new Error(`team project failed: ${teamProject.status}`)
    const teamProjectId = (await teamProject.json()).project.id
    const teamList = await apiFetch('/projects', { headers: { 'X-Team-ID': teamId } })
    const personalList = await apiFetch('/projects')
    if (teamList.status !== 200 || personalList.status !== 200) {
      throw new Error(`project scope read failed: ${teamList.status}/${personalList.status}`)
    }
    const teamIds = (await teamList.json()).projects.map(project => project.id)
    const personalIds = (await personalList.json()).projects.map(project => project.id)
    if (!teamIds.includes(teamProjectId) || teamIds.includes(personalId)
        || !personalIds.includes(personalId) || personalIds.includes(teamProjectId)) {
      throw new Error('personal and team project scopes overlapped')
    }
    return { personalId, teamId, teamProjectId }
  })
}

// Every profile/backend/viewport proves that command recall is off the prompt
// readiness path and that a late response preserves a draft already being typed.
async function prepareStartupProbe(page) {
  let release, requested = false
  const pending = new Promise(resolve => { release = resolve })
  const handler = async route => {
    requested = true
    await pending
    await route.fulfill({ json: { runs: [{ command: 'late startup recall' }] } })
  }
  await page.route('**/history/commands?*', handler)
  return async () => {
    try {
      await ensurePromptReady(page)
      await expect.poll(() => requested).toBe(true)
      const input = page.locator(await page.locator('#hamburger-btn').isVisible() ? '#mobile-cmd' : '#cmd')
      await input.fill('draft while recall is loading')
      release()
      await page.waitForFunction(() => window.APP_STATE_API.getState().cmdHistory.includes('late startup recall'))
      await expect(input).toHaveValue('draft while recall is loading')
      await input.fill('')
    } finally {
      release()
      await page.unroute('**/history/commands?*', handler)
    }
  }
}

async function qualifyBrowser(page, context, projectName) {
  const profile = profileFor(projectName)
  const startupProbe = await prepareStartupProbe(page)
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  if (profile === 'open') {
    await startupProbe()
    await expect(page.locator('#hud-session')).toHaveText('ANON')
    await expect(page.locator('[data-action="logout"]')).toHaveClass(/\bu-hidden\b/)
    await expect(page.locator('[data-menu-action="logout"]')).toHaveClass(/\bu-hidden\b/)
    expect((await readStatuses(page))['/projects']).toBe(200)
    const { secret: credential } = await keepBrowserWorkspace(page, { returnCredential: true })
    await expect(page.locator('#hud-session')).toContainText('crd_')
    expect((await readStatuses(page))['/projects']).toBe(200)
    const scope = await qualifyPersonalAndTeamScope(page)
    await logOutFromMenu(page)
    await expect(page).toHaveURL(/\/auth\/sign-in/)
    await page.getByRole('button', { name: 'Continue anonymously' }).click()
    await ensurePromptReady(page)
    await expect(page.locator('#hud-session')).toHaveText('ANON')
    expect(await page.evaluate(() => localStorage.getItem('access_credential'))).toBeNull()
    await expect(page.locator('[data-action="logout"]')).toHaveClass(/\bu-hidden\b/)
    await expect(page.locator('[data-menu-action="logout"]')).toHaveClass(/\bu-hidden\b/)
    expect(await page.evaluate(async id => (await apiFetch(`/projects/${id}`)).status, scope.personalId)).toBe(404)
    const kept = await page.request.get(`/projects/${scope.personalId}`, { headers: { 'X-Darklab-Credential': credential } })
    expect(kept.status()).toBe(200)
    await page.reload({ waitUntil: 'domcontentloaded' })
    await ensurePromptReady(page)
    await expect(page.locator('#hud-session')).toHaveText('ANON')
    return
  }

  await expect(page).toHaveURL(/\/auth\/sign-in\?next=/)
  await expect(page.getByLabel('Access credential')).toHaveCount(profile === 'oidc_required' ? 0 : 1)
  const providerLink = page.getByRole('link', { name: 'Continue with identity provider' })
  if (profile === 'token_required') await expect(providerLink).toHaveCount(0)
  else await expect(providerLink).toBeVisible()

  for (const path of protectedReads) {
    const response = await page.request.get(path)
    expect(response.status(), `${profile}: ${path}`).toBe(401)
  }

  if (profile === 'oidc_required') {
    await page.getByRole('link', { name: 'Continue with identity provider' }).click()
  } else {
    await page.getByLabel('Access credential').fill(bootstrapCredential(profile))
    await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  }
  // Predicate URL assertions also wait for full load on the assertion timeout.
  // Give navigation its own budget, then check that the shell is usable.
  await page.waitForURL(url => url.pathname === '/', { waitUntil: 'domcontentloaded', timeout: 30_000 })
  await startupProbe()

  if (profile === 'oidc_required') {
    const mobile = await page.locator('#hamburger-btn').isVisible()
    if (mobile) {
      await page.locator('#hamburger-btn').click()
      await page.locator('#mobile-menu-sheet [data-menu-action="access"]').click()
    } else {
      await openRailAction(page, 'options')
      await page.locator('#options-tab-access').click()
    }
    await page.locator('#options-access-add-btn').click()
    const editor = page.locator('#options-access-editor')
    await expect(editor.getByLabel('Credential type')).toHaveValue('pat')
    await expect(editor.locator('option[value="portable"]')).toHaveCount(0)
    await editor.getByLabel('Label', { exact: true }).fill('Provider workspace CLI')
    const issued = page.waitForResponse(response => new URL(response.url()).pathname === '/auth/credentials'
      && response.request().method() === 'POST')
    await editor.getByRole('button', { name: 'Save', exact: true }).click()
    expect((await issued).status()).toBe(201)
    await expect(page.locator('#options-access-reveal')).toBeVisible()
    await page.locator('#options-access-reveal').getByRole('button', { name: 'Close', exact: true }).click()
    if (mobile) await page.locator('#options-overlay').click({ position: { x: 5, y: 5 } })
    else await page.getByRole('button', { name: 'Close options', exact: true }).click()
    await expect(page.locator('#options-overlay')).not.toHaveClass(/\bopen\b/)
  }

  if (profile !== 'oidc_required') {
    const credentialAbsent = await page.evaluate(secret =>
      ![document.documentElement.outerHTML, JSON.stringify(localStorage), JSON.stringify(sessionStorage), document.cookie]
        .some(value => value.includes(secret)), bootstrapCredential(profile))
    expect(credentialAbsent).toBe(true)
  }

  const principal = await page.evaluate(async () => (await (await apiFetch('/auth/principal')).json()).authentication)
  expect(principal.credential_type).toBe(profile === 'oidc_required' ? 'oidc' : 'portable')
  const sessionCookie = (await context.cookies()).find(cookie => cookie.name === 'darklab_browser_session')
  expect(sessionCookie).toEqual(expect.objectContaining({ httpOnly: true, secure: true, sameSite: 'Strict' }))
  expect(await page.evaluate(() => document.cookie)).not.toContain('darklab_browser_session=')

  const statuses = await readStatuses(page)
  for (const [path, status] of Object.entries(statuses)) expect(status, `${profile}: ${path}`).toBe(200)
  await qualifyPersonalAndTeamScope(page)
  const rotatedCookie = (await context.cookies()).find(cookie => cookie.name === 'darklab_browser_session')
  expect(rotatedCookie?.value).not.toBe(sessionCookie.value)
  await page.reload({ waitUntil: 'domcontentloaded' })
  await page.waitForURL(url => url.pathname === '/', { waitUntil: 'domcontentloaded', timeout: 30_000 })
  await ensurePromptReady(page)
  expect((await readStatuses(page))['/projects']).toBe(200)

  const loggedOut = page.waitForResponse(response => new URL(response.url()).pathname === '/auth/logout')
  await logOutFromMenu(page)
  expect((await loggedOut).status()).toBe(204)
  expect((await page.request.get('/projects')).status()).toBe(401)
  await expect(page).toHaveURL(/\/auth\/sign-in\?next=/)
  if (profile === 'mixed') {
    await page.getByRole('link', { name: 'Continue with identity provider' }).click()
    await page.waitForURL(url => url.pathname === '/', { waitUntil: 'domcontentloaded', timeout: 30_000 })
    await ensurePromptReady(page)
    const providerAuthentication = await page.evaluate(async () =>
      (await (await apiFetch('/auth/principal')).json()).authentication)
    expect(providerAuthentication.credential_type).toBe('oidc')
    expect((await readStatuses(page))['/projects']).toBe(200)
    await logOutFromMenu(page)
    await expect(page).toHaveURL(/\/auth\/sign-in\?next=/)
  }
}

test('desktop profile gate, sign-in, protected reads, and session recovery', async ({ page, context }, testInfo) => {
  await qualifyBrowser(page, context, testInfo.project.name)
})

test.describe('mobile profile qualification', () => {
  test.use({ viewport: { width: 375, height: 812 }, hasTouch: true, isMobile: true })

  test('sign-in and protected reads stay available at mobile width', async ({ page, context }, testInfo) => {
    await qualifyBrowser(page, context, testInfo.project.name)
    const width = await page.evaluate(() => ({ document: document.documentElement.scrollWidth, viewport: innerWidth }))
    expect(width.document).toBeLessThanOrEqual(width.viewport)
  })
})
