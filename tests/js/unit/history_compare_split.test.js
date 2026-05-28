import { describe, expect, it, vi } from 'vitest'
import { MemoryStorage, fromDomScripts } from './helpers/extract.js'

function loadCompareHelpers({
  apiFetchImpl,
  mobileMode = false,
  clipboardImpl,
  compareViewMode = 'auto',
  compareContext = '3',
  useRealSelectEnhancer = false,
} = {}) {
  document.body.innerHTML = '<input id="cmd" /><div id="permalink-toast"></div>'
  const apiFetch = apiFetchImpl || vi.fn(() => Promise.resolve({ json: () => Promise.resolve({}) }))
  const showToast = vi.fn()
  const clipboard = clipboardImpl || { writeText: vi.fn(() => Promise.resolve()) }
  const applyCompareViewModePreference = vi.fn((mode) => { compareViewMode = mode })
  const applyCompareContextPreference = vi.fn((mode) => { compareContext = mode })
  const fns = fromDomScripts(
    [
      'app/static/js/core/utils.js',
      'app/static/js/core/history_core.js',
      'app/static/js/features/run-comparison/history_compare_core.js',
      'app/static/js/features/run-comparison/history_compare_overlay.js',
      'app/static/js/features/history/history_actions.js',
      'app/static/js/features/history/history_project_actions.js',
      'app/static/js/features/history/history_recall.js',
      'app/static/js/history.js',
      'app/static/js/features/history/history_links.js',
      'app/static/js/features/history/history_mutations.js',
      'app/static/js/features/history/history_restore.js',
      'app/static/js/features/history/history_run_details.js',
      'app/static/js/features/run-comparison/history_compare_controls.js',
      'app/static/js/features/run-comparison/history_compare_navigation.js',
      'app/static/js/features/run-comparison/history_compare_renderer.js',
      'app/static/js/features/run-comparison/history_compare_launcher.js',
    ],
    {
      document,
      localStorage: new MemoryStorage(),
      APP_CONFIG: { recent_commands_limit: 20, history_panel_limit: 8, max_tabs: 10 },
      apiFetch,
      navigator: { clipboard },
      showToast,
      bindDismissible: vi.fn(),
      refocusComposerAfterAction: vi.fn(),
      restoreHistoryRunIntoTab: vi.fn(() => Promise.resolve()),
      createTab: vi.fn(),
      activateTab: vi.fn(),
      useMobileTerminalViewportMode: () => mobileMode,
      getCompareViewModePreference: () => compareViewMode,
      getCompareContextPreference: () => compareContext,
      applyCompareViewModePreference,
      applyCompareContextPreference,
      ...(useRealSelectEnhancer ? {} : { enhanceAppSelects: vi.fn() }),
      setTimeout,
      clearTimeout,
    },
    `({
      _renderHistoryComparison,
      _renderHistoryCompareSplitPane,
      fetchAndRenderHistoryComparison,
    })`,
  )
  return { ...fns, apiFetch, showToast, clipboard, applyCompareViewModePreference, applyCompareContextPreference }
}

function flushPromises() {
  return new Promise(resolve => setImmediate(resolve))
}

