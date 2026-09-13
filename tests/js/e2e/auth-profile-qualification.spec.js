// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { readFileSync } from 'fs'
import { resolve } from 'path'

import { test, expect } from '@playwright/test'

import { ensurePromptReady, keepBrowserWorkspace } from './helpers.js'

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

async function qualifyBrowser(page, context, projectName) {
  const profile = profileFor(projectName)
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  if (profile === 'open') {
    await ensurePromptReady(page)
    await expect(page.locator('#hud-session')).toHaveText('ANON')
    expect((await readStatuses(page))['/projects']).toBe(200)
    await keepBrowserWorkspace(page)
    await expect(page.locator('#hud-session')).toContainText('crd_')
    expect((await readStatuses(page))['/projects']).toBe(200)
    await qualifyPersonalAndTeamScope(page)
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
  await expect(page).toHaveURL(url => url.pathname === '/')
  await ensurePromptReady(page)

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
  await ensurePromptReady(page)
  await expect(page).toHaveURL(url => url.pathname === '/')
  expect((await readStatuses(page))['/projects']).toBe(200)

  const logoutStatus = await page.evaluate(async () => (await apiFetch('/auth/logout', { method: 'POST' })).status)
  expect(logoutStatus).toBe(204)
  expect((await readStatuses(page))['/projects']).toBe(401)
  if (profile === 'mixed') {
    await page.goto('/', { waitUntil: 'domcontentloaded' })
    await expect(page).toHaveURL(/\/auth\/sign-in\?next=/)
    await page.getByRole('link', { name: 'Continue with identity provider' }).click()
    await expect(page).toHaveURL(url => url.pathname === '/')
    await ensurePromptReady(page)
    const providerAuthentication = await page.evaluate(async () =>
      (await (await apiFetch('/auth/principal')).json()).authentication)
    expect(providerAuthentication.credential_type).toBe('oidc')
    expect((await readStatuses(page))['/projects']).toBe(200)
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
