#!/usr/bin/env node

import { chromium } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(__dirname, '..', '..')
const AUTOCOMPLETE_FILE = path.join(ROOT, 'app', 'conf', 'autocomplete.yaml')
const DEFAULT_OUT_DIR = path.join('/tmp', 'darklab-shell-container-smoke-test-corpus')

function parseArgs(argv) {
  const args = {
    baseUrl: process.env.AUTOCOMPLETE_BASE_URL || 'http://localhost:5001',
    outDir: process.env.AUTOCOMPLETE_OUT_DIR || DEFAULT_OUT_DIR,
    commandsFile: '',
    headed: false,
    clearBetween: true,
    resumeFromCommand: '',
    pauseMs: Number(process.env.AUTOCOMPLETE_PAUSE_MS || 500),
    settleMs: Number(process.env.AUTOCOMPLETE_SETTLE_MS || 2500),
    stableMs: Number(process.env.AUTOCOMPLETE_STABLE_MS || 1000),
    commandTimeoutMs: Number(process.env.AUTOCOMPLETE_COMMAND_TIMEOUT_MS || 300_000),
    saveTimeoutMs: Number(process.env.AUTOCOMPLETE_SAVE_TIMEOUT_MS || 10_000),
    toastTimeoutMs: Number(process.env.AUTOCOMPLETE_TOAST_TIMEOUT_MS || 2_000),
    keepBrowserOpen: false,
  }

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i]
    if (arg === '--base-url' && argv[i + 1]) {
      args.baseUrl = argv[++i]
      continue
    }
    if (arg === '--out-dir' && argv[i + 1]) {
      args.outDir = argv[++i]
      continue
    }
    if (arg === '--commands-file' && argv[i + 1]) {
      args.commandsFile = argv[++i]
      continue
    }
    if (arg === '--pause-ms' && argv[i + 1]) {
      args.pauseMs = Number(argv[++i])
      continue
    }
    if (arg === '--settle-ms' && argv[i + 1]) {
      args.settleMs = Number(argv[++i])
      continue
    }
    if (arg === '--stable-ms' && argv[i + 1]) {
      args.stableMs = Number(argv[++i])
      continue
    }
    if (arg === '--command-timeout-ms' && argv[i + 1]) {
      args.commandTimeoutMs = Number(argv[++i])
      continue
    }
    if (arg === '--save-timeout-ms' && argv[i + 1]) {
      args.saveTimeoutMs = Number(argv[++i])
      continue
    }
    if (arg === '--toast-timeout-ms' && argv[i + 1]) {
      args.toastTimeoutMs = Number(argv[++i])
      continue
    }
    if (arg === '--headed') {
      args.headed = true
      continue
    }
    if (arg === '--no-clear-between') {
      args.clearBetween = false
      continue
    }
    if (arg === '--start-from-command' && argv[i + 1]) {
      args.resumeFromCommand = argv[++i]
      continue
    }
    if (arg === '--keep-browser-open') {
      args.keepBrowserOpen = true
      continue
    }
    if (arg === '--help' || arg === '-h') {
      console.log(`Usage: node scripts/capture_output_for_smoke_test.mjs [options]

By default, commands are read from app/conf/autocomplete.yaml (context.<root>.examples[].value).
Use --commands-file to run a specific subset instead.

Options:
  --base-url <url>            App URL to connect to (default: ${args.baseUrl})
  --out-dir <dir>             Directory for captured txt files (default: ${args.outDir})
  --commands-file <path>      Plain-text file of commands to run (one per line, # comments ignored)
  --pause-ms <ms>             Pause between commands to avoid rate limits (default: ${args.pauseMs})
  --settle-ms <ms>            Time to wait after a command finishes before saving (default: ${args.settleMs})
  --stable-ms <ms>            Time the output line count must remain unchanged before saving (default: ${args.stableMs})
  --command-timeout-ms <ms>   Time to wait for each command to finish (default: ${args.commandTimeoutMs})
  --save-timeout-ms <ms>      Time to wait for a download after clicking save (default: ${args.saveTimeoutMs})
  --toast-timeout-ms <ms>     Time to wait for the no-output toast (default: ${args.toastTimeoutMs})
  --headed                    Launch a visible browser window
  --no-clear-between          Leave output in the tab between commands
  --start-from-command <cmd>  Skip commands before the first exact match (searches within --commands-file if both are provided)
  --keep-browser-open         Leave the browser open after capture finishes
`)
      process.exit(0)
    }
  }

  return args
}