function compareData(overrides = {}) {
  return {
    left_run_id: 'run-a',
    right_run_id: 'run-b',
    left: { id: 'run-a', command: 'nmap darklab.sh', exit_code: 0, output_line_count: 5 },
    right: { id: 'run-b', command: 'nmap darklab.sh', exit_code: 1, output_line_count: 6 },
    deltas: {
      exit_code_changed: true,
      exit_code: { left: 0, right: 1 },
      duration_seconds: { delta: 2 },
      output_lines: { delta: 1 },
      findings: { delta: 0 },
    },
    totals: {
      left_total_lines: 5,
      right_total_lines: 6,
      equal_line_count: 1,
      changed_line_count: 1,
      added_line_count: 2,
      removed_line_count: 1,
    },
    limits: {
      line_display_truncate: 24,
      lazy_equal_page_limit: 2,
      lazy_equal_byte_limit: 1000,
    },
    truncated: {
      hunks_omitted: 0,
      lines_omitted: { left: 0, right: 0, total: 0 },
    },
    hunks: [
      {
        op: 'equal',
        left: { start: 0, end: 1, lines: [{ text: 'same', line_index: 0 }] },
        right: { start: 0, end: 1, lines: [{ text: 'same', line_index: 0 }] },
      },
      {
        op: 'replace',
        left: {
          start: 1,
          end: 3,
          lines: [
            { text: 'service old', line_index: 1 },
            { text: 'left only', line_index: 2 },
          ],
        },
        right: {
          start: 1,
          end: 4,
          lines: [
            { text: 'service new', line_index: 1 },
            { text: 'right only one', line_index: 2 },
            { text: 'right only two', line_index: 3 },
          ],
        },
        changed_pairs: [{
          left_index: 0,
          right_index: 0,
          segments: {
            left: [{ text: 'service ' }, { text: 'old', changed: true }],
            right: [{ text: 'service ' }, { text: 'new', changed: true }],
          },
        }],
        left_unpaired: [1],
        right_unpaired: [1, 2],
      },
      {
        op: 'insert',
        left: { start: 3, end: 3 },
        right: { start: 4, end: 5, lines: [{ text: 'added line', line_index: 4 }] },
      },
      {
        op: 'delete',
        left: { start: 3, end: 4, lines: [{ text: 'removed line', line_index: 3 }] },
        right: { start: 5, end: 5 },
        lines_omitted: { left: 1, right: 0, total: 1 },
      },
    ],
    objects: {
      findings: { added: [], removed: [] },
      entities: { added: [], removed: [] },
      artifacts: { added: [], removed: [] },
    },
    ...overrides,
  }
}

