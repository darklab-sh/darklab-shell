import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fromDomScripts } from './helpers/extract.js'

function loadRunMonitor({
  runs = [],
  mobile = false,
  bindMobileSheet = undefined,
  attachActiveRunFromMonitor = undefined,
  tabs = [],
} = {}) {
  const responses = Array.isArray(runs[0]) ? runs : [runs]
  let responseIndex = 0
  const apiFetch = vi.fn(() => Promise.resolve({
    ok: true,
    json: () => {
      const response = responses[Math.min(responseIndex, responses.length - 1)]
      responseIndex += 1
      return Promise.resolve({ runs: response })
    },
  }))
  window.matchMedia = vi.fn(() => ({ matches: mobile }))
  return fromDomScripts(
    ['app/static/js/run_monitor.js'],
    {
      document,
      window,
      apiFetch,
      showToast: vi.fn(),
      getTabs: vi.fn(() => tabs),
      activateTab: vi.fn(),
      ...(attachActiveRunFromMonitor ? { attachActiveRunFromMonitor } : {}),
      ...(bindMobileSheet ? { bindMobileSheet } : {}),
    },
    `{
      apiFetch,
      openRunMonitor: window.openRunMonitor,
      closeRunMonitor: window.closeRunMonitor,
    }`,
  )
}

describe('Run Monitor', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <div id="rail"></div>
      <div id="hud-status-cell">
        <span id="status">IDLE</span>
      </div>
    `
    sessionStorage.clear()
    vi.useRealTimers()
    Object.defineProperty(document, 'visibilityState', {
      configurable: true,
      value: 'visible',
    })
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

  it('offers attach and takeover actions for runs owned by another live browser', async () => {
    const attachActiveRunFromMonitor = vi.fn(() => Promise.resolve(true))
    const { openRunMonitor } = loadRunMonitor({
      attachActiveRunFromMonitor,
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
    expect(buttons.map(button => button.textContent)).toEqual(['Attach', 'Take over'])
    buttons[0].click()
    await Promise.resolve()
    expect(attachActiveRunFromMonitor).toHaveBeenCalledWith(
      expect.objectContaining({ run_id: 'run-other-client' }),
      { takeover: false },
    )

    await openRunMonitor({ source: 'test' })
    document.querySelectorAll('.run-monitor-action-btn')[1].click()
    await Promise.resolve()
    expect(attachActiveRunFromMonitor).toHaveBeenCalledWith(
      expect.objectContaining({ run_id: 'run-other-client' }),
      { takeover: true },
    )
  })

  it('keeps takeover available when another browser owns a run already attached locally', async () => {
    const attachActiveRunFromMonitor = vi.fn(() => Promise.resolve(true))
    const { openRunMonitor } = loadRunMonitor({
      attachActiveRunFromMonitor,
      tabs: [{ id: 'tab-2', label: 'sleep 60', runId: 'run-other-client', attachMode: 'read-only' }],
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

    expect(document.querySelector('.run-monitor-meta')?.textContent).toContain('controlled elsewhere')
    const buttons = [...document.querySelectorAll('.run-monitor-action-btn')]
    expect(buttons.map(button => button.textContent)).toEqual(['Take over'])
    buttons[0].click()
    await Promise.resolve()
    expect(attachActiveRunFromMonitor).toHaveBeenCalledWith(
      expect.objectContaining({ run_id: 'run-other-client' }),
      { takeover: true },
    )
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

    expect(apiFetch).toHaveBeenCalledTimes(3)
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

    expect(apiFetch).toHaveBeenCalledTimes(2)
    expect(document.querySelector('.run-monitor-meter-cpu')?.getAttribute('aria-label')).toBe('CPU 47%')

    closeRunMonitor()
  })

  it('opens as a header-only drawer when there are no active runs', async () => {
    const { openRunMonitor, closeRunMonitor } = loadRunMonitor({ runs: [] })

    await expect(openRunMonitor({ source: 'test' })).resolves.toBe(true)

    expect(document.getElementById('run-monitor')?.classList.contains('u-hidden')).toBe(false)
    expect(document.querySelector('.run-monitor-summary')?.textContent).toBe('0 active runs')
    expect(document.querySelector('.run-monitor-list')?.children.length).toBe(0)

    closeRunMonitor()
  })

  it('uses mobile sheet chrome and shared sheet binding on mobile', async () => {
    const bindMobileSheet = vi.fn((sheet) => {
      const grab = document.createElement('div')
      grab.className = 'sheet-grab gesture-handle'
      grab.setAttribute('aria-hidden', 'true')
      sheet.insertBefore(grab, sheet.firstChild || null)
    })
    const { openRunMonitor } = loadRunMonitor({ runs: [], mobile: true, bindMobileSheet })

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
    expect(cell.title).toBe('Open Run Monitor')

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
