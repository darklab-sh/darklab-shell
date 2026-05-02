import { test, expect } from '@playwright/test'
import {
  ensurePromptReady,
  makeTestIp,
  runCommand,
  setComposerValueForTest,
  waitForHistoryRuns,
} from './helpers.js'

const CMD = 'hostname'

function testScopedIp(testInfo, baseOffset = 0) {
  const key = `${testInfo.file}:${testInfo.title}`
  let sum = 0
  for (const ch of key) sum = (sum + ch.charCodeAt(0)) % 200
  return makeTestIp(baseOffset + sum)
}

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

async function answerTerminalConfirm(page, answer, expectedText) {
  await ensurePromptReady(page)
  await setComposerValueForTest(page, answer)
  await page.keyboard.press('Enter')
  await expect(page.locator('.tab-panel.active .output')).toContainText(expectedText, {
    timeout: 15_000,
  })
  await page.waitForFunction(
    () => (typeof hasPendingTerminalConfirm === 'function' ? !hasPendingTerminalConfirm() : true),
    { timeout: 15_000 },
  )
}

test.describe('session-token lifecycle', () => {
  test.beforeEach(async ({ page }, testInfo) => {
    await page.setExtraHTTPHeaders({ 'X-Forwarded-For': testScopedIp(testInfo, 330) })
    await page.goto('/')
    await page.evaluate(() => localStorage.clear())
    await page.reload()
    await ensurePromptReady(page)
  })

  test('generate persists the token across reload and clear returns to anonymous', async ({
    page,
  }) => {
    const anonymousSession = await storedAnonymousSessionId(page)

    await runCommand(page, 'session-token generate')
    await expect(page.locator('.tab-panel.active .output')).toContainText('session token generated')

    const token = await storedSessionToken(page)
    expect(token).toMatch(/^tok_[a-f0-9]{32}$/)
    expect(await currentSessionId(page)).toBe(token)

    await page.reload()
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
    await runCommand(page, CMD)
    await waitForHistoryRuns(page, 1)
    const token = await issueSessionToken(page)

    await runCommand(page, `session-token set ${token}`)
    await expect(page.locator('.tab-panel.active .output')).toContainText(
      'migrate history, files, workflows, and recent domains to this session token?',
    )
    await answerTerminalConfirm(page, 'no', 'History, file, workflow, and recent-domain migration skipped.')

    expect(await storedSessionToken(page)).toBe(token)
    expect(await currentSessionId(page)).toBe(token)
    expect(await historyCommands(page)).not.toContain(CMD)
  })

  test('set migration carries history, starred commands, and workspace files', async ({
    page,
  }) => {
    await runCommand(page, CMD)
    await waitForHistoryRuns(page, 1)
    await starCommand(page, CMD)
    await writeWorkspaceFile(page, 'nested/token-migration.txt', 'migrated file')
    const token = await issueSessionToken(page)

    await runCommand(page, `session-token set ${token}`)
    await expect(page.locator('.tab-panel.active .output')).toContainText(
      'migrate history, files, workflows, and recent domains to this session token?',
    )
    await answerTerminalConfirm(page, 'yes', 'migrated —')

    expect(await storedSessionToken(page)).toBe(token)
    await expect.poll(async () => historyCommands(page)).toContain(CMD)
    await expect.poll(async () => starredCommands(page)).toContain(CMD)
    await expect.poll(async () => workspaceFilePaths(page)).toContain(
      'nested/token-migration.txt',
    )
  })

  test('recent domain autocomplete follows the active session token across browser contexts', async ({
    page,
    browser,
  }, testInfo) => {
    const token = await issueSessionToken(page)
    await runCommand(page, `session-token set ${token}`)
    await expect.poll(async () => currentSessionId(page)).toBe(token)

    await runCommand(page, 'ping -c 1 darklab.sh')
    await expect.poll(async () => page.evaluate(async () => {
      const resp = await apiFetch('/session/recent-domains')
      const data = await resp.json()
      return data.domains || []
    })).toContain('darklab.sh')

    const context = await browser.newContext({
      extraHTTPHeaders: { 'X-Forwarded-For': testScopedIp(testInfo, 390) },
    })
    const otherPage = await context.newPage()
    try {
      await otherPage.goto('/')
      await ensurePromptReady(otherPage)
      await runCommand(otherPage, `session-token set ${token}`)
      await expect.poll(async () => currentSessionId(otherPage)).toBe(token)
      await expect.poll(async () => otherPage.evaluate(() => (
        typeof _readRecentDomains === 'function' ? _readRecentDomains() : []
      ))).toContain('darklab.sh')

      await expect.poll(async () => otherPage.evaluate(() => (
        typeof getAutocompleteMatches === 'function'
          ? getAutocompleteMatches('ping ', 5).map(item => item.value)
          : []
      ))).toContain('darklab.sh')
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
