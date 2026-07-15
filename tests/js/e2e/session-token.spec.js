// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { test, expect } from '@playwright/test'
import {
  ensureAutocompleteReady,
  ensurePromptReady,
  runCommand,
  setComposerValueForTest,
  waitForHistoryRuns,
} from './helpers.js'

const CMD = 'hostname'

async function currentSessionId(page) {
  return page.evaluate(() => SESSION_ID)
}

async function storedSessionToken(page) {
  return page.evaluate(() => localStorage.getItem('session_token'))
}

async function storedAnonymousSessionId(page) {
  return page.evaluate(() => localStorage.getItem('session_id'))
}

async function issueSessionToken(page) {
  return page.evaluate(async () => {
    const resp = await apiFetch('/session/token/generate')
    if (!resp.ok) throw new Error(`token generate failed: ${resp.status}`)
    const data = await resp.json()
    return data.session_token
  })
}

async function historyCommands(page) {
  return page.evaluate(async () => {
    const resp = await apiFetch('/history?page_size=50&type=runs')
    if (!resp.ok) throw new Error(`history failed: ${resp.status}`)
    const data = await resp.json()
    return (data.runs || []).map(run => run.command)
  })
}

async function starredCommands(page) {
  return page.evaluate(async () => {
    const resp = await apiFetch('/session/starred')
    if (!resp.ok) throw new Error(`starred failed: ${resp.status}`)
    const data = await resp.json()
    return data.commands || []
  })
}

async function workspaceFilePaths(page) {
  return page.evaluate(async () => {
    const resp = await apiFetch('/workspace/files')
    if (!resp.ok) throw new Error(`workspace files failed: ${resp.status}`)
    const data = await resp.json()
    return (data.files || []).map(file => file.path)
  })
}

async function writeWorkspaceFile(page, path, text) {
  await page.evaluate(
    async ({ filePath, fileText }) => {
      const resp = await apiFetch('/workspace/files', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: filePath, text: fileText }),
      })
      if (!resp.ok) throw new Error(`workspace write failed: ${resp.status}`)
    },
    { filePath: path, fileText: text },
  )
}

async function starCommand(page, command) {
  await page.evaluate(async (cmd) => {
    const resp = await apiFetch('/session/starred', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command: cmd }),
    })
    if (!resp.ok) throw new Error(`star failed: ${resp.status}`)
  }, command)
}

async function answerTerminalConfirm(page, answer, expectedText, { timeout = 30_000 } = {}) {
  await ensurePromptReady(page, { timeout })
  await setComposerValueForTest(page, answer, { waitForAutocomplete: false })
  await page.keyboard.press('Enter')
  await expect(page.locator('.tab-panel.active .output')).toContainText(expectedText, {
    timeout,
  })
  await page.waitForFunction(
    () => (typeof hasPendingTerminalConfirm === 'function' ? !hasPendingTerminalConfirm() : true),
    undefined,
    { timeout },
  )
}