function slugify(command) {
  return command
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .replace(/-{2,}/g, '-')
    .slice(0, 96) || 'command'
}

function loadCommands(args) {
  if (args.commandsFile) {
    return readFileSync(args.commandsFile, 'utf8')
      .split(/\r?\n/)
      .map(line => line.trim())
      .filter(line => line && !line.startsWith('#'))
  }
  const script = [
    'import yaml, json, sys',
    "d = yaml.safe_load(open(sys.argv[1]))",
    "ctx = d.get('context', {})",
    "cmds = [ex['value'] for spec in ctx.values() if isinstance(spec, dict) for ex in (spec.get('examples') or []) if str(ex.get('value', '')).strip()]",
    "print(json.dumps(cmds))",
  ].join('\n')
  const output = execFileSync('python3', ['-c', script, AUTOCOMPLETE_FILE], { encoding: 'utf8' }).trim()
  return JSON.parse(output)
}

function selectCommandTimeoutMs(command, defaultTimeoutMs) {
  const trimmed = command.trim()
  const root = trimmed.split(/\s+/, 1)[0].toLowerCase()

  if (root === 'nmap') {
    if (/\s-p-(?=\s|$)/.test(trimmed) || /\s--top-ports\b/.test(trimmed)) {
      return Math.max(defaultTimeoutMs, 1_800_000)
    }
    return Math.max(defaultTimeoutMs, 900_000)
  }

  if (['masscan', 'wapiti', 'wpscan', 'nikto', 'nuclei'].includes(root)) {
    return Math.max(defaultTimeoutMs, 900_000)
  }

  if (['mtr', 'traceroute', 'tcptraceroute', 'whois', 'dig', 'nslookup', 'host'].includes(root)) {
    return Math.max(defaultTimeoutMs, 300_000)
  }

  return defaultTimeoutMs
}

function selectCommandSettleMs(command, defaultSettleMs) {
  const trimmed = command.trim()
  const root = trimmed.split(/\s+/, 1)[0].toLowerCase()

  if (root === 'man') {
    return Math.max(defaultSettleMs, 5_000)
  }

  if (['nmap', 'masscan', 'wapiti', 'wpscan', 'nikto', 'nuclei'].includes(root)) {
    return Math.max(defaultSettleMs, 3_000)
  }

  if (['mtr', 'traceroute', 'tcptraceroute', 'whois', 'dig', 'nslookup', 'host', 'curl', 'wget'].includes(root)) {
    return Math.max(defaultSettleMs, 2_000)
  }

  return defaultSettleMs
}

async function ensureHealthy(page, timeoutMs = 120_000) {
  const resp = await page.goto('/health', { waitUntil: 'domcontentloaded' })
  if (!resp || !resp.ok()) {
    throw new Error(`health check failed: ${resp ? resp.status() : 'no response'}`)
  }
  await page.goto('/', { waitUntil: 'domcontentloaded' })
  await page.locator('#cmd').waitFor({ timeout: timeoutMs })
}

async function startCommand(page, command) {
  const input = page.locator('#cmd')
  await input.fill(command)
  await page.keyboard.press('Enter')
}

async function waitForCommandCompletion(page, timeoutMs) {
  await page.locator('.status-pill').filter({ hasNotText: 'RUNNING' }).waitFor({ timeout: timeoutMs })
}

async function waitForOutputToSettle(page, timeoutMs, stableMs) {
  const lineCount = page.locator('.tab-panel.active .output .line')
  const deadline = Date.now() + timeoutMs
  let lastCount = await lineCount.count()
  let lastChange = Date.now()

  while (Date.now() < deadline) {
    await page.waitForTimeout(250)
    const currentCount = await lineCount.count()
    if (currentCount !== lastCount) {
      lastCount = currentCount
      lastChange = Date.now()
      continue
    }
    if (Date.now() - lastChange >= stableMs) {
      return
    }
  }

  throw new Error(`output did not settle within ${timeoutMs}ms`)
}

async function saveCurrentOutput(page, command, destination, timeouts) {
  const lineCount = await page.locator('.tab-panel.active .output .line').count()
  const saveButton = page.locator('.tab-panel.active [data-action="save"]')

  if (lineCount > 0) {
    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: timeouts.saveTimeoutMs }),
      saveButton.click(),
    ])
    await download.saveAs(destination)
    return { exported: true, note: '' }
  }

  await saveButton.click()
  const toast = page.locator('#permalink-toast')
  await toast.waitFor({ state: 'visible', timeout: timeouts.toastTimeoutMs })
  const note = (await toast.textContent())?.trim() || 'No output to export'
  await writeFile(destination, `# command: ${command}\n# note: ${note}\n`, 'utf8')
  return { exported: false, note }
}

