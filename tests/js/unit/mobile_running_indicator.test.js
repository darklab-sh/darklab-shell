/**
 * Contract-layer coverage for the mobile running-indicator surface in
 * app/static/js/mobile_chrome.js (`// ── Mobile non-active running-state
 * indicator ──` block). The running indicator is the trailing chip and pair
 * of edge-glow overlays that surface background-tab run state on mobile;
 * iOS-Safari-specific behavior (cold-container smooth-scroll drop, momentum-
 * scroll destabilization from sticky/absolute children) cannot run in jsdom
 * and is covered by the Playwright suite, but the contract layer — mount,
 * kill switch, chip visibility, chip count, active-tab exclusion, cycle-tap
 * dispatch — is fully jsdom-testable and pinned here.
 *
 * The module is a single IIFE so the tests re-load the source into a fresh
 * Function scope per case via `mountModule()`. A synchronous
 * requestAnimationFrame stub collapses the rAF-coalesced `syncRunningIndicator`
 * into one sync pass, and `location.search` is set before module load so the
 * `?ri=off` / `?ri=0` kill switch (read once at IIFE init) can be exercised.
 */

import { beforeEach, afterEach, describe, it, expect, vi } from 'vitest'
import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../../..')
const MOBILE_CHROME_SRC = readFileSync(
  resolve(REPO_ROOT, 'app/static/js/mobile_chrome.js'),
  'utf8',
)

function buildHarness({ includePeek = false } = {}) {
  document.body.innerHTML = `
    <div id="mobile-shell"></div>
    <div class="terminal-bar">
      <div class="tabs-bar" id="tabs-bar"></div>
      <span id="status"></span>
      <span id="run-timer"></span>
    </div>
    ${includePeek ? `
      <div id="mobile-recent-peek" class="recent-peek nav-item u-hidden" role="button" tabindex="0" aria-label="Show recent commands">
        <span class="recent-peek-handle" aria-hidden="true"></span>
        <span class="recent-peek-label">Recent</span>
        <span class="recent-peek-count" id="mobile-recent-peek-count">0</span>
        <span class="recent-peek-preview" id="mobile-recent-peek-preview"></span>
      </div>
    ` : ''}
  `
}

function addTab(id, { running = false, active = false } = {}) {
  const tabsBar = document.getElementById('tabs-bar')
  const el = document.createElement('div')
  el.className = 'tab' + (running ? ' running' : '') + (active ? ' active' : '')
  el.dataset.id = id
  tabsBar.appendChild(el)
  return el
}

function setLocationSearch(search) {
  // Module reads location.search exactly once at init time. jsdom allows
  // writing to href but not to search directly; use replaceState instead.
  window.history.replaceState({}, '', '/' + (search || ''))
}

