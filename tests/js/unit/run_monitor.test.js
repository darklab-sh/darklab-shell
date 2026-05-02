import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fromDomScripts } from './helpers/extract.js'

function pathXCoordinates(path) {
  return [...String(path || '').matchAll(/[ML](-?\d+(?:\.\d+)?)\s/g)]
    .map(match => Number(match[1]))
}

function loadRunMonitor({
  runs = [],
  status = { uptime: 12, db: 'ok', redis: 'none', server_time: Date.now() },
  workspace = {
    enabled: true,
    usage: { bytes_used: 2048, file_count: 2 },
    limits: { quota_bytes: 4096, max_files: 10 },
  },
  stats = {
    runs: { total: 4, succeeded: 3, failed: 1, incomplete: 0, average_elapsed_seconds: 12.3 },
    snapshots: 1,
    starred_commands: 2,
    active_runs: 0,
  },
  insights = {
    days: 28,
    first_run_date: '2026-01-02',
    max_day_count: 2,
    activity: [
      { date: '2026-01-01', count: 0, succeeded: 0, failed: 0, incomplete: 0 },
      { date: '2026-01-02', count: 1, succeeded: 1, failed: 0, incomplete: 0 },
      { date: '2026-01-03', count: 2, succeeded: 1, failed: 1, incomplete: 0 },
      { date: '2026-01-04', count: 0, succeeded: 0, failed: 0, incomplete: 0 },
      { date: '2026-01-05', count: 1, succeeded: 0, failed: 0, incomplete: 1 },
      { date: '2026-01-06', count: 0, succeeded: 0, failed: 0, incomplete: 0 },
      { date: '2026-01-07', count: 0, succeeded: 0, failed: 0, incomplete: 0 },
      { date: '2026-01-08', count: 1, succeeded: 1, failed: 0, incomplete: 0 },
    ],
    command_mix: [
      {
        root: 'nmap',
        category: 'Vulnerability Scanning',
        count: 3,
        succeeded: 2,
        failed: 1,
        incomplete: 0,
        average_elapsed_seconds: 14,
        total_elapsed_seconds: 42,
        last_started: '2026-01-03T00:00:00',
      },
      {
        root: 'curl',
        category: 'Network Diagnostics',
        count: 1,
        succeeded: 1,
        failed: 0,
        incomplete: 0,
        average_elapsed_seconds: 2,
        total_elapsed_seconds: 2,
        last_started: '2026-01-02T00:00:00',
      },
    ],
    constellation: [
      {
        id: 'run-star-1',
        root: 'nmap',
        category: 'Vulnerability Scanning',
        command: 'nmap -sT ip.darklab.sh',
        started: '2026-01-03T00:00:00',
        elapsed_seconds: 14,
        exit_code: 0,
        output_line_count: 12,
      },
    ],
    events: [
      { root: 'nmap', command: 'nmap -sT ip.darklab.sh', exit_code: 0, elapsed_seconds: 14 },
    ],
    windows: {
      activity: { days: 28, label: 'last 28 days' },
      command_mix: { days: 90, label: 'last 90 days' },
      constellation: { days: 90, label: 'last 90 days' },
    },
  },
  mobile = false,
  bindMobileSheet = undefined,
  attachActiveRunFromMonitor = undefined,
  killActiveRunFromMonitor = undefined,
  openHistoryWithFilters = undefined,
  restoreHistoryRun = undefined,
  pauseBackgroundRunStreamsForStatusMonitor = undefined,
  resumeBackgroundRunStreamsAfterStatusMonitor = undefined,
  tabs = [],
} = {}) {
  const responses = Array.isArray(runs[0]) ? runs : [runs]
  const insightResponses = Array.isArray(insights) ? insights : [insights]
  let responseIndex = 0
  let insightResponseIndex = 0
  const apiFetch = vi.fn((url) => {
    if (String(url) === '/status') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(status) })
    }
    if (String(url) === '/workspace/files') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(workspace) })
    }
    if (String(url) === '/history/stats') {
      return Promise.resolve({ ok: true, json: () => Promise.resolve(stats) })
    }
    if (String(url).startsWith('/history/insights')) {
      return Promise.resolve({
        ok: true,
        json: () => {
          const response = insightResponses[Math.min(insightResponseIndex, insightResponses.length - 1)]
          insightResponseIndex += 1
          return Promise.resolve(response)
        },
      })
    }
    return Promise.resolve({
      ok: true,
      json: () => {
        const response = responses[Math.min(responseIndex, responses.length - 1)]
        responseIndex += 1
        return Promise.resolve({ runs: response })
      },
    })
  })
  window.matchMedia = vi.fn(() => ({ matches: mobile }))
  if (openHistoryWithFilters) window.openHistoryWithFilters = openHistoryWithFilters
  if (restoreHistoryRun) window.restoreHistoryRun = restoreHistoryRun
  return fromDomScripts(
    ['app/static/js/run_monitor.js'],
    {
      document,
      window,
      apiFetch,
      showToast: vi.fn(),
      getTabs: vi.fn(() => tabs),
      activateTab: vi.fn(),
      ...(pauseBackgroundRunStreamsForStatusMonitor
        ? { pauseBackgroundRunStreamsForStatusMonitor }
        : {}),
      ...(resumeBackgroundRunStreamsAfterStatusMonitor
        ? { resumeBackgroundRunStreamsAfterStatusMonitor }
        : {}),
      ...(attachActiveRunFromMonitor ? { attachActiveRunFromMonitor } : {}),
      ...(killActiveRunFromMonitor ? { killActiveRunFromMonitor } : {}),
      ...(bindMobileSheet ? { bindMobileSheet } : {}),
    },
    `{
      apiFetch,
      openRunMonitor: window.openRunMonitor,
      closeRunMonitor: window.closeRunMonitor,
    }`,
  )
}

