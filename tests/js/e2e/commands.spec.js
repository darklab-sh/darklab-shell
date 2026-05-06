import { test, expect } from '@playwright/test'
import { ensurePromptReady, runCommand, makeTestIp } from './helpers.js'

const CMD = 'hostname'
const TEST_IP = makeTestIp(64)

test.describe('command execution', () => {
  test.beforeEach(async ({ page }) => {
    await page.setExtraHTTPHeaders({ 'X-Forwarded-For': TEST_IP })
    await page.goto('/')
    await page.locator('#cmd').waitFor()
    await ensurePromptReady(page)
  })

  test('output appears in the terminal after running a command', async ({ page }) => {
    await runCommand(page, CMD)
    const output = page.locator('.tab-panel.active .output')
    await expect(output).toContainText('hostname')
  })

  test('HUD LAST EXIT shows 0 after a successful run and output has exit-ok line', async ({ page }) => {
    await runCommand(page, CMD)
    await expect(page.locator('.status-pill')).toHaveText('IDLE')
    await expect(page.locator('#hud-last-exit')).toHaveText('0')
    // The exit summary line has the exit-ok class
    await expect(page.locator('.tab-panel.active .output .exit-ok')).toBeVisible()
  })

  test('denied command shows [denied] in output and non-zero LAST EXIT', async ({ page }) => {
    // Shell operators are blocked client-side — no server round-trip needed
    await page.locator('#cmd').fill('ls -la && whoami')
    await page.keyboard.press('Enter')
    await expect(page.locator('.status-pill')).toHaveText('IDLE')
    await expect(page.locator('#hud-last-exit')).not.toHaveText('0')
    await expect(page.locator('#hud-last-exit')).not.toHaveText('—')
    await expect(page.locator('.tab-panel.active .output')).toContainText('[denied]')
  })
})

