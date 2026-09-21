// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { afterEach, beforeEach, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ fetch: vi.fn(), persist: vi.fn(), log: vi.fn(), emit: vi.fn() }))
vi.mock('../../../app/static/js/core/config.js', () => ({ APP_CONFIG: {} }))
vi.mock('../../../app/static/js/core/dom.js', () => ({ themeSelect: null }))
vi.mock('../../../app/static/js/core/state.js', () => ({ emitUiEvent: mocks.emit }))
vi.mock('../../../app/static/js/output.js', () => ({ buildPromptLabel: () => 'test $' }))
vi.mock('../../../app/static/js/session.js', () => ({ apiFetch: mocks.fetch, logClientError: mocks.log }))
vi.mock('../../../app/static/js/features/preferences/preferences.js', () => ({
  _persistCurrentSessionPreferences: mocks.persist, getPreference: () => '',
}))
vi.mock('../../../app/static/js/ui/ui_pressable.js', () => ({
  bindPressable: (button, { onActivate }) => button.addEventListener('click', onActivate),
}))

const active = { name: 'active', label: 'Active', vars: { '--bg': '#112233' } }
const choices = [active, { name: 'first', label: 'First', vars: { '--bg': '#445566' } },
  { name: 'second', label: 'Second', vars: { '--bg': '#778899' } }]
const response = () => ({ ok: true, json: async () => ({ current: active, themes: choices }) })
let theme

beforeEach(async () => {
  vi.resetModules()
  Object.values(mocks).forEach(mock => mock.mockReset())
  document.body.innerHTML = '<div id="theme-select" tabindex="-1"></div>'
  document.body.dataset.theme = 'active'
  window.ThemeRegistry = { current: structuredClone(active), themes: choices.map(({ name, label }) => ({ name, label })), details_loaded: false }
  window.ThemeCssVars = { current: structuredClone(active.vars), fallback: { '--bg': '#000000' } }
  theme = await import('../../../app/static/js/features/theme/theme.js')
})
afterEach(() => {
  delete window.ThemeRegistry
  delete window.ThemeCssVars
  delete window.applyThemeSelection
  delete window.syncThemeSelectionControls
  document.documentElement.removeAttribute('style')
})

it('keeps the active palette usable without fetching previews at startup', () => {
  theme.renderThemeSelectionOptions()
  expect(theme.applyThemeSelection('active', false)).toBe(true)
  expect(mocks.fetch).not.toHaveBeenCalled()
  expect(window.ThemeRegistry.current.vars).toEqual(active.vars)
  expect(window.ThemeCssVars.current).toEqual(active.vars)
})

it('shares one catalog request and applies only the newest rapid selection', async () => {
  let resolve
  mocks.fetch.mockImplementation(() => new Promise(done => { resolve = done }))
  const first = theme.applyThemeSelection('first')
  const second = theme.applyThemeSelection('second')
  await Promise.resolve()
  expect(mocks.fetch).toHaveBeenCalledTimes(1)
  // A late server preference must not replace the user's pending selection.
  expect(theme.applyThemeSelection('active', false)).toBe(false)
  resolve(response())
  expect(await first).toBe(false)
  expect(await second).toBe(true)
  expect(document.body.dataset.theme).toBe('second')
  expect(window.ThemeRegistry.current.vars).toEqual(choices[2].vars)
  expect(mocks.persist).toHaveBeenCalledTimes(1)
})

it('does not restore the server palette or an older choice after a newer loaded choice', async () => {
  let resolve
  mocks.fetch.mockImplementation(() => new Promise(done => { resolve = done }))
  const pending = theme.applyThemeSelection('first')
  await Promise.resolve()
  theme.applyThemeSelection('active')
  resolve(response())
  expect(await pending).toBe(false)
  expect(document.body.dataset.theme).toBe('active')
  expect(window.ThemeCssVars.current).toEqual(active.vars)
})

it('preserves the active theme through failure and allows a retry with complete previews', async () => {
  mocks.fetch.mockResolvedValueOnce({ ok: false, status: 503 }).mockResolvedValueOnce(response())
  await theme.renderThemeSelectionOptions({ load: true })
  expect(window.ThemeRegistry.current.vars).toEqual(active.vars)
  const retry = document.querySelector('#theme-select button')
  expect(retry.textContent).toBe('Retry loading themes')
  retry.click()
  await vi.waitFor(() => expect(document.querySelectorAll('.theme-card')).toHaveLength(3))
  expect(document.querySelector('[data-theme-name="second"]').style.getPropertyValue('--bg')).toBe('#778899')
  expect(document.querySelector('[data-theme-name="active"]').getAttribute('aria-pressed')).toBe('true')
  expect(mocks.fetch).toHaveBeenCalledTimes(2)
})

it('rejects malformed catalogs without caching a failure', async () => {
  mocks.fetch.mockResolvedValueOnce({ ok: true, json: async () => ({ themes: [{ name: 'incomplete' }] }) })
    .mockResolvedValueOnce(response())
  expect(await theme.applyThemeSelection('first')).toBe(false)
  expect(window.ThemeRegistry.details_loaded).toBe(false)
  expect(await theme.applyThemeSelection('first')).toBe(true)
})