function mountModule({
  mobileMode = true,
  tabs = [],
  activeTabId = null,
  locationSearch = '',
  activateTab = vi.fn(),
  includePeek = false,
  recentPreviewHistory = [],
  openRunMonitor = vi.fn(() => Promise.resolve(true)),
  reducedMotion = false,
} = {}) {
  buildHarness({ includePeek })
  if (mobileMode) document.body.classList.add('mobile-terminal-mode')
  else document.body.classList.remove('mobile-terminal-mode')
  setLocationSearch(locationSearch)

  for (const tab of tabs) {
    addTab(tab.id, { running: tab.st === 'running', active: tab.id === activeTabId })
  }

  const injectedGlobal = window
  injectedGlobal.getTabs = () => tabs
  injectedGlobal.getActiveTabId = () => activeTabId
  injectedGlobal.getActiveTab = () => tabs.find(tab => tab.id === activeTabId) || null
  injectedGlobal.activateTab = activateTab
  injectedGlobal.recentPreviewHistory = recentPreviewHistory
  injectedGlobal.openRunMonitor = openRunMonitor
  const origMatchMedia = window.matchMedia
  window.matchMedia = vi.fn((query) => ({
    matches: reducedMotion && String(query).includes('prefers-reduced-motion'),
    media: String(query || ''),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
  const origBindPressable = globalThis.bindPressable
  globalThis.bindPressable = (el, options = {}) => {
    el.addEventListener('click', (event) => options.onActivate && options.onActivate(event))
  }
  injectedGlobal.onUiEvent = (name, handler, options) => {
    document.addEventListener(name, handler, options)
    return () => document.removeEventListener(name, handler, options)
  }

  // Collapse rAF to sync so syncRunningIndicator resolves inside the test tick.
  const origRaf = window.requestAnimationFrame
  window.requestAnimationFrame = (cb) => {
    cb()
    return 0
  }

  // Execute the IIFE. The file wraps itself in
  // `(function initMobileChrome(global) {...})(typeof window !== 'undefined' ? window : this);`
  // so re-evaluating the source runs the init block once against our DOM.
  new Function('window', MOBILE_CHROME_SRC)(injectedGlobal)

  return {
    activateTab,
    openRunMonitor,
    tabs,
    restore() {
      window.requestAnimationFrame = origRaf
      window.matchMedia = origMatchMedia
      if (origBindPressable === undefined) delete globalThis.bindPressable
      else globalThis.bindPressable = origBindPressable
    },
  }
}

describe('mobile running-state indicator', () => {
  let ctx = null
  afterEach(() => {
    if (ctx && ctx.restore) ctx.restore()
    ctx = null
    document.body.className = ''
    document.body.innerHTML = ''
  })

  it('mounts the chip and both edge-glow overlays when enabled', () => {
    ctx = mountModule({
      tabs: [
        { id: 'tab-a', st: 'running' },
        { id: 'tab-b', st: 'idle' },
      ],
      activeTabId: 'tab-b',
    })

    const chip = document.getElementById('mobile-running-chip')
    expect(chip).not.toBeNull()
    expect(chip.tagName).toBe('BUTTON')
    expect(chip.getAttribute('aria-label')).toBe('Cycle to next running tab')
    expect(document.querySelectorAll('.tab-edge-glow.tab-edge-glow-left').length).toBe(1)
    expect(document.querySelectorAll('.tab-edge-glow.tab-edge-glow-right').length).toBe(1)
  })

  it('does not mount a separate mobile runtime pill because the header timer is canonical', () => {
    ctx = mountModule({
      tabs: [{ id: 'tab-a', st: 'running' }],
      activeTabId: 'tab-b',
    })

    expect(document.getElementById('mobile-runtime')).toBeNull()
  })

  it('?ri=off kill switch skips mounting the chip and edge glows entirely', () => {
    ctx = mountModule({
      tabs: [{ id: 'tab-a', st: 'running' }],
      activeTabId: 'tab-b',
      locationSearch: '?ri=off',
    })

    expect(document.getElementById('mobile-running-chip')).toBeNull()
    expect(document.querySelector('.tab-edge-glow')).toBeNull()
  })

  it('?ri=0 kill switch also skips mounting', () => {
    ctx = mountModule({
      tabs: [{ id: 'tab-a', st: 'running' }],
      activeTabId: 'tab-b',
      locationSearch: '?ri=0',
    })

    expect(document.getElementById('mobile-running-chip')).toBeNull()
    expect(document.querySelector('.tab-edge-glow')).toBeNull()
  })

  it('hides the chip when there are no running non-active tabs', () => {
    ctx = mountModule({
      tabs: [
        { id: 'tab-a', st: 'idle' },
        { id: 'tab-b', st: 'idle' },
      ],
      activeTabId: 'tab-a',
    })

    const chip = document.getElementById('mobile-running-chip')
    expect(chip.classList.contains('u-hidden')).toBe(true)
  })

  it('shows the chip with a count that equals the number of running non-active tabs', () => {
    ctx = mountModule({
      tabs: [
        { id: 'tab-a', st: 'running' },
        { id: 'tab-b', st: 'running' },
        { id: 'tab-c', st: 'running' },
        { id: 'tab-d', st: 'idle' },
      ],
      activeTabId: 'tab-d',
    })

    const chip = document.getElementById('mobile-running-chip')
    expect(chip.classList.contains('u-hidden')).toBe(false)
    expect(chip.querySelector('.mobile-running-count').textContent).toBe('3')
  })

  it('excludes the active tab from the count even if it is running', () => {
    ctx = mountModule({
      tabs: [
        { id: 'tab-a', st: 'running' },
        { id: 'tab-b', st: 'running' },
        { id: 'tab-c', st: 'running' },
      ],
      activeTabId: 'tab-b',
    })

    const chip = document.getElementById('mobile-running-chip')
    expect(chip.classList.contains('u-hidden')).toBe(false)
    // tab-b is the active tab: count drops from 3 to 2.
    expect(chip.querySelector('.mobile-running-count').textContent).toBe('2')
  })

  it('replaces the mobile recents peek with Run Monitor while the active tab is running', () => {
    ctx = mountModule({
      includePeek: true,
      recentPreviewHistory: ['hostname'],
      tabs: [
        { id: 'tab-a', st: 'running', command: 'sleep 30' },
      ],
      activeTabId: 'tab-a',
    })

    const peek = document.getElementById('mobile-recent-peek')
    expect(peek.classList.contains('u-hidden')).toBe(false)
    expect(peek.dataset.peekMode).toBe('run-monitor')
    expect(document.getElementById('mobile-recent-peek-count').textContent).toBe('live')
    expect(document.querySelector('.recent-peek-label').textContent).toBe('Run Monitor')
    expect(document.getElementById('mobile-recent-peek-preview').textContent).toBe('sleep 30')
    expect(peek.classList.contains('recent-peek-run-monitor-wiggle')).toBe(true)
  })

  it('opens Run Monitor from the running peek instead of the recents sheet', () => {
    const openRunMonitor = vi.fn(() => Promise.resolve(true))
    ctx = mountModule({
      includePeek: true,
      openRunMonitor,
      tabs: [{ id: 'tab-a', st: 'running', command: 'sleep 30' }],
      activeTabId: 'tab-a',
    })

    document.getElementById('mobile-recent-peek').click()

    expect(openRunMonitor).toHaveBeenCalledWith({ source: 'mobile-peek' })
  })

  it('shows elapsed time for the active mobile Run Monitor peek when runStart is known', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-01-01T00:00:05Z'))
    ctx = mountModule({
      includePeek: true,
      tabs: [
        {
          id: 'tab-a',
          st: 'running',
          command: 'sleep 30',
          runStart: new Date('2026-01-01T00:00:00Z').getTime(),
        },
      ],
      activeTabId: 'tab-a',
    })

    expect(document.getElementById('mobile-recent-peek-count').textContent).toBe('0:05')

    vi.useRealTimers()
  })

  it('suppresses the mobile Run Monitor peek wiggle for reduced motion', () => {
    ctx = mountModule({
      includePeek: true,
      reducedMotion: true,
      tabs: [{ id: 'tab-a', st: 'running', command: 'sleep 30' }],
      activeTabId: 'tab-a',
    })

    expect(document.getElementById('mobile-recent-peek').classList.contains('recent-peek-run-monitor-wiggle')).toBe(false)
  })

  it('returns the peek to recents after the active run finalization hold expires', () => {
    vi.useFakeTimers()
    ctx = mountModule({
      includePeek: true,
      recentPreviewHistory: ['hostname'],
      tabs: [{ id: 'tab-a', st: 'running', command: 'sleep 30' }],
      activeTabId: 'tab-a',
    })

    ctx.tabs[0].st = 'ok'
    document.dispatchEvent(new CustomEvent('app:tab-status-changed', {
      detail: { id: 'tab-a', status: 'ok', activeTabId: 'tab-a' },
    }))

    expect(document.getElementById('mobile-recent-peek').dataset.peekMode).toBe('run-monitor')

    vi.advanceTimersByTime(2600)

    expect(document.getElementById('mobile-recent-peek').dataset.peekMode).toBe('recents')
    expect(document.querySelector('.recent-peek-label').textContent).toBe('Recent')
    expect(document.getElementById('mobile-recent-peek-count').textContent).toBe('1')
    vi.useRealTimers()
  })

  it('activates the edge glow when a running non-active tab is only partially clipped off-screen', () => {
    ctx = mountModule({
      tabs: [
        { id: 'tab-a', st: 'running' },
        { id: 'tab-b', st: 'running' },
        { id: 'tab-c', st: 'idle' },
      ],
      activeTabId: 'tab-c',
    })

    const tabsBar = document.getElementById('tabs-bar')
    const tabA = tabsBar.querySelector('.tab[data-id="tab-a"]')
    const tabB = tabsBar.querySelector('.tab[data-id="tab-b"]')
    const tabC = tabsBar.querySelector('.tab[data-id="tab-c"]')

    tabsBar.getBoundingClientRect = () => ({
      left: 100,
      right: 300,
      top: 0,
      bottom: 32,
      width: 200,
      height: 32,
    })
    tabA.getBoundingClientRect = () => ({
      left: 96,
      right: 156,
      top: 0,
      bottom: 32,
      width: 60,
      height: 32,
    })
    tabB.getBoundingClientRect = () => ({
      left: 250,
      right: 304,
      top: 0,
      bottom: 32,
      width: 54,
      height: 32,
    })
    tabC.getBoundingClientRect = () => ({
      left: 180,
      right: 240,
      top: 0,
      bottom: 32,
      width: 60,
      height: 32,
    })

    document.dispatchEvent(new CustomEvent('app:tab-status-changed', {
      detail: { id: 'tab-a', status: 'running', activeTabId: 'tab-c' },
    }))

    expect(document.querySelector('.tab-edge-glow-left').classList.contains('is-active')).toBe(true)
    expect(document.querySelector('.tab-edge-glow-right').classList.contains('is-active')).toBe(true)
  })

  it('chip tap activates the next running non-active tab in tab-row order', () => {
    const activateTab = vi.fn()
    ctx = mountModule({
      tabs: [
        { id: 'tab-a', st: 'running' },
        { id: 'tab-b', st: 'idle' },
        { id: 'tab-c', st: 'running' },
      ],
      activeTabId: 'tab-b',
      activateTab,
    })

    const chip = document.getElementById('mobile-running-chip')
    chip.click()

    expect(activateTab).toHaveBeenCalledTimes(1)
    expect(activateTab).toHaveBeenCalledWith('tab-a', { focusComposer: false })
  })

  it('chip tap cycles through the running set and wraps around', () => {
    const activateTab = vi.fn()
    ctx = mountModule({
      tabs: [
        { id: 'tab-a', st: 'running' },
        { id: 'tab-b', st: 'running' },
        { id: 'tab-c', st: 'idle' },
      ],
      activeTabId: 'tab-c',
      activateTab,
    })

    const chip = document.getElementById('mobile-running-chip')
    chip.click()
    chip.click()
    chip.click()

    expect(activateTab).toHaveBeenCalledTimes(3)
    expect(activateTab.mock.calls[0][0]).toBe('tab-a')
    expect(activateTab.mock.calls[1][0]).toBe('tab-b')
    // Third tap wraps back to the first running tab.
    expect(activateTab.mock.calls[2][0]).toBe('tab-a')
  })

  it('re-syncs the chip count from tab lifecycle events instead of DOM mutation observers', () => {
    ctx = mountModule({
      tabs: [
        { id: 'tab-a', st: 'running' },
        { id: 'tab-b', st: 'idle' },
      ],
      activeTabId: 'tab-b',
    })

    const chip = document.getElementById('mobile-running-chip')
    expect(chip.querySelector('.mobile-running-count').textContent).toBe('1')

    ctx.tabs[1].st = 'running'
    document.dispatchEvent(new CustomEvent('app:tab-status-changed', {
      detail: { id: 'tab-b', status: 'running', activeTabId: 'tab-b' },
    }))

    // Active tab is excluded, so count stays at 1.
    expect(chip.querySelector('.mobile-running-count').textContent).toBe('1')

    ctx.tabs.push({ id: 'tab-c', st: 'running' })
    const tabEl = addTab('tab-c', { running: true, active: false })
    expect(tabEl).not.toBeNull()
    document.dispatchEvent(new CustomEvent('app:tab-created', {
      detail: { id: 'tab-c', label: 'tab c', activeTabId: 'tab-b' },
    }))

    expect(chip.querySelector('.mobile-running-count').textContent).toBe('2')
  })

  it('hides the chip and edge glows when the body is not in mobile-terminal-mode', () => {
    ctx = mountModule({
      mobileMode: false,
      tabs: [{ id: 'tab-a', st: 'running' }],
      activeTabId: 'tab-b',
    })

    const chip = document.getElementById('mobile-running-chip')
    // Chip is mounted but carries u-hidden when the desktop layout is active.
    expect(chip).not.toBeNull()
    expect(chip.classList.contains('u-hidden')).toBe(true)
    const left = document.querySelector('.tab-edge-glow-left')
    const right = document.querySelector('.tab-edge-glow-right')
    expect(left.classList.contains('is-active')).toBe(false)
    expect(right.classList.contains('is-active')).toBe(false)
  })
})
