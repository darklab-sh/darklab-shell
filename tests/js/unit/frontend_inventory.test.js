// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'
import { beforeAll, describe, expect, it } from 'vitest'
import {
  buildFrontendInventoryReport,
  formatFrontendInventoryCheckResult,
} from '../../../scripts/frontend/inventory_frontend_modules.mjs'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../../..')
const INVENTORY_CHECK_TIMEOUT_MS = 60_000
let inventoryReport = null

function runInventoryJson() {
  if (inventoryReport) return inventoryReport
  inventoryReport = buildFrontendInventoryReport({ root: REPO_ROOT })
  return inventoryReport
}

function runInventoryCheckWithOutput({ allowlistPath = undefined } = {}) {
  return formatFrontendInventoryCheckResult(buildFrontendInventoryReport({
    root: REPO_ROOT,
    ...(allowlistPath ? { allowlistPath } : {}),
  }))
}

function moduleReport(report, source) {
  const module = report.modules.find((entry) => entry.source === source)
  expect(module).toBeTruthy()
  return module
}

describe('frontend browser global boundary inventory', () => {
  beforeAll(() => {
    runInventoryJson()
  }, INVENTORY_CHECK_TIMEOUT_MS)

  const EXPECTED_BOUNDARY_BUDGETS = Object.freeze({
    window_publish_purposes: Object.freeze({
      intentional_bootstrap: 4,
      lazy_placeholder: 102,
      module_api_bridge: 61,
      bridge_internal: 10,
      test_hook: 3,
      compatibility_export: 0,
    }),
    window_property_read_purposes: Object.freeze({
      intentional_bootstrap: 2,
      lazy_placeholder: 13,
      module_api_bridge: 9,
      test_hook: 1,
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
      module_api_bridge: 66,
      bridge_internal: 0,
      test_hook: 3,
      compatibility_export: 0,
      compatibility_read: 0,
    }),
    resolver_helper_calls_by_class: Object.freeze({
      bridge_dispatch: 95,
      global_only: 546,
      import_first: 588,
    }),
    resolver_helper_calls_by_final_resolution: Object.freeze({
      allowlisted_global: 54,
      bridge_dispatch_report_only: 91,
      dynamic_or_non_literal: 27,
      fallback_imported_binding: 375,
      fallback_local_binding: 12,
      global_publish: 77,
      guarded_compatibility_fallback: 506,
      same_file_import_source: 87,
      unresolved_report_only: 0,
    }),
    bridge_dispatch: Object.freeze({
      declaration_count: 84,
      registration_count: 89,
      dispatch_count: 91,
      dispatched_missing_declaration_count: 0,
      dispatched_missing_registration_count: 0,
      declared_not_dispatched_count: 0,
      registered_not_declared_count: 0,
      by_bridge: Object.freeze({
        controller_action: Object.freeze({ declared_count: 6, registered_count: 6, dispatched_count: 6 }),
        output: Object.freeze({ declared_count: 12, registered_count: 12, dispatched_count: 12 }),
        runner: Object.freeze({ declared_count: 24, registered_count: 24, dispatched_count: 24 }),
        tabs: Object.freeze({ declared_count: 18, registered_count: 18, dispatched_count: 18 }),
        workspace: Object.freeze({ declared_count: 17, registered_count: 17, dispatched_count: 17 }),
        workflows: Object.freeze({ declared_count: 7, registered_count: 7, dispatched_count: 7 }),
      }),
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

  it('keeps lazy loader placeholders separate from unexpected window publishes', () => {
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
    expect(report.generated_by).toBe('scripts/frontend/inventory_frontend_modules.mjs')
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
  }, INVENTORY_CHECK_TIMEOUT_MS)

  it('pins browser-boundary budgets so the global surface cannot grow silently', () => {
    const report = runInventoryJson()

    expect(report.summary.unresolved_app_bare_read_count).toBe(0)
    expect(report.summary.unused_allowlist_entry_count).toBe(0)
    expectPurposeBudgets(
      report.summary.window_publish_purposes,
      EXPECTED_BOUNDARY_BUDGETS.window_publish_purposes,
    )
    expectPurposeBudgets(
      report.summary.window_property_read_purposes,
      EXPECTED_BOUNDARY_BUDGETS.window_property_read_purposes,
    )
    expectPurposeBudgets(
      report.summary.foreign_bare_read_purposes,
      EXPECTED_BOUNDARY_BUDGETS.foreign_bare_read_purposes,
    )
    expectPurposeBudgets(
      report.allowlist.purposes,
      EXPECTED_BOUNDARY_BUDGETS.allowlist_purposes,
    )
    expectPurposeBudgets(
      report.summary.resolver_helper_calls_by_class,
      EXPECTED_BOUNDARY_BUDGETS.resolver_helper_calls_by_class,
    )
    expectPurposeBudgets(
      report.summary.resolver_helper_calls_by_final_resolution,
      EXPECTED_BOUNDARY_BUDGETS.resolver_helper_calls_by_final_resolution,
    )
    Object.entries(EXPECTED_BOUNDARY_BUDGETS.bridge_dispatch).forEach(([key, expected]) => {
      if (key === 'by_bridge') return
      expect(report.summary.bridge_dispatch[key], key).toBe(expected)
    })
    Object.entries(EXPECTED_BOUNDARY_BUDGETS.bridge_dispatch.by_bridge).forEach(([bridge, expected]) => {
      expect(report.summary.bridge_dispatch.by_bridge[bridge], bridge).toEqual(expect.objectContaining(expected))
    })
  })

  it('reports string-keyed ESM resolver helper calls for follow-up guardrails', () => {
    const report = runInventoryJson()
    const tabs = moduleReport(report, '/static/js/tabs.js')

    expect(report.summary.resolver_helper_call_count).toBeGreaterThan(0)
    expect(report.summary.resolver_helper_calls_by_class.global_only).toBeGreaterThan(0)
    expect(report.summary.resolver_helper_calls_by_class.import_first).toBeGreaterThan(0)
    expect(report.summary.resolver_helper_calls_by_class.bridge_dispatch).toBeGreaterThan(0)
    expect(report.summary.resolver_helper_calls_by_resolution.dynamic_or_non_literal).toBeGreaterThan(0)

    expect(tabs.resolver_helper_calls).toContainEqual(expect.objectContaining({
      helper: '_tabGlobalValue',
      class: 'import_first',
      name: '_tabDragSuppressClickUntil',
      fallback: expect.objectContaining({ status: 'missing' }),
    }))
  })

  it('reconciles structural resolver-helper discovery against the committed registry', () => {
    const report = runInventoryJson()
    const discovery = report.summary.resolver_helper_discovery

    expect(discovery.discovered_count).toBeGreaterThan(0)
    expect(discovery.uncovered).toEqual([])
    expect(discovery.dead_registry_entries).toEqual([])
    expect(discovery.dead_ignore_entries).toEqual([])
  })

  it('validates aliased bridge handler-existence predicate keys as bridge dispatch', () => {
    const report = runInventoryJson()
    const uiHelpers = moduleReport(report, '/static/js/ui/ui_helpers.js')

    // `importedHasRunnerHandler('hasPendingTerminalConfirm')` resolves through the
    // aliased import to the canonical hasRunnerHandler and is treated as a runner
    // bridge dispatch, so its key is held to the declared/registered contract.
    expect(uiHelpers.resolver_helper_calls).toContainEqual(expect.objectContaining({
      helper: 'hasRunnerHandler',
      class: 'bridge_dispatch',
      name: 'hasPendingTerminalConfirm',
    }))
    expect(report.summary.bridge_dispatch.dispatched_missing_declaration_count).toBe(0)
    expect(report.summary.bridge_dispatch.dispatched_missing_registration_count).toBe(0)
  })

  it('recognizes aliased and computed browser-global publishers', () => {
    const report = runInventoryJson()
    const suggestions = moduleReport(report, '/static/js/features/autocomplete/suggestions.js')
    const runnerBridge = moduleReport(report, '/static/js/runner_bridge.js')

    // Aliased member write (SOME_GLOBAL.x = …) is now captured as a publish.
    expect(suggestions.window_publishes).toContainEqual(expect.objectContaining({
      name: 'acSuggestions',
      purpose: 'module_api_bridge',
    }))
    // `__darklab*` bridge plumbing is auto-classified, not flagged as a stray publish.
    expect(runnerBridge.window_publishes).toContainEqual(expect.objectContaining({
      name: '__darklabRunnerHandlers',
      purpose: 'bridge_internal',
    }))
    // The publish-side completeness check has no untracked computed publishers.
    expect(report.summary.untracked_computed_publisher_count).toBe(0)
    expect(report.summary.publisher_helper_discovery).toEqual(expect.objectContaining({
      registered_count: 2,
      discovered_count: 2,
      discovered: ['_setStateValue', 'loadProjectNamespace'],
      dead_registry_entries: [],
      dynamic_or_non_literal_call_count: 0,
      dynamic_or_non_literal_calls: [],
    }))
    expect(report.summary.window_publish_purposes.compatibility_export || 0).toBe(0)
  })

  it('fails check mode when computed browser-global publisher registry coverage drifts', () => {
    const fixture = resolve(REPO_ROOT, 'app/static/js/__inventory_publisher_check.fixture.js')
    try {
      writeFileSync(fixture, [
        "const FIXTURE_PUBLISH_GLOBAL = typeof window !== 'undefined' ? window : globalThis",
        'function _unregisteredFixturePublisher(name, value) {',
        '  FIXTURE_PUBLISH_GLOBAL[name] = value',
        '}',
        'export { _unregisteredFixturePublisher }',
        '',
      ].join('\n'))

      const failure = runInventoryCheckWithOutput()

      expect(failure.ok).toBe(false)
      expect(failure.output).toContain('computed browser-global publishers not registered')
      expect(failure.output).toContain('_unregisteredFixturePublisher')
    } finally {
      rmSync(fixture, { force: true })
    }
  }, INVENTORY_CHECK_TIMEOUT_MS)

  it('fails check mode when a registered browser-global publisher uses a dynamic name', () => {
    const fixture = resolve(REPO_ROOT, 'app/static/js/__inventory_publisher_dynamic_check.fixture.js')
    try {
      writeFileSync(fixture, [
        "const FIXTURE_PUBLISH_GLOBAL = typeof window !== 'undefined' ? window : globalThis",
        'function loadProjectNamespace(_modulePath, globalName, factory) {',
        '  FIXTURE_PUBLISH_GLOBAL[globalName] = factory',
        '}',
        "const dynamicName = 'DynamicInventoryPublisherFixture'",
        'loadProjectNamespace("./fixture.js", dynamicName, () => ({}))',
        '',
      ].join('\n'))

      const dynamicFailure = runInventoryCheckWithOutput()

      expect(dynamicFailure.ok).toBe(false)
      expect(dynamicFailure.output).toContain('publisher-helper registry drift')
      expect(dynamicFailure.output).toContain('published name is dynamic or non-literal')
      expect(dynamicFailure.output).toContain('loadProjectNamespace')
    } finally {
      rmSync(fixture, { force: true })
    }
  }, INVENTORY_CHECK_TIMEOUT_MS)

  it('fails check mode when a resolver-shaped helper is missing from the registry', () => {
    const fixture = resolve(REPO_ROOT, 'app/static/js/__inventory_discovery_check.fixture.js')
    try {
      writeFileSync(fixture, [
        "const FIXTURE_DISCOVERY_GLOBAL = typeof window !== 'undefined' ? window : globalThis",
        'function _unregisteredFixtureGlobalFunction(name) {',
        '  const fn = FIXTURE_DISCOVERY_GLOBAL && FIXTURE_DISCOVERY_GLOBAL[name]',
        "  return typeof fn === 'function' ? fn : null",
        '}',
        'export { _unregisteredFixtureGlobalFunction }',
        '',
      ].join('\n'))

      const failure = runInventoryCheckWithOutput()

      expect(failure.ok).toBe(false)
      expect(failure.output).toContain('resolver-helper registry drift')
      expect(failure.output).toContain('_unregisteredFixtureGlobalFunction')
    } finally {
      rmSync(fixture, { force: true })
    }
  }, INVENTORY_CHECK_TIMEOUT_MS)

  it('fails check mode when a string-keyed resolver helper has no resolution path', () => {
    const fixture = resolve(REPO_ROOT, 'app/static/js/__inventory_resolver_check.fixture.js')
    try {
      writeFileSync(fixture, [
        "const FIXTURE_GLOBAL = typeof window !== 'undefined' ? window : globalThis",
        'function _runtimeGlobalFunction(name) {',
        '  const fn = FIXTURE_GLOBAL && FIXTURE_GLOBAL[name]',
        "  return typeof fn === 'function' ? fn : null",
        '}',
        "_runtimeGlobalFunction('missingInventoryResolverFixture')",
        '',
      ].join('\n'))

      const failure = runInventoryCheckWithOutput()

      expect(failure.ok).toBe(false)
      expect(failure.output).toContain('unresolved ESM resolver helper calls')
      expect(failure.output).toContain('/static/js/__inventory_resolver_check.fixture.js')
      expect(failure.output).toContain("_runtimeGlobalFunction('missingInventoryResolverFixture')")
    } finally {
      rmSync(fixture, { force: true })
    }
  }, INVENTORY_CHECK_TIMEOUT_MS)

  it('fails check mode when a bridge dispatch has no declared or registered handler', () => {
    const fixture = resolve(REPO_ROOT, 'app/static/js/__inventory_bridge_dispatch_check.fixture.js')
    try {
      writeFileSync(fixture, [
        "function _callRunnerHandler(name, fallback, args) { return fallback || args || name }",
        "_callRunnerHandler('missingBridgeHandlerFixture', undefined, [])",
        '',
      ].join('\n'))

      const failure = runInventoryCheckWithOutput()

      expect(failure.ok).toBe(false)
      expect(failure.output).toContain('invalid bridge-dispatch contracts')
      expect(failure.output).toContain('missing declared handler slots')
      expect(failure.output).toContain('missing handler registration')
      expect(failure.output).toContain('runner.missingBridgeHandlerFixture')
      expect(failure.output).toContain('/static/js/__inventory_bridge_dispatch_check.fixture.js')
    } finally {
      rmSync(fixture, { force: true })
    }
  }, INVENTORY_CHECK_TIMEOUT_MS)

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

      const failure = runInventoryCheckWithOutput({ allowlistPath: fixtureAllowlist })

      expect(failure.ok).toBe(false)
      expect(failure.output).toContain('unused frontend-globals.allowlist.json entries')
      expect(failure.output).toContain('__inventoryStaleAllowlistFixture')
      expect(failure.output).toContain('/static/js/__inventory_missing_provider.fixture.js')
    } finally {
      rmSync(tempDir, { recursive: true, force: true })
    }
  }, INVENTORY_CHECK_TIMEOUT_MS)
})