describe('history compare split renderer', () => {
  it('renders hunk counts and split-pane rows for equal, replace, insert, and delete hunks', () => {
    const { _renderHistoryComparison } = loadCompareHelpers()
    _renderHistoryComparison(compareData())

    const body = document.querySelector('#history-compare-body')
    expect(document.querySelector('#history-compare-subtitle')?.textContent)
      .toBe('5 lines · 1 unchanged · 1 changed · 2 added · 1 removed')
    expect(document.querySelector('.history-compare-count-badge')).toBeNull()
    expect(document.querySelectorAll('.history-compare-pane')).toHaveLength(2)
    expect(document.querySelector('[data-side="a"]')?.textContent).toContain('service old')
    expect(document.querySelector('[data-side="b"]')?.textContent).toContain('service new')
    expect(document.querySelector('[data-side="b"]')?.textContent).toContain('added line')
    expect(document.querySelector('[data-side="a"]')?.textContent).toContain('removed line')
    expect(document.querySelectorAll('.history-compare-line-delta')).toHaveLength(2)
  })

  it('marks structural kind and role changes on compare rows', () => {
    const { _renderHistoryComparison } = loadCompareHelpers()
    _renderHistoryComparison(compareData({
      hunks: [{
        op: 'replace',
        left: {
          start: 0,
          end: 1,
          lines: [{ text: 'same text', line_index: 0, kind: 'info', role: 'body' }],
        },
        right: {
          start: 0,
          end: 1,
          lines: [{ text: 'same text', line_index: 0, kind: 'info', role: 'section-header' }],
        },
        changed_pairs: [{
          left_index: 0,
          right_index: 0,
          structural_change: true,
          structural: {
            left: { kind: 'info', role: 'body' },
            right: { kind: 'info', role: 'section-header' },
          },
          segments: {
            left: [{ text: 'same text' }],
            right: [{ text: 'same text' }],
          },
        }],
        left_unpaired: [],
        right_unpaired: [],
      }],
      totals: {
        left_total_lines: 1,
        right_total_lines: 1,
        equal_line_count: 0,
        changed_line_count: 1,
        added_line_count: 0,
        removed_line_count: 0,
      },
    }))

    const rows = [...document.querySelectorAll('.history-compare-row.is-structural-change')]
    expect(rows).toHaveLength(2)
    expect(rows[0].dataset.compareRole).toBe('body')
    expect(rows[1].dataset.compareRole).toBe('section-header')
  })

  it('resolves hidden auto mode from viewport and keeps modal view overrides local', () => {
    const { _renderHistoryComparison, applyCompareViewModePreference } = loadCompareHelpers({
      mobileMode: true,
      compareViewMode: 'auto',
    })
    _renderHistoryComparison(compareData())

    let select = document.querySelector('.history-compare-view-select')
    expect(select.value).toBe('unified')
    expect([...select.options].map(option => option.value)).toEqual([
      'unified',
      'changes_only',
      'findings_only',
    ])
    expect(document.querySelector('.history-compare-reset-view').hidden).toBe(true)

    _renderHistoryComparison(compareData({ _compareViewModeRaw: 'unified' }))
    select = document.querySelector('.history-compare-view-select')
    expect(document.querySelector('.history-compare-view-select').value).toBe('unified')
    expect(document.querySelector('.history-compare-reset-view').hidden).toBe(true)

    _renderHistoryComparison(compareData({ _compareViewModeRaw: 'side_by_side' }))
    select = document.querySelector('.history-compare-view-select')
    expect(select.value).toBe('unified')
    expect([...select.options].map(option => option.value)).not.toContain('side_by_side')

    select.value = 'changes_only'
    select.dispatchEvent(new Event('change', { bubbles: true }))
    expect(applyCompareViewModePreference).not.toHaveBeenCalled()
    const reset = document.querySelector('.history-compare-reset-view')
    expect(reset.hidden).toBe(false)
    expect(reset.getAttribute('aria-label')).toBe('Reset comparison view to default')
    expect(reset.textContent).toBe('↻')

    reset.click()
    expect(applyCompareViewModePreference).not.toHaveBeenCalled()
    expect(document.querySelector('.history-compare-view-select').value).toBe('unified')
    expect(document.querySelector('.history-compare-reset-view').hidden).toBe(true)
  })

  it('renders a fetched comparison in mobile mode with the real select enhancer', async () => {
    const apiFetch = vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve(compareData()),
    }))
    const { fetchAndRenderHistoryComparison, showToast } = loadCompareHelpers({
      apiFetchImpl: apiFetch,
      mobileMode: true,
      compareViewMode: 'auto',
      useRealSelectEnhancer: true,
    })

    fetchAndRenderHistoryComparison('run-a', 'run-b')
    await flushPromises()
    await flushPromises()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(apiFetch).toHaveBeenCalledWith('/history/compare?left=run-a&right=run-b')
    expect(showToast).not.toHaveBeenCalledWith('Failed to compare runs', 'error')
    expect(document.getElementById('history-compare-overlay')?.classList.contains('open')).toBe(true)
    expect(document.activeElement?.id).toBe('history-compare-modal')
    expect(document.querySelector('.history-compare-split')?.dataset.compareViewMode).toBe('unified')
    expect(document.querySelector('.history-compare-view-select')?.value).toBe('unified')
    expect(document.querySelector('.history-compare-controls .app-select-menu')?.classList.contains('dropdown-up')).toBe(false)
    expect(document.querySelector('.history-compare-actions-menu-wrap')?.classList.contains('save-menu-down')).toBe(true)
    expect(document.querySelector('.history-compare-actions-menu')?.classList.contains('dropdown-up')).toBe(false)
  })

  it('surfaces backend compare errors instead of only the generic failure toast', async () => {
    const apiFetch = vi.fn(() => Promise.resolve({
      ok: false,
      status: 400,
      json: () => Promise.resolve({ error: 'Choose two different runs to compare' }),
    }))
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    const { fetchAndRenderHistoryComparison, showToast } = loadCompareHelpers({ apiFetchImpl: apiFetch })

    try {
      fetchAndRenderHistoryComparison('run-a', 'run-a')
      await flushPromises()
      await flushPromises()
      await flushPromises()
    } finally {
      consoleError.mockRestore()
    }

    expect(document.getElementById('permalink-toast')?.textContent)
      .toContain('Failed to compare runs: Choose two different runs to compare')
  })

  it('hides equal-line context controls and rows in changes-only and findings-only modes', () => {
    const data = compareData()
    const { _renderHistoryComparison } = loadCompareHelpers({ compareViewMode: 'changes_only' })
    _renderHistoryComparison(data)

    expect(document.querySelector('.history-compare-context-select')).toBeNull()
    expect(document.querySelector('.history-compare-row.is-equal')).toBeNull()
    expect(document.querySelector('.history-compare-split')).not.toBeNull()

    const { _renderHistoryComparison: renderFindingsOnly } = loadCompareHelpers({ compareViewMode: 'findings_only' })
    renderFindingsOnly(compareData({
      objects: {
        findings: { added: [{ id: 'f1', title: 'new finding' }], removed: [] },
        artifacts: { added: [], removed: [] },
      },
    }))
    expect(document.querySelector('.history-compare-context-select')).toBeNull()
    expect(document.querySelector('.history-compare-split')).toBeNull()
    expect(document.querySelector('.history-compare-object-section')).not.toBeNull()
  })

  it('renders added and removed entity-set diffs from comparison objects', () => {
    const { _renderHistoryComparison } = loadCompareHelpers()
    _renderHistoryComparison(compareData({
      hunks: [],
      totals: {
        left_total_lines: 3,
        right_total_lines: 3,
        equal_line_count: 3,
        changed_line_count: 0,
        added_line_count: 0,
        removed_line_count: 0,
      },
      objects: {
        findings: { added: [], removed: [] },
        entities: {
          added: [{
            type: 'domain',
            value: 'www.darklab.sh',
            canonical_value: 'www.darklab.sh',
            confidence: 'high',
          }],
          removed: [{
            type: 'ip',
            value: '192.0.2.10',
            canonical_value: '192.0.2.10',
            confidence: 'medium',
          }],
          unchanged_count: 1,
        },
        artifacts: { added: [], removed: [] },
      },
    }))

    const sections = Array.from(document.querySelectorAll('.history-compare-object-section'));
    expect(sections.map(section => section.querySelector('summary')?.textContent)).toEqual([
      'Added entities (1)',
      'Removed entities (1)',
    ])
    expect(document.querySelector('[data-object-kind="entity"][data-compare-side="b"]')?.textContent)
      .toContain('www.darklab.sh')
    expect(document.querySelector('[data-object-kind="entity"][data-compare-side="a"]')?.textContent)
      .toContain('192.0.2.10')
    expect(document.querySelector('.history-compare-empty')).toBeNull()
  })

  it('rerenders full equal hunks when context dropdown changes without refetching or saving defaults', () => {
    const apiFetch = vi.fn(() => Promise.resolve({ json: () => Promise.resolve({}) }))
    const { _renderHistoryComparison, applyCompareContextPreference } = loadCompareHelpers({
      apiFetchImpl: apiFetch,
      compareContext: '3',
    })
    _renderHistoryComparison(compareData({
      hunks: [{
        op: 'equal',
        left: {
          start: 0,
          end: 8,
          lines: Array.from({ length: 8 }, (_, index) => ({ text: `left ${index}`, line_index: index })),
        },
        right: {
          start: 0,
          end: 8,
          lines: Array.from({ length: 8 }, (_, index) => ({ text: `right ${index}`, line_index: index })),
        },
      }],
    }))

    expect(document.querySelector('[data-side="a"]')?.textContent).not.toContain('left 4')
    const contextSelect = document.querySelector('.history-compare-context-select')
    expect(contextSelect.value).toBe('3')
    contextSelect.value = 'all'
    contextSelect.dispatchEvent(new Event('change', { bubbles: true }))
    expect(applyCompareContextPreference).not.toHaveBeenCalled()
    expect(apiFetch).not.toHaveBeenCalled()
    expect(document.querySelector('[data-side="a"]')?.textContent).toContain('left 4')
  })

  it('renders replace blocks while preserving each side output order', () => {
    const { _renderHistoryComparison } = loadCompareHelpers()
    _renderHistoryComparison(compareData())

    const leftText = [...document.querySelectorAll('[data-side="a"] .history-compare-row')]
      .map(row => row.textContent.trim())
      .join('|')
    const rightText = [...document.querySelectorAll('[data-side="b"] .history-compare-row')]
      .map(row => row.textContent.trim())
      .join('|')
    expect(leftText.indexOf('Aservice old')).toBeLessThan(leftText.indexOf('-left only'))
    expect(rightText.indexOf('Bservice new')).toBeLessThan(rightText.indexOf('+right only one'))
    expect(rightText.indexOf('+right only one')).toBeLessThan(rightText.indexOf('+right only two'))
  })

  it('keeps right-only replace lines before later paired right lines', () => {
    const { _renderHistoryComparison } = loadCompareHelpers()
    _renderHistoryComparison(compareData({
      hunks: [{
        op: 'replace',
        left: {
          start: 0,
          end: 1,
          lines: [{ text: 'Nmap done: 1 host scanned in 0.44 seconds', line_index: 0 }],
        },
        right: {
          start: 0,
          end: 2,
          lines: [
            { text: '6788/tcp open smc-http', line_index: 0 },
            { text: 'Nmap done: 1 host scanned in 0.45 seconds', line_index: 1 },
          ],
        },
        changed_pairs: [{
          left_index: 0,
          right_index: 1,
          segments: {
            left: [{ text: 'Nmap done: 1 host scanned in 0.4' }, { text: '4', changed: true }, { text: ' seconds' }],
            right: [{ text: 'Nmap done: 1 host scanned in 0.4' }, { text: '5', changed: true }, { text: ' seconds' }],
          },
        }],
        left_unpaired: [],
        right_unpaired: [0],
      }],
      totals: {
        left_total_lines: 1,
        right_total_lines: 2,
        equal_line_count: 0,
        changed_line_count: 1,
        added_line_count: 1,
        removed_line_count: 0,
      },
      limits: {
        line_display_truncate: 120,
        lazy_equal_page_limit: 2,
        lazy_equal_byte_limit: 1000,
      },
    }))

    const rightRows = [...document.querySelectorAll('[data-side="b"] .history-compare-row')]
      .map(row => row.textContent.trim())
    expect(rightRows.findIndex(text => text.includes('6788/tcp open smc-http')))
      .toBeLessThan(rightRows.findIndex(text => text.includes('Nmap done: 1 host scanned')))
  })

  it('renders per-hunk and surplus truncation placeholders', () => {
    const { _renderHistoryComparison } = loadCompareHelpers()
    _renderHistoryComparison(compareData({
      left: {
        id: 'run-a',
        command: 'nmap darklab.sh',
        exit_code: 0,
        output_line_count: 5,
        output_source: { noise_lines_omitted: 2 },
      },
      right: {
        id: 'run-b',
        command: 'nmap darklab.sh',
        exit_code: 1,
        output_line_count: 6,
        output_source: { noise_lines_omitted: 1 },
      },
      truncated: {
        hunks_omitted: 2,
        lines_omitted: { left: 1, right: 0, total: 1 },
      },
    }))

    expect(document.querySelector('#history-compare-body')?.textContent)
      .toContain('3 changed line(s) or hunk(s) omitted')
    expect(document.querySelector('[data-side="a"]')?.textContent)
      .toContain('1 changed line(s) omitted in this block.')
    expect(document.querySelector('[data-side="a"]')?.textContent)
      .toContain('2 additional changed hunk(s) omitted.')
    expect(document.querySelector('#history-compare-body')?.textContent)
      .toContain('3 noisy transcript line(s) folded out of this comparison')
  })

  it('expands folded equal hunks through paginated lazy fetches and reuses cached lines', async () => {
    const apiFetch = vi.fn((url) => {
      const parsed = new URL(url, 'https://example.test')
      const side = parsed.searchParams.get('side')
      const start = Number(parsed.searchParams.get('start'))
      if (side === 'a' && start === 1) {
        return Promise.resolve({ json: () => Promise.resolve({ lines: [{ text: 'left folded 1', line_index: 1 }], start: 1, end: 2, truncated: true }) })
      }
      if (side === 'a' && start === 2) {
        return Promise.resolve({ json: () => Promise.resolve({ lines: [{ text: 'left folded 2', line_index: 2 }], start: 2, end: 3, truncated: false }) })
      }
      if (side === 'b' && start === 1) {
        return Promise.resolve({ json: () => Promise.resolve({ lines: [{ text: 'right folded 1', line_index: 1 }], start: 1, end: 2, truncated: true }) })
      }
      return Promise.resolve({ json: () => Promise.resolve({ lines: [{ text: 'right folded 2', line_index: 2 }], start: 2, end: 3, truncated: false }) })
    })
    const { _renderHistoryComparison } = loadCompareHelpers({ apiFetchImpl: apiFetch })
    _renderHistoryComparison(compareData({
      project_id: 'prj_1',
      hunks: [{
        op: 'equal',
        left: { start: 0, end: 4 },
        right: { start: 0, end: 4 },
        context: {
          leading: {
            left: [{ text: 'left lead', line_index: 0 }],
            right: [{ text: 'right lead', line_index: 0 }],
          },
          trailing: {
            left: [{ text: 'left tail', line_index: 3 }],
            right: [{ text: 'right tail', line_index: 3 }],
          },
          omitted: 2,
        },
      }],
    }))

    document.querySelector('.history-compare-fold').click()
    await flushPromises()
    await flushPromises()
    expect(document.querySelector('[data-side="a"]')?.textContent).toContain('left folded 2')
    expect(document.querySelector('[data-side="b"]')?.textContent).toContain('right folded 2')
    expect(apiFetch).toHaveBeenCalledTimes(4)
    expect(apiFetch.mock.calls[0][0]).toContain('project_id=prj_1')

    document.querySelector('.history-compare-fold').click()
    document.querySelector('.history-compare-fold').click()
    await flushPromises()
    expect(apiFetch).toHaveBeenCalledTimes(4)
  })

  it('continues lazy fold pagination across byte-limited pages', async () => {
    const apiFetch = vi.fn((url) => {
      const parsed = new URL(url, 'https://example.test')
      const side = parsed.searchParams.get('side')
      const start = Number(parsed.searchParams.get('start'))
      const label = side === 'a' ? 'left' : 'right'
      return Promise.resolve({
        json: () => Promise.resolve({
          lines: [{ text: `${label} byte page ${start}`, line_index: start }],
          start,
          end: start + 1,
          truncated: start < 2,
          byte_limit: 16,
        }),
      })
    })
    const { _renderHistoryComparison } = loadCompareHelpers({ apiFetchImpl: apiFetch })
    _renderHistoryComparison(compareData({
      limits: {
        line_display_truncate: 200,
        lazy_equal_page_limit: 2,
        lazy_equal_byte_limit: 16,
      },
      hunks: [{
        op: 'equal',
        left: { start: 0, end: 4 },
        right: { start: 0, end: 4 },
        context: {
          leading: {
            left: [{ text: 'left lead', line_index: 0 }],
            right: [{ text: 'right lead', line_index: 0 }],
          },
          trailing: {
            left: [{ text: 'left tail', line_index: 3 }],
            right: [{ text: 'right tail', line_index: 3 }],
          },
          omitted: 2,
        },
      }],
    }))

    document.querySelector('.history-compare-fold').click()
    await flushPromises()
    await flushPromises()
    await flushPromises()
    expect(document.querySelector('[data-side="a"]')?.textContent).toContain('left byte page 2')
    expect(document.querySelector('[data-side="b"]')?.textContent).toContain('right byte page 2')
    expect(apiFetch).toHaveBeenCalledTimes(4)
    expect(apiFetch.mock.calls.map(call => new URL(call[0], 'https://example.test').searchParams.get('start')))
      .toEqual(['1', '1', '2', '2'])
  })

  it('expands a single oversized lazy line without requiring another page', async () => {
    const oversized = 'x'.repeat(120)
    const apiFetch = vi.fn(url => {
      const parsed = new URL(url, 'https://example.test')
      const side = parsed.searchParams.get('side')
      return Promise.resolve({
        json: () => Promise.resolve({
          lines: [{ text: `${side}:${oversized}`, line_index: 1 }],
          start: 1,
          end: 2,
          truncated: false,
          byte_limit: 16,
        }),
      })
    })
    const { _renderHistoryComparison } = loadCompareHelpers({ apiFetchImpl: apiFetch })
    _renderHistoryComparison(compareData({
      limits: {
        line_display_truncate: 200,
        lazy_equal_page_limit: 2,
        lazy_equal_byte_limit: 16,
      },
      hunks: [{
        op: 'equal',
        left: { start: 0, end: 3 },
        right: { start: 0, end: 3 },
        context: {
          leading: {
            left: [{ text: 'left lead', line_index: 0 }],
            right: [{ text: 'right lead', line_index: 0 }],
          },
          trailing: {
            left: [{ text: 'left tail', line_index: 2 }],
            right: [{ text: 'right tail', line_index: 2 }],
          },
          omitted: 1,
        },
      }],
    }))

    document.querySelector('.history-compare-fold').click()
    await flushPromises()
    await flushPromises()
    expect(document.querySelector('[data-side="a"]')?.textContent).toContain(`a:${oversized}`)
    expect(document.querySelector('[data-side="b"]')?.textContent).toContain(`b:${oversized}`)
    expect(apiFetch).toHaveBeenCalledTimes(2)
  })

  it('stops lazy fold pagination when the backend clamps a stale range', async () => {
    const apiFetch = vi.fn(url => {
      const parsed = new URL(url, 'http://localhost')
      const side = parsed.searchParams.get('side')
      return Promise.resolve({
        json: () => Promise.resolve({
          lines: [{ text: `${side} folded`, line_index: 1 }],
          start: 1,
          end: 2,
          truncated: true,
          range_clamped: true,
        }),
      })
    })
    const { _renderHistoryComparison } = loadCompareHelpers({ apiFetchImpl: apiFetch })
    _renderHistoryComparison(compareData({
      hunks: [{
        op: 'equal',
        left: { start: 0, end: 5 },
        right: { start: 0, end: 5 },
        context: {
          leading: {
            left: [{ text: 'left lead', line_index: 0 }],
            right: [{ text: 'right lead', line_index: 0 }],
          },
          trailing: {
            left: [{ text: 'left tail', line_index: 4 }],
            right: [{ text: 'right tail', line_index: 4 }],
          },
          omitted: 3,
        },
      }],
    }))

    document.querySelector('.history-compare-fold').click()
    await flushPromises()
    await flushPromises()
    expect(document.querySelector('[data-side="a"]')?.textContent).toContain('a folded')
    expect(document.querySelector('[data-side="b"]')?.textContent).toContain('b folded')
    expect(apiFetch).toHaveBeenCalledTimes(2)
  })

  it('expands empty folded equal ranges without a lazy fetch', async () => {
    const apiFetch = vi.fn()
    const { _renderHistoryComparison } = loadCompareHelpers({ apiFetchImpl: apiFetch })
    _renderHistoryComparison(compareData({
      hunks: [{
        op: 'equal',
        left: { start: 0, end: 2 },
        right: { start: 0, end: 2 },
        context: {
          leading: {
            left: [{ text: 'left lead', line_index: 0 }],
            right: [{ text: 'right lead', line_index: 0 }],
          },
          trailing: {
            left: [{ text: 'left tail', line_index: 1 }],
            right: [{ text: 'right tail', line_index: 1 }],
          },
          omitted: 1,
        },
      }],
    }))

    document.querySelector('.history-compare-fold').click()
    await flushPromises()
    expect(apiFetch).not.toHaveBeenCalled()
    expect(document.querySelector('.history-compare-fold')?.textContent).toBe('▾ Hide unchanged lines')
  })

  it('expands long line text in place', () => {
    const { _renderHistoryComparison } = loadCompareHelpers()
    _renderHistoryComparison(compareData({
      limits: { line_display_truncate: 6 },
      hunks: [{
        op: 'insert',
        left: { start: 0, end: 0 },
        right: {
          start: 0,
          end: 1,
          lines: [{ text: 'abcdefghijklmnopqrstuvwxyz', line_index: 0 }],
        },
      }],
    }))

    expect(document.querySelector('[data-side="b"]')?.textContent).toContain('abcdef')
    expect(document.querySelector('[data-side="b"]')?.textContent).not.toContain('mnopqrstuvwxyz')
    document.querySelector('.history-compare-line-expander').click()
    expect(document.querySelector('[data-side="b"]')?.textContent).toContain('abcdefghijklmnopqrstuvwxyz')
  })

  it('uses totals for copy summary output', async () => {
    const clipboard = { writeText: vi.fn(() => Promise.resolve()) }
    const { _renderHistoryComparison } = loadCompareHelpers({ clipboardImpl: clipboard })
    _renderHistoryComparison(compareData())
    document.querySelector('.history-compare-actions-trigger').click()
    expect(document.querySelector('.history-compare-actions-menu-wrap').classList.contains('open')).toBe(true)
    ;[...document.querySelectorAll('.history-compare-actions-menu .dropdown-item')]
      .find(button => button.textContent === 'Copy summary')
      .click()
    await Promise.resolve()

    expect(document.querySelector('.history-compare-actions-menu-wrap').classList.contains('open')).toBe(false)
    expect(clipboard.writeText.mock.calls[0][0]).toContain('Changed: 1')
    expect(clipboard.writeText.mock.calls[0][0]).toContain('Added: 2')
    expect(clipboard.writeText.mock.calls[0][0]).toContain('Removed: 1')
    expect(clipboard.writeText.mock.calls[0][0]).toContain('Unchanged: 1')
  })

  it('does not sync split pane scroll positions in mobile terminal mode', () => {
    const { _renderHistoryComparison } = loadCompareHelpers({ mobileMode: true })
    _renderHistoryComparison(compareData())
    const left = document.querySelector('[data-side="a"]')
    const right = document.querySelector('[data-side="b"]')
    left.scrollTop = 42
    left.dispatchEvent(new Event('scroll'))

    expect(right.scrollTop).toBe(0)
  })
})
