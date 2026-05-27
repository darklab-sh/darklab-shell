import { beforeEach, describe, expect, it } from 'vitest'
import { fromDomScripts } from './helpers/extract.js'

function loadDecide() {
  return fromDomScripts(
    ['app/static/js/tabs.js'],
    { document, window },
    '{ _decideTabbarChromeCollapsed, _TABBAR_CHROME_FIT_BUFFER }',
  )
}

describe('_decideTabbarChromeCollapsed', () => {
  let decide
  let BUFFER

  beforeEach(() => {
    ;({ _decideTabbarChromeCollapsed: decide, _TABBAR_CHROME_FIT_BUFFER: BUFFER } = loadDecide())
  })

  it('never collapses when the user has pinned the chrome open', () => {
    // Even with tabs that overflow badly, an explicit "expanded" pref wins.
    expect(decide({ pref: 'expanded', tabsWidth: 9000, chromeFullWidth: 400, barWidth: 800 })).toBe(false)
  })

  it('does not collapse in auto mode when tabs fit alongside the full chrome', () => {
    // 300 tabs + 200 chrome = 500, well under 1000 - buffer.
    expect(decide({ pref: 'auto', tabsWidth: 300, chromeFullWidth: 200, barWidth: 1000 })).toBe(false)
  })

  it('collapses in auto mode when tabs cannot fit alongside the full chrome', () => {
    // 700 tabs + 400 chrome = 1100 > 1000 - buffer.
    expect(decide({ pref: 'auto', tabsWidth: 700, chromeFullWidth: 400, barWidth: 1000 })).toBe(true)
  })

  it('returns false when measurements are not yet available', () => {
    expect(decide({ pref: 'auto', tabsWidth: 700, chromeFullWidth: 0, barWidth: 1000 })).toBe(false)
    expect(decide({ pref: 'auto', tabsWidth: 700, chromeFullWidth: 400, barWidth: 0 })).toBe(false)
  })

  it('respects the fit buffer at the boundary', () => {
    // Exactly at barWidth: tabs+chrome == barWidth, which exceeds (barWidth - buffer) → collapse.
    expect(decide({ pref: 'auto', tabsWidth: 600, chromeFullWidth: 400, barWidth: 1000 })).toBe(true)
    // Leave more than the buffer of slack → fits.
    expect(decide({ pref: 'auto', tabsWidth: 600 - BUFFER - 1, chromeFullWidth: 400, barWidth: 1000 })).toBe(false)
  })

  it('is state-independent — the decision does not take a current collapsed flag', () => {
    // Same inputs always yield the same result regardless of any prior state,
    // which is what prevents collapse/expand oscillation.
    const args = { pref: 'auto', tabsWidth: 700, chromeFullWidth: 400, barWidth: 1000 }
    expect(decide(args)).toBe(decide(args))
    expect(decide.length).toBe(1) // single options object, no separate state arg
  })
})
