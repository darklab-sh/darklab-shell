import { describe, expect, it, vi } from 'vitest'
import { MemoryStorage, fromDomScripts } from './helpers/extract.js'

function loadCompareHelpers({ apiFetchImpl, mobileMode = false, clipboardImpl } = {}) {
  document.body.innerHTML = '<input id="cmd" /><div id="permalink-toast"></div>'
  const apiFetch = apiFetchImpl || vi.fn(() => Promise.resolve({ json: () => Promise.resolve({}) }))
  const showToast = vi.fn()
  const clipboard = clipboardImpl || { writeText: vi.fn(() => Promise.resolve()) }
  const fns = fromDomScripts(
    ['app/static/js/utils.js', 'app/static/js/history_core.js', 'app/static/js/history.js'],
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
      setTimeout,
      clearTimeout,
    },
    `({
      _renderHistoryComparison,
      _renderHistoryCompareSplitPane,
      fetchAndRenderHistoryComparison,
    })`,
  )
  return { ...fns, apiFetch, showToast, clipboard }
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
    expect(body?.textContent).toContain('changed 1')
    expect(body?.textContent).toContain('added 2')
    expect(body?.textContent).toContain('removed 1')
    expect(document.querySelectorAll('.history-compare-pane')).toHaveLength(2)
    expect(document.querySelector('[data-side="a"]')?.textContent).toContain('service old')
    expect(document.querySelector('[data-side="b"]')?.textContent).toContain('service new')
    expect(document.querySelector('[data-side="b"]')?.textContent).toContain('added line')
    expect(document.querySelector('[data-side="a"]')?.textContent).toContain('removed line')
    expect(document.querySelectorAll('.history-compare-line-delta')).toHaveLength(2)
  })

  it('renders replace blocks in pair, left-only, then right-only order', () => {
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

  it('renders per-hunk and surplus truncation placeholders', () => {
    const { _renderHistoryComparison } = loadCompareHelpers()
    _renderHistoryComparison(compareData({
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
    ;[...document.querySelectorAll('.history-compare-actions button')]
      .find(button => button.textContent === 'Copy summary')
      .click()
    await Promise.resolve()

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
