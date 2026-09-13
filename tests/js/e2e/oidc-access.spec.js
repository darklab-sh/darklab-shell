// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { readFileSync } from 'fs'
import { resolve } from 'path'

import { test, expect } from '@playwright/test'

import { ensurePromptReady, openRailAction } from './helpers.js'


function operatorCredential() {
  const directory = process.env.PW_E2E_SECRET_DIR
  if (!directory) throw new Error('PW_E2E_SECRET_DIR is not set')
  return readFileSync(resolve(directory, 'oidc.credential'), 'utf8').trim()
}


async function openAccess(page) {
  await openRailAction(page, 'options')
  await page.locator('#options-tab-access').click()
  await expect(page.locator('#options-access-oidc-section')).toBeVisible()
}


test.describe('managed sign-in with a local HTTPS provider', () => {
  test('links after both proofs, unlinks with revocation, then signs in through the provider', async ({ page, context }) => {
    await page.goto('/')
    await expect(page).toHaveURL(/\/auth\/sign-in\?next=/)
    const providerGap = await page.locator('.restricted-sign-in-card').evaluate(card => {
      const details = card.querySelector('p')
      const provider = card.querySelector('.restricted-sign-in-provider')
      return provider.getBoundingClientRect().top - details.getBoundingClientRect().bottom
    })
    expect(providerGap).toBeGreaterThanOrEqual(16)
    await page.getByLabel('Access credential').fill(operatorCredential())
    await Promise.all([
      page.waitForURL(url => url.pathname === '/'),
      page.getByRole('button', { name: 'Sign in', exact: true }).click(),
    ])
    await ensurePromptReady(page)
    const original = await page.evaluate(async () => (await (await apiFetch('/auth/principal')).json()).principal.id)

    await openAccess(page)
    await expect(page.locator('#options-access-oidc-link')).toBeVisible()
    await Promise.all([
      page.waitForResponse(response => new URL(response.url()).pathname === '/auth/oidc/callback'),
      page.locator('#options-access-oidc-link').click(),
    ])
    await expect.poll(async () => {
      const response = await page.request.get('/auth/oidc/identity')
      return response.ok() && (await response.json()).linked
    }).toBe(true)
    await page.goto('/')
    await ensurePromptReady(page)
    await openAccess(page)
    await expect(page.locator('#options-access-oidc-unlink')).toBeVisible()
    await page.locator('#options-access-oidc-unlink').click()
    await page.locator('#confirm-host [data-confirm-action-id="unlink"]').click()
    await expect(page).toHaveURL(/\/auth\/sign-in/)

    await page.getByRole('link', { name: 'Continue with identity provider' }).click()
    await page.waitForURL(url => url.pathname === '/')
    await ensurePromptReady(page)
    const authentication = await page.evaluate(async () => (await (await apiFetch('/auth/principal')).json()).authentication)
    expect(authentication.credential_type).toBe('oidc')
    expect(authentication.credential_id).toBe('')
    await expect(page.locator('#hud-session')).toHaveText('OIDC')
    await openAccess(page)
    await expect(page.locator('#options-access-summary')).toHaveText('Authenticated workspace')
    expect(await page.evaluate(() => document.cookie)).not.toContain('darklab_browser_session=')
    const cookie = (await context.cookies()).find(item => item.name === 'darklab_browser_session')
    expect(cookie).toEqual(expect.objectContaining({ httpOnly: true, secure: true, sameSite: 'Strict' }))
    const providerPrincipal = await page.evaluate(async () => (await (await apiFetch('/auth/principal')).json()).principal.id)
    expect(providerPrincipal).not.toBe(original)
  })

  test('shows a safe error when the provider declines authorization', async ({ page }) => {
    let intercepted = 0
    await page.route(url => url.pathname === '/auth/oidc/start', async route => {
      intercepted += 1
      const response = await route.fetch({ maxRedirects: 0 })
      const state = new URL(response.headers().location).searchParams.get('state')
      const redirect = new URL('/auth/oidc/callback', route.request().url())
      redirect.searchParams.set('state', state)
      redirect.searchParams.set('error', 'access_denied')
      return route.fulfill({ response, status: 302, headers: { ...response.headers(), location: redirect.href } })
    })
    await page.goto('/')
    await page.getByRole('link', { name: 'Continue with identity provider' }).click()
    expect(intercepted).toBe(1)
    await expect(page.getByRole('alert')).toContainText("Provider sign-in couldn't be completed")
    await expect(page).toHaveURL(/\/auth\/sign-in\?oidc_error=1/)
  })
})