describe('Status Monitor', () => {
  beforeEach(() => {
    document.body.className = ''
    document.body.innerHTML = `
      <div id="rail"></div>
      <div id="hud-status-cell">
        <span id="status">IDLE</span>
      </div>
    `
    delete window.openHistoryWithFilters
    delete window.restoreHistoryRun
    sessionStorage.clear()
    vi.useRealTimers()
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'visible',
    })
  })

  it('pauses background run streams while open and resumes them on close', async () => {
    const pauseBackgroundRunStreamsForStatusMonitor = vi.fn()
    const resumeBackgroundRunStreamsAfterStatusMonitor = vi.fn()
    const {
      apiFetch,
      openRunMonitor,
      closeRunMonitor,
    } = loadRunMonitor({
      pauseBackgroundRunStreamsForStatusMonitor,
      resumeBackgroundRunStreamsAfterStatusMonitor,
    })

    await openRunMonitor({ source: 'test' })

    expect(pauseBackgroundRunStreamsForStatusMonitor).toHaveBeenCalledTimes(1)
    expect(pauseBackgroundRunStreamsForStatusMonitor.mock.invocationCallOrder[0]).toBeLessThan(
      apiFetch.mock.invocationCallOrder[0],
    )

    closeRunMonitor()

    expect(resumeBackgroundRunStreamsAfterStatusMonitor).toHaveBeenCalledTimes(1)
  })

  it('renders active-run CPU and memory telemetry when available', async () => {
    const { openRunMonitor, closeRunMonitor } = loadRunMonitor({
      runs: [
        {
          run_id: 'run-telemetry',
          pid: 1234,
          command: 'amass enum -active -d darklab.sh',
          started: new Date().toISOString(),
          resource_usage: {
            status: 'ok',
            cpu_seconds: 8.4,
            memory_bytes: 536870912,
            process_count: 2,
          },
        },
      ],
    })

    await openRunMonitor({ source: 'test' })

    const cpuMeter = document.querySelector('.run-monitor-meter-cpu')
    expect(cpuMeter?.getAttribute('aria-label')).toBe('CPU collecting')
    expect(cpuMeter?.classList.contains('run-monitor-meter-collecting')).toBe(true)
    expect(cpuMeter?.style.getPropertyValue('--meter-percent')).toBe('75%')
    expect(cpuMeter?.querySelector('.run-monitor-meter-value')?.textContent).toBe('')
    expect(document.querySelector('.run-monitor-meter-mem')?.getAttribute('aria-label')).toBe('MEM 512 MB')
    expect(document.querySelector('.run-monitor-meter-mem')?.style.getPropertyValue('--meter-percent')).toBe('50%')
    expect(document.querySelector('.run-monitor-spark-panel')?.textContent).toContain('CPU/MEM 60s')
    expect(document.querySelector('.run-monitor-spark-values')).toBeNull()
    expect([...document.querySelectorAll('.run-monitor-meta-chip')].map(chip => chip.textContent)).toEqual(
      expect.arrayContaining(['run run-tele', 'pid 1234']),
    )
    expect(document.querySelector('.run-monitor-item')?.children[1]).toBe(
      document.querySelector('.run-monitor-spark-panel'),
    )
    const showcaseChildren = [...document.querySelector('.status-monitor-showcase')?.children || []]
      .map(child => child.className)
    expect(showcaseChildren[0]).toContain('status-monitor-pulse-strip')
    expect(showcaseChildren[1]).toContain('status-monitor-runs-section')
    expect(showcaseChildren[2]).toContain('status-monitor-showcase-grid')

    closeRunMonitor()
  })

  it('renders unavailable telemetry chips when backend stats are absent', async () => {
    const { openRunMonitor, closeRunMonitor } = loadRunMonitor({
      runs: [
        {
          run_id: 'run-no-telemetry',
          pid: 1234,
          command: 'sleep 60',
          started: new Date().toISOString(),
        },
      ],
    })

    await openRunMonitor({ source: 'test' })

    expect(document.querySelector('.run-monitor-meter-cpu')?.getAttribute('aria-label')).toBe('CPU n/a')
    expect(document.querySelector('.run-monitor-meter-mem')?.getAttribute('aria-label')).toBe('MEM n/a')

    closeRunMonitor()
  })

  it('labels active runs owned by another live browser as monitor-only', async () => {
    const { openRunMonitor, closeRunMonitor } = loadRunMonitor({
      runs: [
        {
          run_id: 'run-other-client',
          pid: 1234,
          command: 'sleep 60',
          started: new Date().toISOString(),
          has_live_owner: true,
          owned_by_this_client: false,
        },
      ],
    })

    await openRunMonitor({ source: 'test' })

    expect(document.querySelector('.run-monitor-meta')?.textContent).toContain('another browser')

    closeRunMonitor()
  })

  it('offers attach and kill actions for runs owned by another live browser', async () => {
    const attachActiveRunFromMonitor = vi.fn(() => Promise.resolve(true))
    const killActiveRunFromMonitor = vi.fn(() => Promise.resolve(true))
    const { openRunMonitor } = loadRunMonitor({
      attachActiveRunFromMonitor,
      killActiveRunFromMonitor,
      runs: [
        {
          run_id: 'run-other-client',
          pid: 1234,
          command: 'sleep 60',
          started: new Date().toISOString(),
          has_live_owner: true,
          owned_by_this_client: false,
        },
      ],
    })

    await openRunMonitor({ source: 'test' })

    const buttons = [...document.querySelectorAll('.run-monitor-action-btn')]
    expect(buttons.map(button => button.textContent)).toEqual(['Attach', 'Kill'])
    expect(buttons[1].classList.contains('run-monitor-action-btn-kill')).toBe(true)
    buttons[0].click()
    await Promise.resolve()
    expect(attachActiveRunFromMonitor).toHaveBeenCalledWith(
      expect.objectContaining({ run_id: 'run-other-client' }),
    )

    await openRunMonitor({ source: 'test' })
    document.querySelectorAll('.run-monitor-action-btn')[1].click()
    await Promise.resolve()
    expect(killActiveRunFromMonitor).toHaveBeenCalledWith(
      expect.objectContaining({ run_id: 'run-other-client' }),
    )
    expect(document.getElementById('run-monitor')?.classList.contains('u-hidden')).toBe(false)
  })

  it('keeps kill available when another browser owns a run already attached locally', async () => {
    const attachActiveRunFromMonitor = vi.fn(() => Promise.resolve(true))
    const killActiveRunFromMonitor = vi.fn(() => Promise.resolve(true))
    const { openRunMonitor } = loadRunMonitor({
      attachActiveRunFromMonitor,
      killActiveRunFromMonitor,
      tabs: [{ id: 'tab-2', label: 'sleep 60', runId: 'run-other-client', attachMode: 'attached' }],
      runs: [
        {
          run_id: 'run-other-client',
          pid: 1234,
          command: 'sleep 60',
          started: new Date().toISOString(),
          has_live_owner: true,
          owned_by_this_client: false,
        },
      ],
    })

    await openRunMonitor({ source: 'test' })

    expect(document.querySelector('.run-monitor-meta')?.textContent).toContain('another browser')
    const buttons = [...document.querySelectorAll('.run-monitor-action-btn')]
    expect(buttons.map(button => button.textContent)).toEqual(['Kill'])
    buttons[0].click()
    await Promise.resolve()
    expect(attachActiveRunFromMonitor).not.toHaveBeenCalled()
    expect(killActiveRunFromMonitor).toHaveBeenCalledWith(
      expect.objectContaining({ run_id: 'run-other-client' }),
    )
  })

  it('shows attach again after an attached tab is closed', async () => {
    const attachActiveRunFromMonitor = vi.fn(() => Promise.resolve(true))
    const killActiveRunFromMonitor = vi.fn(() => Promise.resolve(true))
    const tabs = [{ id: 'tab-2', label: 'sleep 60', runId: 'run-other-client', attachMode: 'attached' }]
    const { openRunMonitor, closeRunMonitor } = loadRunMonitor({
      attachActiveRunFromMonitor,
      killActiveRunFromMonitor,
      tabs,
      runs: [
        {
          run_id: 'run-other-client',
          pid: 1234,
          command: 'sleep 60',
          started: new Date().toISOString(),
          has_live_owner: true,
          owned_by_this_client: false,
        },
      ],
    })

    await openRunMonitor({ source: 'test' })
    expect([...document.querySelectorAll('.run-monitor-action-btn')].map(button => button.textContent)).toEqual(['Kill'])

    closeRunMonitor()
    tabs.length = 0
    await openRunMonitor({ source: 'test' })

    expect([...document.querySelectorAll('.run-monitor-action-btn')].map(button => button.textContent)).toEqual(['Attach', 'Kill'])
    closeRunMonitor()
  })

  it('warms CPU samples while closed so first open can show a percent', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'))
    const started = new Date().toISOString()
    const { openRunMonitor, closeRunMonitor, apiFetch } = loadRunMonitor({
      runs: [
        [
          {
            run_id: 'run-warm',
            pid: 1234,
            command: 'nmap -sV darklab.sh',
            started,
            resource_usage: { status: 'ok', cpu_seconds: 5, memory_bytes: 4096 },
          },
        ],
        [
          {
            run_id: 'run-warm',
            pid: 1234,
            command: 'nmap -sV darklab.sh',
            started,
            resource_usage: { status: 'ok', cpu_seconds: 5.4, memory_bytes: 8192 },
          },
        ],
        [
          {
            run_id: 'run-warm',
            pid: 1234,
            command: 'nmap -sV darklab.sh',
            started,
            resource_usage: { status: 'ok', cpu_seconds: 5.4, memory_bytes: 8192 },
          },
        ],
      ],
    })

    document.dispatchEvent(new CustomEvent('app:status-changed', { detail: { status: 'running' } }))
    await Promise.resolve()
    await Promise.resolve()

    vi.setSystemTime(new Date('2026-01-01T00:00:01Z'))
    await vi.advanceTimersByTimeAsync(900)

    await openRunMonitor({ source: 'test' })

    expect(apiFetch.mock.calls.filter(([url]) => url === '/history/active')).toHaveLength(3)
    expect(document.querySelector('.run-monitor-meter-cpu')?.getAttribute('aria-label')).toBe('CPU 44%')
    expect(document.querySelector('.run-monitor-meter-mem')?.getAttribute('aria-label')).toBe('MEM 8.0 KB')

    closeRunMonitor()
  })

  it('does a quick follow-up refresh after opening on a baseline-only CPU sample', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'))
    const started = new Date().toISOString()
    const { openRunMonitor, closeRunMonitor, apiFetch } = loadRunMonitor({
      runs: [
        [
          {
            run_id: 'run-open-followup',
            pid: 1234,
            command: 'ffuf -u https://ip.darklab.sh/FUZZ',
            started,
            resource_usage: { status: 'ok', cpu_seconds: 2, memory_bytes: 4096 },
          },
        ],
        [
          {
            run_id: 'run-open-followup',
            pid: 1234,
            command: 'ffuf -u https://ip.darklab.sh/FUZZ',
            started,
            resource_usage: { status: 'ok', cpu_seconds: 2.9, memory_bytes: 4096 },
          },
        ],
      ],
    })

    await openRunMonitor({ source: 'test' })
    expect(document.querySelector('.run-monitor-meter-cpu')?.getAttribute('aria-label')).toBe('CPU collecting')

    vi.setSystemTime(new Date('2026-01-01T00:00:01Z'))
    await vi.advanceTimersByTimeAsync(900)

    expect(apiFetch.mock.calls.filter(([url]) => url === '/history/active')).toHaveLength(2)
    expect(document.querySelector('.run-monitor-meter-cpu')?.getAttribute('aria-label')).toBe('CPU 47%')

    closeRunMonitor()
  })

  it('reuses the active-run row, sparkline path, and meter elements across polls', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'))
    const started = new Date().toISOString()
    const { openRunMonitor, closeRunMonitor } = loadRunMonitor({
      runs: [
        [
          {
            run_id: 'run-stable',
            pid: 4242,
            command: 'nuclei -u darklab.sh',
            started,
            resource_usage: { status: 'ok', cpu_seconds: 1, memory_bytes: 4096 },
          },
        ],
        [
          {
            run_id: 'run-stable',
            pid: 4242,
            command: 'nuclei -u darklab.sh',
            started,
            resource_usage: { status: 'ok', cpu_seconds: 1.5, memory_bytes: 8192 },
          },
        ],
        [
          {
            run_id: 'run-stable',
            pid: 4242,
            command: 'nuclei -u darklab.sh',
            started,
            resource_usage: { status: 'ok', cpu_seconds: 4.5, memory_bytes: 16384 },
          },
        ],
      ],
    })

    await openRunMonitor({ source: 'test' })

    const itemBefore = document.querySelector('.run-monitor-item')
    const cpuPathBefore = document.querySelector('.run-monitor-sparkline-cpu')
    const memPathBefore = document.querySelector('.run-monitor-sparkline-mem')
    const cpuMeterBefore = document.querySelector('.run-monitor-meter-cpu')
    const memMeterBefore = document.querySelector('.run-monitor-meter-mem')
    const cpuPercentBefore = cpuMeterBefore?.style.getPropertyValue('--meter-percent')
    const cpuPathDBefore = cpuPathBefore?.getAttribute('d')

    vi.setSystemTime(new Date('2026-01-01T00:00:01Z'))
    await vi.advanceTimersByTimeAsync(900)

    expect(document.querySelector('.run-monitor-item')).toBe(itemBefore)
    expect(document.querySelector('.run-monitor-sparkline-cpu')).toBe(cpuPathBefore)
    expect(document.querySelector('.run-monitor-sparkline-mem')).toBe(memPathBefore)
    expect(document.querySelector('.run-monitor-meter-cpu')).toBe(cpuMeterBefore)
    expect(document.querySelector('.run-monitor-meter-mem')).toBe(memMeterBefore)
    expect(cpuMeterBefore?.style.getPropertyValue('--meter-percent')).not.toBe(cpuPercentBefore)
    expect(cpuPathBefore?.getAttribute('d')).not.toBe(cpuPathDBefore)
    expect(document.querySelectorAll('.run-monitor-item')).toHaveLength(1)

    closeRunMonitor()
  })

  it('drops a run row when the active set no longer contains it', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'))
    const started = new Date().toISOString()
    const { openRunMonitor, closeRunMonitor } = loadRunMonitor({
      runs: [
        [
          {
            run_id: 'run-finishing',
            pid: 1111,
            command: 'subfinder -d darklab.sh',
            started,
            resource_usage: { status: 'ok', cpu_seconds: 1, memory_bytes: 2048 },
          },
        ],
        [],
      ],
    })

    await openRunMonitor({ source: 'test' })
    expect(document.querySelectorAll('.run-monitor-item')).toHaveLength(1)

    await window.refreshRunMonitor()

    expect(document.querySelectorAll('.run-monitor-item')).toHaveLength(0)
    expect(document.querySelector('.run-monitor-empty')?.textContent).toBe('No active runs.')

    closeRunMonitor()
  })

  it('does not reload history insights on every active-run refresh', async () => {
    const { openRunMonitor, closeRunMonitor, apiFetch } = loadRunMonitor({ runs: [[], []] })

    await openRunMonitor({ source: 'test' })
    expect(apiFetch.mock.calls.filter(([url]) => url === '/history/insights')).toHaveLength(1)

    await window.refreshRunMonitor()
    expect(apiFetch.mock.calls.filter(([url]) => url === '/history/insights')).toHaveLength(1)

    closeRunMonitor()
  })

  it('refreshes history insights when active runs drain to zero', async () => {
    const baseInsights = {
      first_run_date: '2026-01-01',
      max_day_count: 1,
      activity: [{ date: '2026-01-01', count: 1, succeeded: 1, failed: 0, incomplete: 0 }],
      command_mix: [],
      constellation: [],
      events: [],
      windows: {
        activity: { days: 28, label: 'last 28 days' },
        command_mix: { days: 30, label: 'last 30 days' },
        constellation: { days: 30, label: 'last 30 days' },
      },
    }
    const changedInsights = {
      ...baseInsights,
      max_day_count: 2,
      activity: [{ date: '2026-01-01', count: 2, succeeded: 1, failed: 0, incomplete: 1 }],
    }
    const { openRunMonitor, closeRunMonitor, apiFetch } = loadRunMonitor({
      runs: [
        [{
          run_id: 'run-transition',
          pid: 1234,
          command: 'sleep 10',
          started: new Date().toISOString(),
        }],
        [],
      ],
      insights: [baseInsights, changedInsights],
    })

    await openRunMonitor({ source: 'test' })
    const initialSignature = document.querySelector('.status-monitor-showcase-grid')?.dataset.visualSignature

    await window.refreshRunMonitor()

    expect(apiFetch.mock.calls.filter(([url]) => url === '/history/insights')).toHaveLength(2)
    expect(document.querySelector('.status-monitor-showcase-grid')?.dataset.visualSignature).not.toBe(initialSignature)

    closeRunMonitor()
  })

  it('does not refresh insights on a 0 → >0 transition', async () => {
    // Insights-refresh trigger is locked to active-run count >0 → 0 only.
    // Starting a new run should not retrigger the load — the new run is
    // visible in the active runs panel and the pulse strip live.
    const { openRunMonitor, closeRunMonitor, apiFetch } = loadRunMonitor({
      runs: [
        [],
        [{
          run_id: 'run-new',
          pid: 1234,
          command: 'sleep 10',
          started: new Date().toISOString(),
        }],
      ],
    })

    await openRunMonitor({ source: 'test' })
    expect(apiFetch.mock.calls.filter(([url]) => url === '/history/insights')).toHaveLength(1)

    await window.refreshRunMonitor()
    expect(apiFetch.mock.calls.filter(([url]) => url === '/history/insights')).toHaveLength(1)

    closeRunMonitor()
  })

  it('clamps off-scale stars above the p98 ceiling and renders an upward tick', async () => {
    const constellation = []
    for (let i = 0; i < 100; i += 1) {
      const day = String((i % 28) + 1).padStart(2, '0')
      const minute = String((i * 7) % 60).padStart(2, '0')
      constellation.push({
        id: `fast-${i}`,
        root: 'nuclei',
        category: 'Vulnerability Scanning',
        command: 'nuclei',
        started: `2026-01-${day}T12:${minute}:00`,
        elapsed_seconds: 3,
        exit_code: 0,
        output_line_count: 5,
      })
    }
    constellation.push({
      id: 'outlier',
      root: 'nuclei',
      category: 'Vulnerability Scanning',
      command: 'nuclei',
      started: '2026-01-15T13:00:00',
      elapsed_seconds: 7200,
      exit_code: 0,
      output_line_count: 5,
    })
    const insights = {
      first_run_date: '2026-01-01',
      max_day_count: 5,
      activity: [{ date: '2026-01-01', count: 1, succeeded: 1, failed: 0, incomplete: 0 }],
      command_mix: [],
      constellation,
      events: [],
      windows: {
        activity: { days: 28, label: 'last 28 days' },
        command_mix: { days: 30, label: 'last 30 days' },
        constellation: { days: 30, label: 'last 30 days' },
      },
    }
    const { openRunMonitor, closeRunMonitor } = loadRunMonitor({ insights })

    await openRunMonitor({ source: 'test' })

    const outlier = document.querySelector('.status-monitor-star-node[data-star-id="outlier"]')
    expect(outlier).toBeTruthy()
    expect(outlier.classList.contains('status-monitor-star-node-offscale')).toBe(true)
    expect(outlier.querySelector('.status-monitor-star-offscale-tick')).toBeTruthy()

    const fast = document.querySelector('.status-monitor-star-node[data-star-id="fast-0"]')
    expect(fast).toBeTruthy()
    expect(fast.classList.contains('status-monitor-star-node-offscale')).toBe(false)
    expect(fast.querySelector('.status-monitor-star-offscale-tick')).toBeNull()

    closeRunMonitor()
  })

  it('only connects same-root stars within 2h on the same calendar date', async () => {
    const constellation = [
      // Pair A: same day, 30 min apart → connects (1 streak path).
      {
        id: 's1a', root: 'nuclei', category: 'Vulnerability Scanning', command: 'nuclei',
        started: '2026-01-10T12:00:00', elapsed_seconds: 5, exit_code: 0, output_line_count: 5,
      },
      {
        id: 's1b', root: 'nuclei', category: 'Vulnerability Scanning', command: 'nuclei',
        started: '2026-01-10T12:30:00', elapsed_seconds: 5, exit_code: 0, output_line_count: 5,
      },
      // 3h gap on same day → no connection across this gap.
      {
        id: 's2', root: 'nuclei', category: 'Vulnerability Scanning', command: 'nuclei',
        started: '2026-01-10T15:30:00', elapsed_seconds: 5, exit_code: 0, output_line_count: 5,
      },
      // Same day still, 30 min after s2 (s2 → s3 within 2h) but a fourth point
      // the next day would not connect to s3.
      {
        id: 's3', root: 'nuclei', category: 'Vulnerability Scanning', command: 'nuclei',
        started: '2026-01-10T16:00:00', elapsed_seconds: 5, exit_code: 0, output_line_count: 5,
      },
      // Different day, 30 min after s3 in real time → must not connect (day-bucket break).
      {
        id: 's4', root: 'nuclei', category: 'Vulnerability Scanning', command: 'nuclei',
        started: '2026-01-11T00:30:00', elapsed_seconds: 5, exit_code: 0, output_line_count: 5,
      },
    ]
    const insights = {
      first_run_date: '2026-01-01',
      max_day_count: 5,
      activity: [{ date: '2026-01-10', count: 5, succeeded: 5, failed: 0, incomplete: 0 }],
      command_mix: [],
      constellation,
      events: [],
      windows: {
        activity: { days: 28, label: 'last 28 days' },
        command_mix: { days: 30, label: 'last 30 days' },
        constellation: { days: 30, label: 'last 30 days' },
      },
    }
    const { openRunMonitor, closeRunMonitor } = loadRunMonitor({ insights })

    await openRunMonitor({ source: 'test' })

    // Two segments connect: (s1a-s1b) and (s2-s3). The 3h gap between s1b
    // and s2 splits one. The next-day jump between s3 and s4 splits the other.
    const paths = document.querySelectorAll('.status-monitor-constellation-streak')
    expect(paths.length).toBe(2)

    closeRunMonitor()
  })

  it('omits the 24 axis label so the rightmost cluster reads as 20:00 to midnight', async () => {
    const { openRunMonitor, closeRunMonitor } = loadRunMonitor({})

    await openRunMonitor({ source: 'test' })

    const labels = [...document.querySelectorAll('.status-monitor-constellation-guide-label')]
      .map(node => node.textContent)
    expect(labels).toContain('00')
    expect(labels).toContain('20')
    expect(labels).not.toContain('24')

    closeRunMonitor()
  })

  it('does not poll history insights on a timer while the monitor is open', async () => {
    vi.useFakeTimers()
    const { openRunMonitor, closeRunMonitor, apiFetch } = loadRunMonitor({ runs: [[], []] })

    await openRunMonitor({ source: 'test' })
    expect(apiFetch.mock.calls.filter(([url]) => url === '/history/insights')).toHaveLength(1)

    await vi.advanceTimersByTimeAsync(3000)
    expect(apiFetch.mock.calls.filter(([url]) => url === '/history/insights')).toHaveLength(1)

    await vi.advanceTimersByTimeAsync(60000)
    expect(apiFetch.mock.calls.filter(([url]) => url === '/history/insights')).toHaveLength(1)

    closeRunMonitor()
  })

  it('uses CPU hysteresis and recent samples for the pulse strip', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'))
    const started = new Date().toISOString()
    const { openRunMonitor, closeRunMonitor } = loadRunMonitor({
      runs: [
        [
          {
            run_id: 'run-pulse',
            pid: 1234,
            command: 'nmap -sT ip.darklab.sh',
            started,
            resource_usage: { status: 'ok', cpu_seconds: 10, memory_bytes: 4096 },
          },
        ],
        [
          {
            run_id: 'run-pulse',
            pid: 1234,
            command: 'nmap -sT ip.darklab.sh',
            started,
            resource_usage: { status: 'ok', cpu_seconds: 10.4, memory_bytes: 4096 },
          },
        ],
        [
          {
            run_id: 'run-pulse',
            pid: 1234,
            command: 'nmap -sT ip.darklab.sh',
            started,
            resource_usage: { status: 'ok', cpu_seconds: 10.84, memory_bytes: 4096 },
          },
        ],
        [
          {
            run_id: 'run-pulse',
            pid: 1234,
            command: 'nmap -sT ip.darklab.sh',
            started,
            resource_usage: { status: 'ok', cpu_seconds: 11.35, memory_bytes: 4096 },
          },
        ],
      ],
    })

    await openRunMonitor({ source: 'test' })
    const strip = document.querySelector('.status-monitor-pulse-strip')
    expect(strip?.dataset.pulseSignature).toBe('1:0')
    expect(strip?.dataset.pulseCpuSamples).toBe('')
    expect(strip?.dataset.pulseLoad).toBe('idle')
    expect(strip?.style.getPropertyValue('--pulse-load-color')).toBe('var(--green)')
    const initialPlaceholderPath = pathXCoordinates(document.querySelector('.status-monitor-pulse-placeholder-line')?.getAttribute('d'))
    const initialPath = pathXCoordinates(document.querySelector('.status-monitor-pulse-line')?.getAttribute('d'))
    expect(initialPlaceholderPath[0]).toBeLessThan(0)
    expect(initialPath[0]).toBeGreaterThan(500)
    expect(initialPlaceholderPath[initialPlaceholderPath.length - 1]).toBeCloseTo(initialPath[0], 1)
    expect(initialPath.every((x, index) => index === 0 || x >= initialPath[index - 1])).toBe(true)

    vi.setSystemTime(new Date('2026-01-01T00:00:01Z'))
    await window.refreshRunMonitor()
    const firstCpuSignature = strip?.dataset.pulseSignature
    expect(firstCpuSignature).toBe('1:8')
    expect(strip?.dataset.pulseCpuSamples).toBe('40')
    expect(strip?.dataset.pulseLoad).toBe('busy')
    expect(strip?.style.getPropertyValue('--pulse-load-color')).toBe('var(--amber)')
    expect(document.querySelector('.run-monitor-summary')?.textContent).toContain('40% avg CPU')
    expect(strip?.querySelector('.status-monitor-pulse-meta')).toBeNull()
    await vi.advanceTimersByTimeAsync(700)
    const firstCpuPath = pathXCoordinates(document.querySelector('.status-monitor-pulse-line')?.getAttribute('d'))
    expect(firstCpuPath.length).toBeGreaterThan(2)
    expect(firstCpuPath.every((x, index) => index === 0 || x >= firstCpuPath[index - 1])).toBe(true)
    expect(document.querySelector('.status-monitor-pulse-track')?.getAttribute('transform')).toMatch(/^translate\(-/)

    vi.setSystemTime(new Date('2026-01-01T00:00:02Z'))
    await window.refreshRunMonitor()
    expect(strip?.dataset.pulseSignature).toBe(firstCpuSignature)
    expect(strip?.dataset.pulseCpuSamples).toBe('40,44')
    expect(document.querySelector('.run-monitor-summary')?.textContent).toContain('44% avg CPU')

    vi.setSystemTime(new Date('2026-01-01T00:00:03Z'))
    await window.refreshRunMonitor()
    expect(strip?.dataset.pulseSignature).toBe('1:10')
    expect(strip?.dataset.pulseCpuSamples).toBe('40,44,51')
    expect(strip?.dataset.pulseLoad).toBe('busy')
    expect(document.querySelector('.run-monitor-summary')?.textContent).toContain('51% avg CPU')

    await vi.advanceTimersByTimeAsync(700)
    const movedTransform = document.querySelector('.status-monitor-pulse-track')?.getAttribute('transform')
    expect(movedTransform).toMatch(/^translate\(-/)
    closeRunMonitor()
    const reopenPromise = openRunMonitor({ source: 'test' })
    expect(document.querySelector('.status-monitor-pulse-strip')?.dataset.pulseLoad).toBe('idle')
    expect(document.querySelector('.status-monitor-pulse-strip')?.style.getPropertyValue('--pulse-load-color')).toBe('var(--green)')
    await reopenPromise
    const reopenedPlaceholderPath = pathXCoordinates(document.querySelector('.status-monitor-pulse-placeholder-line')?.getAttribute('d'))
    const reopenedPath = pathXCoordinates(document.querySelector('.status-monitor-pulse-line')?.getAttribute('d'))
    expect(document.querySelector('.status-monitor-pulse-track')?.getAttribute('transform')).toMatch(/^translate\(0(?:\.0)? 0\)$/)
    expect(reopenedPlaceholderPath[reopenedPlaceholderPath.length - 1]).toBeCloseTo(reopenedPath[0], 1)

    closeRunMonitor()
  })

  it('shows active-run loading state on open instead of stale cached rows', async () => {
    const activeRun = {
      run_id: 'run-loading-state',
      pid: 1234,
      command: 'sleep 10',
      started: new Date().toISOString(),
    }
    const { openRunMonitor, closeRunMonitor, apiFetch } = loadRunMonitor({ runs: [[activeRun], []] })

    const firstOpen = openRunMonitor({ source: 'test' })
    expect(apiFetch.mock.calls[0]?.[0]).toBe('/history/active')
    expect(document.querySelector('.run-monitor-summary')?.textContent).toBe('Loading active runs...')
    expect(document.querySelector('.status-monitor-runs-empty')?.textContent).toBe('Loading active runs...')
    expect(document.querySelector('.run-monitor-list')?.textContent).not.toContain('sleep 10')

    await firstOpen
    expect(document.querySelector('.run-monitor-list')?.textContent).toContain('sleep 10')
    closeRunMonitor()

    const reopen = openRunMonitor({ source: 'test' })
    expect(document.querySelector('.run-monitor-summary')?.textContent).toBe('Loading active runs...')
    expect(document.querySelector('.status-monitor-runs-empty')?.textContent).toBe('Loading active runs...')
    expect(document.querySelector('.run-monitor-list')?.textContent).not.toContain('sleep 10')

    await reopen
    expect(document.querySelector('.status-monitor-runs-empty')?.textContent).toBe('No active runs.')
    expect(document.querySelector('.run-monitor-list')?.textContent).not.toContain('sleep 10')
    closeRunMonitor()
  })

  it('opens as a status dashboard when there are no active runs', async () => {
    const { openRunMonitor, closeRunMonitor } = loadRunMonitor({ runs: [] })

    await expect(openRunMonitor({ source: 'test' })).resolves.toBe(true)

    expect(document.getElementById('run-monitor')?.classList.contains('u-hidden')).toBe(false)
    expect(document.getElementById('run-monitor')?.classList.contains('run-monitor-modal')).toBe(true)
    expect(document.body.classList.contains('run-monitor-desktop-open')).toBe(true)
    expect(document.querySelector('.run-monitor-summary')?.textContent).toBe('0 active · 12s uptime')
    expect(document.querySelector('.run-monitor-list')?.children.length).toBe(4)
    expect(document.querySelector('#run-monitor-title')?.textContent).toBe('Status Monitor')
    expect(document.querySelector('.status-monitor-pulse-strip')).not.toBeNull()
    expect(document.querySelectorAll('.status-monitor-pulse-line')).toHaveLength(1)
    expect(document.querySelectorAll('.status-monitor-pulse-placeholder-line')).toHaveLength(1)
    expect(document.querySelectorAll('.status-monitor-pulse-beat-glows')).toHaveLength(1)
    expect(document.querySelector('.status-monitor-pulse-title')).toBeNull()
    expect(document.querySelector('.status-monitor-pulse-segment')).toBeNull()
    expect(document.querySelector('.status-monitor-pulse-meta')).toBeNull()
    expect(document.querySelector('.status-monitor-pulse-glow')?.getAttribute('style')).toContain('--pulse-glow-opacity:')
    expect(document.querySelector('.status-monitor-pulse-line')?.getAttribute('d')).toMatch(/^M/)
    expect(document.querySelector('.status-monitor-health-pips')).toBeNull()
    expect(document.querySelector('.status-monitor-constellation-card')?.textContent).toContain('Command Constellation')
    expect(document.querySelector('.status-monitor-constellation-card')?.textContent).toContain('last 90 days')
    expect(document.querySelector('.status-monitor-constellation-card .status-monitor-category-legend')?.textContent).toContain('Vuln')
    expect(document.querySelectorAll('.status-monitor-constellation-guide-major')).toHaveLength(7)
    expect(document.querySelectorAll('.status-monitor-constellation-guide-minor')).toHaveLength(6)
    expect([...document.querySelectorAll('.status-monitor-constellation-guide-label')].map(label => label.textContent)).toEqual([
      '00',
      '04',
      '08',
      '12',
      '16',
      '20',
    ])
    expect(document.querySelector('.status-monitor-treemap-card')?.textContent).toContain('nmap')
    expect(document.querySelector('.status-monitor-treemap-card')?.textContent).toContain('last 90 days')
    expect(document.querySelector('.status-monitor-treemap-card .status-monitor-category-legend')?.textContent).toContain('Diag')
    const treemapBody = document.querySelector('.status-monitor-treemap')
    const treemapTile = document.querySelector('.status-monitor-treemap-tile')
    treemapBody.getBoundingClientRect = () => ({ left: 20, top: 24, width: 360, height: 160 })
    treemapTile.getBoundingClientRect = () => ({ left: 28, top: 32, width: 160, height: 90 })
    document.querySelector('.status-monitor-treemap-card .status-monitor-constellation-popover').getBoundingClientRect = () => ({
      left: 0,
      top: 0,
      width: 150,
      height: 76,
    })
    treemapTile?.dispatchEvent(new MouseEvent('pointermove', { bubbles: true, clientX: 210, clientY: 62 }))
    const treemapPopover = document.querySelector('.status-monitor-treemap-card .status-monitor-constellation-popover')
    expect(treemapPopover?.classList.contains('status-monitor-constellation-popover-visible')).toBe(true)
    expect(treemapPopover?.textContent).toContain('nmap')
    expect(treemapPopover?.textContent).toContain('3 runs mapped')
    expect(treemapPopover?.textContent).toContain('1 fail')
    expect(parseFloat(treemapPopover?.style.left || '0')).toBeLessThanOrEqual(202)
    expect(parseFloat(treemapPopover?.style.top || '0')).toBeGreaterThanOrEqual(8)
    expect(document.querySelector('.status-monitor-heatmap-card')?.textContent).toContain('Activity Heatmap')
    expect(document.querySelector('.status-monitor-heatmap-card')?.textContent).toContain('last 28 days')
    expect(document.querySelectorAll('.status-monitor-heatmap-cell')).toHaveLength(28)
    expect(document.querySelector('.status-monitor-heatmap-months')?.textContent).toContain('Jan')
    expect([...document.querySelectorAll('.status-monitor-heatmap-weekday')].map(el => el.textContent)).toEqual(['Mon', 'Wed', 'Fri'])
    expect(document.querySelectorAll('.status-monitor-heatmap-legend-swatch')).toHaveLength(5)
    expect(document.querySelector('[data-date="2026-01-05"]')?.style.gridColumn).toBe('2')
    expect(document.querySelector('[data-date="2026-01-05"]')?.style.gridRow).toBe('1')
    expect(document.querySelector('[data-date="2026-01-01"]')?.classList.contains('status-monitor-heatmap-out-of-range')).toBe(true)
    expect(document.querySelector('[data-date="2026-01-05"]')?.hasAttribute('title')).toBe(false)
    const heatmapCell = document.querySelector('[data-date="2026-01-05"]')
    const heatmapBody = document.querySelector('.status-monitor-heatmap-body')
    heatmapBody.getBoundingClientRect = () => ({ left: 10, top: 20, width: 320, height: 140 })
    heatmapCell.getBoundingClientRect = () => ({ left: 180, top: 34, width: 9, height: 9 })
    document.querySelector('.status-monitor-heatmap-card .status-monitor-constellation-popover').getBoundingClientRect = () => ({
      left: 0,
      top: 0,
      width: 120,
      height: 60,
    })
    heatmapCell?.dispatchEvent(new MouseEvent('pointermove', { bubbles: true, clientX: 290, clientY: 80 }))
    const heatmapPopover = document.querySelector('.status-monitor-heatmap-card .status-monitor-constellation-popover')
    expect(heatmapPopover?.classList.contains('status-monitor-constellation-popover-visible')).toBe(true)
    expect(heatmapPopover?.textContent).toContain('2026-01-05')
    expect(heatmapPopover?.textContent).toContain('1 run')
    expect(heatmapPopover?.textContent).toContain('0 success')
    expect(heatmapPopover?.textContent).toContain('1 incomplete')
    expect(parseFloat(heatmapPopover?.style.left || '0')).toBeLessThan(280)
    expect(parseFloat(heatmapPopover?.style.left || '0')).toBeGreaterThanOrEqual(8)
    expect(parseFloat(heatmapPopover?.style.top || '0')).toBeGreaterThanOrEqual(8)
    const firstPopoverLeft = heatmapPopover?.style.left
    const secondHeatmapCell = document.querySelector('[data-date="2026-01-03"]')
    secondHeatmapCell.getBoundingClientRect = () => ({ left: 92, top: 52, width: 9, height: 9 })
    secondHeatmapCell?.dispatchEvent(new MouseEvent('pointermove', { bubbles: true, clientX: 70, clientY: 62 }))
    expect(heatmapPopover?.textContent).toContain('2026-01-03')
    expect(heatmapPopover?.style.left).not.toBe(firstPopoverLeft)
    expect(document.querySelector('.status-monitor-event-ticker')?.textContent).toContain('nmap')
    expect([...document.querySelectorAll('.status-monitor-section-title')].map(title => title.textContent)).toContain('System')
    expect(document.querySelector('.status-monitor-runs-empty')?.textContent).toBe('No active runs.')
    expect(document.querySelectorAll('.status-monitor-star-ambient').length).toBeGreaterThan(100)
    expect(document.querySelector('.status-monitor-star-node')).not.toBeNull()
    expect(document.querySelector('.status-monitor-constellation-sparse')?.textContent).toBe('More runs will sharpen this map.')
    expect(document.querySelector('.status-monitor-star-failure-ring')).toBeNull()

    document.querySelector('.status-monitor-star-node').dispatchEvent(new Event('pointerover', { bubbles: true }))
    const starPopover = document.querySelector('.status-monitor-constellation-popover')
    expect(starPopover?.classList.contains('status-monitor-constellation-popover-visible')).toBe(true)
    expect(starPopover?.textContent).toContain('nmap')
    expect(starPopover?.textContent).toContain('exit 0')
    expect(starPopover?.textContent).toContain('12 lines')
    expect(starPopover?.style.left).toMatch(/px$/)
    expect(parseFloat(starPopover?.style.left || '0')).toBeGreaterThanOrEqual(8)

    const pulseStrip = document.querySelector('.status-monitor-pulse-strip')
    const pulseLine = document.querySelector('.status-monitor-pulse-line')
    const runsSection = document.querySelector('.status-monitor-runs-section')
    const visualGrid = document.querySelector('.status-monitor-showcase-grid')
    const eventRow = document.querySelector('.status-monitor-event-row')
    await window.refreshRunMonitor()
    expect(document.querySelector('.status-monitor-pulse-strip')).toBe(pulseStrip)
    expect(document.querySelector('.status-monitor-pulse-line')).toBe(pulseLine)
    expect(document.querySelector('.status-monitor-runs-section')).toBe(runsSection)
    expect(document.querySelector('.status-monitor-runs-section')?.previousElementSibling).toBe(pulseStrip)
    expect(document.querySelector('.status-monitor-showcase-grid')).toBe(visualGrid)
    expect(document.querySelectorAll('.status-monitor-showcase-grid')).toHaveLength(1)
    expect(document.querySelector('.status-monitor-event-row')).toBe(eventRow)

    closeRunMonitor()
  })

  it('opens history from command territory tiles', async () => {
    const openHistoryWithFilters = vi.fn()
    const { openRunMonitor } = loadRunMonitor({ runs: [], openHistoryWithFilters })

    await expect(openRunMonitor({ source: 'test' })).resolves.toBe(true)

    document.querySelector('.status-monitor-treemap-tile')?.dispatchEvent(
      new MouseEvent('click', { bubbles: true, cancelable: true }),
    )

    expect(openHistoryWithFilters).toHaveBeenCalledWith({ type: 'runs', commandRoot: 'nmap' })
    expect(document.getElementById('run-monitor')?.classList.contains('u-hidden')).toBe(true)
  })

  it('restores runs from constellation stars', async () => {
    const restoreHistoryRun = vi.fn(() => Promise.resolve('tab-restored'))
    const { openRunMonitor } = loadRunMonitor({ runs: [], restoreHistoryRun })

    await expect(openRunMonitor({ source: 'test' })).resolves.toBe(true)

    document.querySelector('.status-monitor-star-node')?.dispatchEvent(
      new MouseEvent('click', { bubbles: true, cancelable: true }),
    )
    await new Promise(resolve => setImmediate(resolve))

    expect(restoreHistoryRun).toHaveBeenCalledWith('run-star-1', { hidePanelOnSuccess: false })
    expect(document.getElementById('run-monitor')?.classList.contains('u-hidden')).toBe(true)
  })

  it('keeps failed constellation stars category-colored with a failure ring', async () => {
    const { openRunMonitor, closeRunMonitor } = loadRunMonitor({
      runs: [],
      insights: {
        days: 28,
        first_run_date: '2026-01-02',
        max_day_count: 1,
        activity: [
          { date: '2026-01-02', count: 1, succeeded: 0, failed: 1, incomplete: 0 },
        ],
        command_mix: [],
        constellation: [
          {
            id: 'run-star-failed',
            root: 'ffuf',
            category: 'Vulnerability Scanning',
            command: 'ffuf -u https://ip.darklab.sh/FUZZ',
            started: '2026-01-03T00:00:00',
            elapsed_seconds: 7,
            exit_code: 1,
            output_line_count: 5,
          },
          {
            id: 'run-star-terminated',
            root: 'ping',
            category: 'Network Diagnostics',
            command: 'ping ip.darklab.sh',
            started: '2026-01-03T01:00:00',
            elapsed_seconds: 12,
            exit_code: -15,
            output_line_count: 3,
          },
        ],
        events: [
          {
            root: 'ping',
            command: 'ping ip.darklab.sh',
            exit_code: -15,
            elapsed_seconds: 12,
          },
        ],
      },
    })

    await expect(openRunMonitor({ source: 'test' })).resolves.toBe(true)

    const failedStar = document.querySelector('.status-monitor-star-failed')
    expect(failedStar).not.toBeNull()
    expect(failedStar?.getAttribute('style')).toContain('--star-hue:')
    expect(failedStar?.getAttribute('fill')).toBeNull()
    expect(document.querySelectorAll('.status-monitor-star-failure-ring')).toHaveLength(1)
    expect(document.querySelectorAll('.status-monitor-star-failed')).toHaveLength(1)
    expect(document.querySelector('.status-monitor-event-failed')).toBeNull()
    expect(document.querySelector('.status-monitor-event-row')?.textContent).toContain('ping terminated')

    closeRunMonitor()
  })

  it('uses neutral category tones and normalized decorative seeds', async () => {
    const { openRunMonitor, closeRunMonitor } = loadRunMonitor({
      runs: [],
      insights: {
        days: 28,
        first_run_date: '2026-01-02',
        max_day_count: 1,
        activity: [],
        command_mix: [
          {
            root: 'CustomTool',
            category: 'Unmapped Bucket',
            count: 5,
            succeeded: 4,
            failed: 1,
            incomplete: 0,
            average_elapsed_seconds: 3,
            total_elapsed_seconds: 15,
          },
          {
            root: ' customtool ',
            category: ' unmapped bucket ',
            count: 4,
            succeeded: 4,
            failed: 0,
            incomplete: 0,
            average_elapsed_seconds: 2,
            total_elapsed_seconds: 8,
          },
        ],
        constellation: [
          {
            id: 'Same Star',
            root: 'CustomTool',
            category: 'Unmapped Bucket',
            command: 'customtool --scan',
            started: '2026-01-03T12:00:00',
            elapsed_seconds: 4,
            exit_code: 0,
            output_line_count: 8,
          },
          {
            id: ' same star ',
            root: ' customtool ',
            category: ' unmapped bucket ',
            command: 'customtool --scan',
            started: '2026-01-03T12:00:00',
            elapsed_seconds: 4,
            exit_code: 0,
            output_line_count: 8,
          },
        ],
        events: [],
      },
    })

    await expect(openRunMonitor({ source: 'test' })).resolves.toBe(true)

    const tiles = [...document.querySelectorAll('.status-monitor-treemap-tile')]
    expect(tiles).toHaveLength(2)
    expect(tiles[0].style.getPropertyValue('--category-hue')).toBe('0')
    expect(tiles[0].style.getPropertyValue('--category-saturation')).toBe('0%')
    expect(tiles[0].style.getPropertyValue('--category-saturation-strong')).toBe('0%')
    expect(tiles[0].style.getPropertyValue('--tile-glow-x')).toBe(tiles[1].style.getPropertyValue('--tile-glow-x'))
    expect(tiles[0].style.getPropertyValue('--tile-glow-y')).toBe(tiles[1].style.getPropertyValue('--tile-glow-y'))
    expect(tiles[0].style.getPropertyValue('--failure-alpha')).toBe('0.35')
    expect(tiles[0].style.getPropertyValue('--failure-stop')).toBe('12.0%')
    expect(tiles[0].style.getPropertyValue('--failure-fade')).toBe('42.0%')
    expect(document.querySelector('.status-monitor-treemap-card .status-monitor-category-legend-item')?.style.getPropertyValue('--legend-saturation')).toBe('0%')
    const details = [...document.querySelectorAll('.status-monitor-treemap-detail')]
    expect(details[0].textContent).toBe('5 · 80%')
    expect(details[1].textContent).toBe('4 runs')
    expect(document.querySelector('.status-monitor-treemap-outcomes')).toBeNull()

    const stars = [...document.querySelectorAll('.status-monitor-star-node .status-monitor-star')]
    expect(stars).toHaveLength(2)
    expect(stars[0].getAttribute('style')).toContain('--star-saturation:0%')
    expect(stars[0].getAttribute('style')).toContain('--star-age-glow:')
    expect(stars[0].getAttribute('cx')).toBe(stars[1].getAttribute('cx'))
    expect(stars[0].getAttribute('cy')).toBe(stars[1].getAttribute('cy'))
    const streak = document.querySelector('.status-monitor-constellation-streak')
    expect(streak).not.toBeNull()
    expect(streak?.getAttribute('style')).toContain('--star-saturation:0%')
    expect(streak?.getAttribute('d')).toMatch(/^M/)

    closeRunMonitor()
  })

  it('uses a squarified command territory layout for small tiles', async () => {
    const command_mix = [
      ['nmap', 48],
      ['ffuf', 22],
      ['httpx', 16],
      ['subfinder', 12],
      ['katana', 9],
      ['naabu', 8],
      ['curl', 6],
      ['dig', 5],
      ['whois', 4],
      ['openssl', 4],
      ['sslscan', 3],
      ['jq', 3],
      ['grep', 2],
      ['wc', 2],
    ].map(([root, count], index) => ({
      root,
      category: index < 6 ? 'Recon' : 'Network Diagnostics',
      count,
      succeeded: count,
      failed: 0,
      incomplete: 0,
      average_elapsed_seconds: 2,
      total_elapsed_seconds: Number(count) * 2,
    }))
    const { openRunMonitor, closeRunMonitor } = loadRunMonitor({
      runs: [],
      insights: {
        days: 28,
        first_run_date: '2026-01-02',
        max_day_count: 0,
        activity: [],
        command_mix,
        constellation: [],
        events: [],
      },
    })

    await expect(openRunMonitor({ source: 'test' })).resolves.toBe(true)

    const aspects = [...document.querySelectorAll('.status-monitor-treemap-tile')].map((tile) => {
      const width = parseFloat(tile.style.width || '0')
      const height = parseFloat(tile.style.height || '0')
      return Math.max(width / height, height / width)
    })
    expect(aspects).toHaveLength(14)
    expect(Math.max(...aspects)).toBeLessThan(8)
    expect(document.querySelectorAll('.status-monitor-treemap-tile-compact').length).toBeGreaterThan(0)
    expect(document.querySelector('.status-monitor-treemap-tile')?.style.getPropertyValue('--category-hue')).toBe('207')

    closeRunMonitor()
  })

  it('keeps an ambient constellation visible before real run history exists', async () => {
    const { openRunMonitor, closeRunMonitor } = loadRunMonitor({
      runs: [],
      insights: {
        days: 28,
        first_run_date: null,
        max_day_count: 0,
        activity: [],
        command_mix: [],
        constellation: [],
        events: [],
      },
    })

    await expect(openRunMonitor({ source: 'test' })).resolves.toBe(true)

    expect(document.querySelectorAll('.status-monitor-star-ambient').length).toBeGreaterThan(100)
    expect([...document.querySelectorAll('.status-monitor-star-ambient')]
      .some(star => star.getAttribute('style')?.includes('--ambient-glow-alpha:0.54'))).toBe(true)
    expect(document.querySelector('.status-monitor-star-node')).toBeNull()
    expect(document.querySelector('.status-monitor-constellation-sparse')?.textContent).toBe('Run history will populate this constellation.')
    expect(document.querySelector('.status-monitor-constellation-empty')).toBeNull()

    closeRunMonitor()
  })

  it('uses mobile sheet chrome and shared sheet binding on mobile', async () => {
    document.body.classList.add('mobile-terminal-mode')
    const bindMobileSheet = vi.fn((sheet) => {
      const grab = document.createElement('div')
      grab.className = 'sheet-grab gesture-handle'
      grab.setAttribute('aria-hidden', 'true')
      sheet.insertBefore(grab, sheet.firstChild || null)
    })
    const { openRunMonitor } = loadRunMonitor({ runs: [], mobile: false, bindMobileSheet })

    await openRunMonitor({ source: 'mobile-peek' })

    const monitor = document.getElementById('run-monitor')
    expect(monitor?.classList.contains('mobile-sheet-surface')).toBe(true)
    expect(monitor?.classList.contains('chrome-drawer')).toBe(false)
    expect(document.body.classList.contains('run-monitor-mobile-open')).toBe(true)
    expect(document.querySelector('#run-monitor > .sheet-grab.gesture-handle')).not.toBeNull()
    expect(bindMobileSheet).toHaveBeenCalledWith(monitor, expect.objectContaining({ onClose: expect.any(Function) }))
  })

  it('calculates CPU from cumulative samples, keeps the last value, and caps display at 100%', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T00:00:00Z'))
    const started = new Date().toISOString()
    const { openRunMonitor, closeRunMonitor } = loadRunMonitor({
      runs: [
        [
          {
            run_id: 'run-busy',
            pid: 1234,
            command: 'yes > /dev/null',
            started,
            resource_usage: {
              status: 'ok',
              cpu_seconds: 10,
              memory_bytes: 4096,
            },
          },
        ],
        [
          {
            run_id: 'run-busy',
            pid: 1234,
            command: 'yes > /dev/null',
            started,
            resource_usage: {
              status: 'ok',
              cpu_seconds: 12,
              memory_bytes: 8192,
            },
          },
        ],
        [
          {
            run_id: 'run-busy',
            pid: 1234,
            command: 'yes > /dev/null',
            started,
            resource_usage: {
              status: 'ok',
              memory_bytes: 12288,
            },
          },
        ],
      ],
    })

    await openRunMonitor({ source: 'test' })
    expect(document.querySelector('.run-monitor-meter-cpu')?.getAttribute('aria-label')).toBe('CPU collecting')

    vi.setSystemTime(new Date('2026-01-01T00:00:01Z'))
    await window.refreshRunMonitor()
    expect(document.querySelector('.run-monitor-meter-cpu')?.getAttribute('aria-label')).toBe('CPU 100%')
    expect(document.querySelector('.run-monitor-meter-cpu')?.style.getPropertyValue('--meter-percent')).toBe('100%')
    expect(document.querySelector('.run-monitor-meter-mem')?.getAttribute('aria-label')).toBe('MEM 8.0 KB')

    vi.setSystemTime(new Date('2026-01-01T00:00:02Z'))
    await window.refreshRunMonitor()
    expect(document.querySelector('.run-monitor-meter-cpu')?.getAttribute('aria-label')).toBe('CPU 100%')
    expect(document.querySelector('.run-monitor-meter-mem')?.getAttribute('aria-label')).toBe('MEM 12 KB')

    closeRunMonitor()
  })

  it('adds the running status affordance and pulses it once per session', async () => {
    loadRunMonitor()
    const cell = document.getElementById('hud-status-cell')

    document.dispatchEvent(new CustomEvent('app:status-changed', { detail: { status: 'running' } }))

    expect(cell.classList.contains('hud-status-expandable')).toBe(true)
    expect(cell.classList.contains('hud-status-affordance-pulse')).toBe(true)
    expect(cell.title).toBe('Open Status Monitor')

    cell.classList.remove('hud-status-affordance-pulse')
    document.dispatchEvent(new CustomEvent('app:status-changed', { detail: { status: 'idle' } }))
    document.dispatchEvent(new CustomEvent('app:status-changed', { detail: { status: 'running' } }))

    expect(cell.classList.contains('hud-status-expandable')).toBe(true)
    expect(cell.classList.contains('hud-status-affordance-pulse')).toBe(false)

    document.dispatchEvent(new CustomEvent('app:status-changed', { detail: { status: 'ok' } }))
    expect(cell.classList.contains('hud-status-expandable')).toBe(false)
    expect(cell.title).toBe('')
  })
})