async function clearOutput(page) {
  await page.locator('.tab-panel.active [data-action="clear"]').click()
  await page.waitForFunction(() => document.querySelectorAll('.tab-panel.active .output .line').length === 0, null, { timeout: 15_000 })
}

async function main() {
  const args = parseArgs(process.argv.slice(2))
  const commands = loadCommands(args)

  if (!commands.length) {
    const source = args.commandsFile || AUTOCOMPLETE_FILE
    throw new Error(`No commands found in ${source}`)
  }

  await mkdir(args.outDir, { recursive: true })

  const browser = await chromium.launch({ headless: !args.headed })
  const context = await browser.newContext({
    viewport: { width: 1600, height: 1200 },
    baseURL: args.baseUrl,
  })
  const page = await context.newPage()

  try {
    await ensureHealthy(page)

    const manifest = []
    const startIndex = args.resumeFromCommand
      ? commands.indexOf(args.resumeFromCommand)
      : 0

    if (args.resumeFromCommand && startIndex === -1) {
      throw new Error(`Could not find start command in autocomplete.yaml examples: ${args.resumeFromCommand}`)
    }

    for (let index = startIndex; index < commands.length; index += 1) {
      const command = commands[index]
      const prefix = String(index + 1).padStart(3, '0')
      const slug = slugify(command)
      const fileName = `${prefix}_${slug}.txt`
      const destination = path.join(args.outDir, fileName)
      const timeoutMs = selectCommandTimeoutMs(command, args.commandTimeoutMs)
      const settleMs = selectCommandSettleMs(command, args.settleMs)

      let captured = false
      let errorMessage = ''

      try {
        await startCommand(page, command)
        await waitForCommandCompletion(page, timeoutMs)
        await waitForOutputToSettle(page, settleMs, args.stableMs)
        const result = await saveCurrentOutput(page, command, destination, args)

        manifest.push({
          index: index + 1,
          command,
          file: fileName,
          exported: result.exported,
          timeoutMs,
          settleMs,
          note: result.note || '',
        })
        captured = true
      } catch (err) {
        errorMessage = err && err.message ? err.message.split('\n')[0] : String(err)
        console.error(`[${prefix}] FAILED: ${command}\n  ${errorMessage}`)

        // Attempt to save whatever output has rendered so far
        let partialResult = { exported: false, note: '' }
        try {
          partialResult = await saveCurrentOutput(page, command, destination, args)
        } catch (saveErr) {
          // Nothing to save or save failed — proceed to recovery
        }

        manifest.push({
          index: index + 1,
          command,
          file: fileName,
          exported: partialResult.exported,
          timeoutMs,
          settleMs,
          note: partialResult.note || '',
          error: errorMessage,
        })

        // Recover page to a clean state before continuing
        try {
          await ensureHealthy(page)
        } catch (recoveryErr) {
          console.error(`[${prefix}] Page recovery failed, stopping: ${recoveryErr && recoveryErr.message ? recoveryErr.message.split('\n')[0] : String(recoveryErr)}`)
          break
        }
      }

      if (captured && args.clearBetween && index < commands.length - 1) {
        await clearOutput(page)
      }

      if (args.pauseMs > 0 && index < commands.length - 1) {
        await page.waitForTimeout(args.pauseMs)
      }
    }

    await writeFile(
      path.join(args.outDir, 'manifest.json'),
      `${JSON.stringify({ baseUrl: args.baseUrl, commands: manifest }, null, 2)}\n`,
      'utf8',
    )

    const failed = manifest.filter(e => e.error).length
    const succeeded = manifest.length - failed
    if (failed > 0) {
      console.log(`Captured ${succeeded}/${manifest.length} commands into ${args.outDir} (${failed} failed — see manifest.json)`)
    } else {
      console.log(`Captured ${manifest.length} commands into ${args.outDir}`)
    }
  } finally {
    if (!args.keepBrowserOpen) {
      await context.close().catch(() => {})
      await browser.close().catch(() => {})
    }
  }
}

main().catch(err => {
  console.error(err && err.stack ? err.stack : String(err))
  process.exit(1)
})
