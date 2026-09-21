// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { readFileSync, existsSync } from 'fs'
import { resolve } from 'path'
import { execFileSync } from 'child_process'
import { expect } from '@playwright/test'

export function controlOperator(action, slot, principal) {
  const python = existsSync('.venv/bin/python') ? resolve('.venv/bin/python') : 'python3'
  return execFileSync(python, [resolve('scripts/test-support/playwright/operator_fixture.py'), action,
    resolve(process.env.PW_E2E_SECRET_DIR, `${slot}.runtime.json`), principal], { stdio: 'pipe', encoding: 'utf8' })
}

export async function withOperatorCapture(page, testInfo, capture, { route = '/diag', themeName } = {}) {
  const { operatorBaseURL, operatorSlot } = testInfo.project.metadata
  const credential = readFileSync(resolve(process.env.PW_E2E_SECRET_DIR, `${operatorSlot}.credential`), 'utf8').trim()
  await page.context().clearCookies()
  if (themeName) await page.context().addCookies([{
    name: 'pref_theme_name', value: themeName.replace(/\.ya?ml$/i, '') + '.yaml', url: operatorBaseURL,
  }])
  const target = new URL(route, operatorBaseURL).href
  await page.goto(target, { waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
  await page.getByLabel('Access credential').fill(credential)
  await page.getByRole('button', { name: 'Sign in', exact: true }).click()
  await page.waitForURL(target, { waitUntil: 'domcontentloaded' })
  const identity = await page.evaluate(async () => {
    const response = await fetch('/auth/principal', { credentials: 'same-origin' })
    return { status: response.status, body: await response.json() }
  })
  expect(identity.status).toBe(200)
  const { principal } = identity.body
  controlOperator('grant', operatorSlot, principal.id)
  try {
    const response = await page.goto(target, { waitUntil: 'domcontentloaded' })
    expect(response.status()).toBe(200)
    await expect(page.locator('body.diag-page')).toBeVisible()
    await capture()
  } finally {
    controlOperator('revoke', operatorSlot, principal.id)
    await page.context().clearCookies()
  }
}