test.describe('interactive PTY command execution', () => {
  test.beforeEach(async ({ page }) => {
    await page.setExtraHTTPHeaders({ 'X-Forwarded-For': makeTestIp(65) })
    await page.addInitScript(() => {
      const originalFetch = window.fetch.bind(window)
      const encoder = new TextEncoder()
      let ptyController = null
      window.__ptyKillRequests = 0
      window.__ptyResizeRequests = 0

      const finishPtyRun = () => {
        if (!ptyController) return
        ptyController.enqueue(
          encoder.encode('data: {"type":"exit","code":143,"elapsed":0.1}\n\n'),
        )
        ptyController.close()
        ptyController = null
      }

      window.fetch = async (input, init) => {
        const url = typeof input === 'string' ? input : input.url
        const rawBody = typeof init?.body === 'string' ? init.body : ''

        if (url.endsWith('/config')) {
          const original = await originalFetch(input, init)
          const cfg = await original.clone().json()
          return new Response(JSON.stringify({
            ...cfg,
            interactive_pty_enabled: true,
            interactive_pty_commands: [{
              root: 'mtr',
              trigger_flag: '--interactive',
              default_rows: 12,
              default_cols: 80,
              requires_args: true,
              allow_input: true,
            }],
          }), {
            status: original.status,
            headers: { 'Content-Type': 'application/json' },
          })
        }

        if (url.endsWith('/history/active') && window.localStorage.getItem('__ptyExposeActiveRun') === '1') {
          return new Response(JSON.stringify({
            runs: [{
              run_id: 'pty-smoke-run',
              command: 'mtr --interactive darklab.sh',
              run_type: 'pty',
              started: '2026-05-06T00:00:00Z',
              has_live_owner: false,
              owner_stale: true,
            }],
          }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        }

        if (url.endsWith('/pty/runs') && init?.method === 'POST') {
          return new Response(JSON.stringify({
            run_id: 'pty-smoke-run',
            stream: '/pty/runs/pty-smoke-run/stream',
            command: 'mtr darklab.sh',
            interactive: true,
            rows: 12,
            cols: 80,
          }), {
            status: 202,
            headers: { 'Content-Type': 'application/json' },
          })
        }

        if (url.endsWith('/pty/runs/pty-smoke-run/snapshot')) {
          return new Response(JSON.stringify({
            run_id: 'pty-smoke-run',
            command: 'mtr --interactive darklab.sh',
            started: '2026-05-06T00:00:00Z',
            rows: 12,
            cols: 80,
            after_event_id: '1770000000000-2',
            entries: [{ text: 'snapshot hop darklab.sh', cls: '' }],
            snapshot_format: 'ansi',
            ansi_snapshot: '\u001b[0m\u001b[2J\u001b[Hsnapshot hop darklab.sh\u001b[1;1H',
            snapshot_truncated: false,
          }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        }

        if (url.includes('/pty/runs/pty-smoke-run/stream')) {
          const isResumeStream = url.includes('after=1770000000000-2')
          const body = new ReadableStream({
            start(controller) {
              ptyController = controller
              controller.enqueue(
                encoder.encode('data: {"type":"started","run_id":"pty-smoke-run"}\n\n'),
              )
              if (!isResumeStream) {
                controller.enqueue(
                  encoder.encode('data: {"type":"output","text":"smoke hop darklab.sh\\r\\n"}\n\n'),
                )
              }
            },
          })
          return new Response(body, {
            status: 200,
            headers: { 'Content-Type': 'text/event-stream' },
          })
        }

        if (url.endsWith('/pty/runs/pty-smoke-run/resize') && init?.method === 'POST') {
          window.__ptyResizeRequests += 1
          return new Response('{}', {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        }

        if (url.includes('/history/pty-smoke-run')) {
          return new Response(JSON.stringify({
            output_entries: [{ text: 'smoke hop darklab.sh', cls: '' }],
          }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        }

        if (url.endsWith('/kill') && init?.method === 'POST' && rawBody.includes('pty-smoke-run')) {
          window.__ptyKillRequests += 1
          finishPtyRun()
          return new Response('{}', {
            status: 200,
            headers: { 'Content-Type': 'application/json' },
          })
        }

        return originalFetch(input, init)
      }
    })
    await page.goto('/')
    await page.locator('#cmd').waitFor()
    await ensurePromptReady(page)
    await page.evaluate(() => {
      window.APP_CONFIG.interactive_pty_enabled = true
      window.APP_CONFIG.interactive_pty_commands = [{
        root: 'mtr',
        trigger_flag: '--interactive',
        default_rows: 12,
        default_cols: 80,
        requires_args: true,
        allow_input: true,
      }]
    })
  })

  test('starts, streams, resizes, and kills an interactive PTY command', async ({ page }) => {
    await page.locator('#cmd').fill('mtr --interactive darklab.sh')
    await page.keyboard.press('Enter')

    await expect(page.locator('#pty-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#pty-modal-status-label')).toHaveText('running')
    await expect(page.locator('#pty-modal-screen .xterm')).toBeVisible()
    await expect(page.locator('#pty-modal-screen')).toContainText('smoke hop darklab.sh')
    await expect.poll(() => page.evaluate(() => window.__ptyResizeRequests)).toBeGreaterThan(0)

    await page.locator('#pty-modal-kill').click()
    await expect(page.locator('#confirm-host')).toContainText('Kill the running process')
    await page.locator('#confirm-host [data-confirm-action-id="confirm"]').click()

    await expect.poll(() => page.evaluate(() => window.__ptyKillRequests)).toBe(1)
    await expect(page.locator('#pty-overlay')).toHaveClass(/u-hidden/)
    await expect(page.locator('.tab-panel.active .output')).toContainText('smoke hop darklab.sh')
  })

  test('reattaches an active interactive PTY after reload', async ({ page }) => {
    await page.locator('#cmd').fill('mtr --interactive darklab.sh')
    await page.keyboard.press('Enter')

    await expect(page.locator('#pty-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#pty-modal-screen')).toContainText('smoke hop darklab.sh')

    await page.evaluate(() => window.localStorage.setItem('__ptyExposeActiveRun', '1'))
    await page.reload()
    await page.locator('#cmd').waitFor()

    await expect(page.locator('#pty-overlay')).toHaveClass(/\bopen\b/)
    await expect(page.locator('#pty-modal-screen')).toContainText('snapshot hop darklab.sh')
    await expect(page.locator('.tab-panel.active .output')).toContainText('reattached to active interactive PTY')
  })
})