test.describe('session-token lifecycle', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/', { waitUntil: 'domcontentloaded' })
    await page.evaluate(() => localStorage.clear())
    await page.reload({ waitUntil: 'domcontentloaded' })
    await ensurePromptReady(page)
  })

  test('generate persists the token across reload and clear returns to anonymous', async ({
    page,
  }) => {
    test.setTimeout(60_000)
    const anonymousSession = await storedAnonymousSessionId(page)

    await runCommand(page, 'session-token generate')
    await expect(page.locator('.tab-panel.active .output')).toContainText('session token generated')

    const token = await storedSessionToken(page)
    expect(token).toMatch(/^tok_[a-f0-9]{32}$/)
    expect(await currentSessionId(page)).toBe(token)

    await page.reload({ waitUntil: 'domcontentloaded' })
    await ensurePromptReady(page)
    expect(await storedSessionToken(page)).toBe(token)
    expect(await currentSessionId(page)).toBe(token)

    await runCommand(page, 'session-token clear')
    await expect(page.locator('.tab-panel.active .output')).toContainText(
      'clear the active session token',
    )
    await answerTerminalConfirm(page, 'yes', 'session token cleared')

    expect(await storedSessionToken(page)).toBeNull()
    expect(await currentSessionId(page)).toBe(anonymousSession)
  })

  test('set can skip migration without moving anonymous history', async ({ page }) => {
    test.setTimeout(60_000)
    await runCommand(page, CMD)
    await waitForHistoryRuns(page, 1)
    const token = await issueSessionToken(page)

    await runCommand(page, `session-token set ${token}`)
    await expect(page.locator('.tab-panel.active .output')).toContainText(
      'migrate history, files, workflows, and recent values to this session token?',
    )
    await answerTerminalConfirm(
      page,
      'no',
      'History, file, workflow, and recent-value migration skipped.',
      { timeout: 45_000 },
    )

    expect(await storedSessionToken(page)).toBe(token)
    expect(await currentSessionId(page)).toBe(token)
    expect(await historyCommands(page)).not.toContain(CMD)
  })

  test('set migration carries history, starred commands, and workspace files', async ({
    page,
  }) => {
    test.setTimeout(60_000)
    await runCommand(page, CMD)
    await waitForHistoryRuns(page, 1)
    await starCommand(page, CMD)
    await writeWorkspaceFile(page, 'nested/token-migration.txt', 'migrated file')
    const token = await issueSessionToken(page)

    await runCommand(page, `session-token set ${token}`)
    await expect(page.locator('.tab-panel.active .output')).toContainText(
      'migrate history, files, workflows, and recent values to this session token?',
    )
    await answerTerminalConfirm(page, 'yes', 'migrated —')

    expect(await storedSessionToken(page)).toBe(token)
    await expect.poll(async () => historyCommands(page)).toContain(CMD)
    await expect.poll(async () => starredCommands(page)).toContain(CMD)
    await expect.poll(async () => workspaceFilePaths(page)).toContain(
      'nested/token-migration.txt',
    )
  })

  test('recent target autocomplete follows the active session token across browser contexts', async ({
    page,
    browser,
  }) => {
    test.setTimeout(90_000)
    const token = await issueSessionToken(page)
    await runCommand(page, `session-token set ${token}`)
    await expect.poll(async () => currentSessionId(page)).toBe(token)
    await ensureAutocompleteReady(page, { timeout: 30_000 })

    await page.evaluate(async () => {
      await apiFetch('/session/recent-values', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ values: [{ kind: 'domain', value: 'darklab.sh' }] }),
      })
    })
    await runCommand(page, 'ping -c 1 -W 1 192.0.2.1')
    await page.evaluate(async () => {
      if (typeof flushRecentValues === 'function') await flushRecentValues()
    })
    await expect.poll(async () => page.evaluate(async () => {
      const resp = await apiFetch('/session/recent-values')
      const data = await resp.json()
      return (data.values && data.values.domain) || []
    })).toContain('darklab.sh')

    const context = await browser.newContext()
    const otherPage = await context.newPage()
    try {
      await otherPage.addInitScript((sessionToken) => {
        localStorage.setItem('session_token', sessionToken)
      }, token)
      await otherPage.goto('/', { waitUntil: 'domcontentloaded' })
      await ensurePromptReady(otherPage, { timeout: 30_000, waitForAutocomplete: true })
      await expect.poll(async () => currentSessionId(otherPage)).toBe(token)
      await ensureAutocompleteReady(otherPage, { timeout: 30_000 })
      await expect.poll(async () => otherPage.evaluate(async () => {
        if (typeof loadRecentValues === 'function') await loadRecentValues()
        return typeof _readRecentValues === 'function' ? _readRecentValues('domain') : []
      }), {
        timeout: 15_000,
        intervals: [250, 500, 1000],
      }).toContain('darklab.sh')

      await expect.poll(async () => otherPage.evaluate(() => (
        typeof getAutocompleteMatches === 'function'
          && typeof acContextRegistry !== 'undefined'
          && acContextRegistry.ping
          ? getAutocompleteMatches('ping ', 5).map(item => item.value)
          : []
      )), {
        timeout: 15_000,
        intervals: [250, 500, 1000],
      }).toContain('darklab.sh')
    } finally {
      await context.close()
    }
  })

  test('set rejects unknown tok tokens before switching identity', async ({ page }) => {
    const anonymousSession = await currentSessionId(page)

    await runCommand(page, 'session-token set tok_00000000000000000000000000000000')

    await expect(page.locator('.tab-panel.active .output')).toContainText(
      'session token not found',
    )
    expect(await storedSessionToken(page)).toBeNull()
    expect(await currentSessionId(page)).toBe(anonymousSession)
  })

  test('revoke active token clears browser storage and reverts to anonymous', async ({
    page,
  }) => {
    const anonymousSession = await storedAnonymousSessionId(page)
    await runCommand(page, 'session-token generate')
    await expect(page.locator('.tab-panel.active .output')).toContainText('session token generated')
    const token = await storedSessionToken(page)

    await runCommand(page, `session-token revoke ${token}`)
    await expect(page.locator('.tab-panel.active .output')).toContainText('revoke session token')
    await answerTerminalConfirm(page, 'yes', 'session token revoked')

    expect(await storedSessionToken(page)).toBeNull()
    expect(await currentSessionId(page)).toBe(anonymousSession)
  })
})
