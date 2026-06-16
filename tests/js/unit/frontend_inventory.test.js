import { execFileSync, spawnSync } from 'node:child_process'
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { beforeAll, describe, expect, it } from 'vitest'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../../..')
const EXEC_OPTIONS = { cwd: REPO_ROOT, encoding: 'utf8', maxBuffer: 20 * 1024 * 1024 }
let inventoryReport = null

function runInventoryJson() {
  if (inventoryReport) return inventoryReport
  inventoryReport = JSON.parse(execFileSync(
    'node',
    ['scripts/inventory_frontend_modules.mjs', '--json', '--check'],
    EXEC_OPTIONS,
  ))
  return inventoryReport
}

function runInventoryCheckWithOutput(env = {}) {
  const result = spawnSync(
    'node',
    ['scripts/inventory_frontend_modules.mjs', '--check'],
    {
      ...EXEC_OPTIONS,
      env: { ...process.env, ...env },
    },
  )
  return {
    ok: result.status === 0,
    output: `${result.stdout || ''}${result.stderr || ''}`,
  }
}

function moduleReport(report, source) {
  const module = report.modules.find((entry) => entry.source === source)
  expect(module).toBeTruthy()
  return module
}

describe('frontend compatibility global inventory', () => {
  beforeAll(() => {
    runInventoryJson()
  }, 30_000)

  const EXPECTED_GLOBAL_BUDGETS = Object.freeze({
    window_publish_purposes: Object.freeze({
      intentional_bootstrap: 2,
      lazy_placeholder: 68,
      module_api_bridge: 25,
      test_hook: 3,
      compatibility_export: 0,
    }),
    window_property_read_purposes: Object.freeze({
      intentional_bootstrap: 1,
      lazy_placeholder: 12,
      module_api_bridge: 2,
      vendor_global: 6,
      compatibility_read: 0,
    }),
    foreign_bare_read_purposes: Object.freeze({
      compatibility_read: 0,
    }),
    allowlist_purposes: Object.freeze({
      intentional_bootstrap: 3,
      vendor_global: 4,
      lazy_placeholder: 1,
      module_api_bridge: 25,
      test_hook: 3,
      compatibility_export: 0,
      compatibility_read: 0,
    }),
  })

  function expectPurposeBudgets(actual, expected) {
    Object.entries(expected).forEach(([purpose, count]) => {
      expect(actual[purpose] || 0, purpose).toBe(count)
    })
  }

  it('classifies intentional bootstrap and vendor globals from the allowlist', () => {
    const report = runInventoryJson()
    const config = moduleReport(report, '/static/js/core/config.js')
    const permalink = moduleReport(report, '/static/js/permalink.js')

    expect(report.allowlist.path).toBe('frontend-globals.allowlist.json')
    expect(config).toBeTruthy()
    expect(report.allowlist.purposes.intentional_bootstrap).toBeGreaterThan(0)
    expect(permalink.window_property_reads).toContainEqual(expect.objectContaining({
      name: 'AnsiUp',
      purpose: 'vendor_global',
    }))
    expect(permalink.window_property_reads).toContainEqual(expect.objectContaining({
      name: 'PermData',
      purpose: 'intentional_bootstrap',
    }))
  })

  it('keeps lazy loader placeholders separate from generic compatibility exports', () => {
    const report = runInventoryJson()
    const lazyAssets = moduleReport(report, '/static/js/core/lazy_assets.js')

    expect(lazyAssets.window_publishes).toContainEqual(expect.objectContaining({
      name: 'loadLazyAsset',
      purpose: 'lazy_placeholder',
    }))
    expect(report.summary.window_publish_purposes.compatibility_export || 0).toBe(0)
  })

  it('passes check mode while reporting global purpose totals', () => {
    const report = runInventoryJson()
    expect(report.generated_by).toBe('scripts/inventory_frontend_modules.mjs')
    expect(report.summary.unresolved_app_bare_read_count).toBe(0)
    expect(report.summary.window_publish_purposes.intentional_bootstrap).toBeGreaterThan(0)
    expect(report.summary.window_publish_purposes.lazy_placeholder).toBeGreaterThan(0)
    expect(report.summary.window_publish_purposes.compatibility_export || 0).toBe(0)
    expect(report.summary.foreign_bare_read_purposes.compatibility_read || 0).toBe(0)
    expect(report.summary.window_property_read_purposes.compatibility_read || 0).toBe(0)

    const provider = resolve(REPO_ROOT, 'app/static/js/__inventory_check_provider.fixture.js')
    const consumer = resolve(REPO_ROOT, 'app/static/js/__inventory_check_consumer.fixture.js')
    try {
      writeFileSync(provider, 'window.__inventoryCheckFixture = 1;\n')
      writeFileSync(consumer, 'window.__inventoryCheckFixture;\n')
      const failure = runInventoryCheckWithOutput()
      expect(failure.ok).toBe(false)
      expect(failure.output).toContain('Non-allowlisted window publishes')
      expect(failure.output).toContain('/static/js/__inventory_check_provider.fixture.js')
      expect(failure.output).toContain('Non-allowlisted window reads')
      expect(failure.output).toContain('/static/js/__inventory_check_consumer.fixture.js')
    } finally {
      rmSync(provider, { force: true })
      rmSync(consumer, { force: true })
    }
  }, 15_000)

  it('pins compatibility-boundary budgets so global debt cannot grow silently', () => {
    const report = runInventoryJson()

    expect(report.summary.unresolved_app_bare_read_count).toBe(0)
    expect(report.summary.unused_allowlist_entry_count).toBe(0)
    expectPurposeBudgets(
      report.summary.window_publish_purposes,
      EXPECTED_GLOBAL_BUDGETS.window_publish_purposes,
    )
    expectPurposeBudgets(
      report.summary.window_property_read_purposes,
      EXPECTED_GLOBAL_BUDGETS.window_property_read_purposes,
    )
    expectPurposeBudgets(
      report.summary.foreign_bare_read_purposes,
      EXPECTED_GLOBAL_BUDGETS.foreign_bare_read_purposes,
    )
    expectPurposeBudgets(
      report.allowlist.purposes,
      EXPECTED_GLOBAL_BUDGETS.allowlist_purposes,
    )
  })

  it('fails check mode when an allowlist entry no longer matches a boundary', () => {
    const tempDir = mkdtempSync(resolve(tmpdir(), 'darklab-inventory-'))
    const fixtureAllowlist = resolve(tempDir, 'frontend-globals.allowlist.json')
    try {
      const allowlist = JSON.parse(readFileSync(resolve(REPO_ROOT, 'frontend-globals.allowlist.json'), 'utf8'))
      allowlist.globals.push({
        name: '__inventoryStaleAllowlistFixture',
        purpose: 'module_api_bridge',
        owner: 'inventory test fixture',
        sources: ['/static/js/__inventory_missing_provider.fixture.js'],
        reason: 'Temporary fixture proves stale allowlist entries fail check mode.',
        removal_target: 'Remove this fixture entry after the assertion.',
      })
      writeFileSync(fixtureAllowlist, `${JSON.stringify(allowlist, null, 2)}\n`)

      const failure = runInventoryCheckWithOutput({ FRONTEND_GLOBALS_ALLOWLIST: fixtureAllowlist })

      expect(failure.ok).toBe(false)
      expect(failure.output).toContain('unused frontend-globals.allowlist.json entries')
      expect(failure.output).toContain('__inventoryStaleAllowlistFixture')
      expect(failure.output).toContain('/static/js/__inventory_missing_provider.fixture.js')
    } finally {
      rmSync(tempDir, { recursive: true, force: true })
    }
  }, 15_000)
})
