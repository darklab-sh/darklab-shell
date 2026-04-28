import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fromDomScripts } from './helpers/extract.js'

function loadRunMonitor({ runs = [] } = {}) {
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
  window.matchMedia = vi.fn(() => ({ matches: false }))
  return fromDomScripts(
    ['app/static/js/run_monitor.js'],
    {
      document,
      window,
      apiFetch,
      showToast: vi.fn(),
      getTabs: vi.fn(() => []),
      activateTab: vi.fn(),
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

    expect(document.querySelector('.run-monitor-meter-cpu')?.getAttribute('aria-label')).toBe('CPU n/a')
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

  it('opens as a header-only drawer when there are no active runs', async () => {
    const { openRunMonitor, closeRunMonitor } = loadRunMonitor({ runs: [] })

    await expect(openRunMonitor({ source: 'test' })).resolves.toBe(true)

    expect(document.getElementById('run-monitor')?.classList.contains('u-hidden')).toBe(false)
    expect(document.querySelector('.run-monitor-summary')?.textContent).toBe('0 active runs')
    expect(document.querySelector('.run-monitor-list')?.children.length).toBe(0)

    closeRunMonitor()
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
    expect(document.querySelector('.run-monitor-meter-cpu')?.getAttribute('aria-label')).toBe('CPU n/a')

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
