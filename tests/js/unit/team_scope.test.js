// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { loadAppFns } from './helpers/app_harness.js'

function apiResponse(payload = {}, { ok = true, status = 200, statusText = 'OK' } = {}) {
  return {
    ok,
    status,
    statusText,
    json: vi.fn(async () => payload),
  }
}

function defaultApiFetch({ teams = [], teamResponse = null } = {}) {
  return vi.fn(async (url) => {
    if (url === '/session/teams') return teamResponse || apiResponse({ teams })
    return apiResponse({})
  })
}

function dispatchScopeStorage(key, newValue) {
  const event = new Event('storage')
  Object.defineProperty(event, 'key', { value: key })
  Object.defineProperty(event, 'newValue', { value: newValue })
  window.dispatchEvent(event)
}

function expectScopedSurfacesReloaded(surfaces) {
  Object.entries(surfaces).forEach(([name, refresh]) => {
    expect(refresh, name).toHaveBeenCalledTimes(1)
  })
}

async function loadTeamScopeHarness({
  apiFetch = defaultApiFetch(),
  sessionId = 'tok_team_scope',
  localStorageEntries = {},
  surfaces = {},
} = {}) {
  const surfaceSpies = {
    reloadSessionHistory: vi.fn(() => Promise.resolve()),
    loadRecentValues: vi.fn(() => Promise.resolve()),
    refreshWorkspaceFileCache: vi.fn(() => Promise.resolve()),
    refreshActiveRuns: vi.fn(() => Promise.resolve()),
    refreshActiveProjectContext: vi.fn(() => Promise.resolve()),
    refreshStatusMonitor: vi.fn(() => Promise.resolve()),
    invalidateOptionsSecrets: vi.fn(() => Promise.resolve()),
    ...surfaces,
  }
  window.refreshActiveProjectContext = surfaceSpies.refreshActiveProjectContext
  window.refreshStatusMonitor = surfaceSpies.refreshStatusMonitor
  window.refreshActiveRuns = surfaceSpies.refreshActiveRuns
  window.invalidateOptionsSecrets = surfaceSpies.invalidateOptionsSecrets
  const harness = await loadAppFns({
    apiFetch,
    sessionId,
    localStorageEntries,
    reloadSessionHistory: surfaceSpies.reloadSessionHistory,
    loadRecentValues: surfaceSpies.loadRecentValues,
    refreshWorkspaceFileCache: surfaceSpies.refreshWorkspaceFileCache,
    refreshActiveRuns: surfaceSpies.refreshActiveRuns,
    refreshActiveProjectContext: surfaceSpies.refreshActiveProjectContext,
    refreshStatusMonitor: surfaceSpies.refreshStatusMonitor,
    invalidateOptionsSecrets: surfaceSpies.invalidateOptionsSecrets,
  })
  return { ...harness, surfaces: surfaceSpies }
}

describe('team scope selector', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    document.body.replaceChildren()
  })

  it('does not refresh team scopes on boot for anonymous personal sessions', async () => {
    const apiFetch = defaultApiFetch()

    await loadTeamScopeHarness({
      apiFetch,
      sessionId: 'anon_scope_boot',
    })
    document.dispatchEvent(new Event('DOMContentLoaded'))
    await Promise.resolve()

    const teamCalls = apiFetch.mock.calls.filter(([url]) => url === '/session/teams')
    expect(teamCalls).toHaveLength(0)
  })

  it('clears a stale stored team id after a successful team refresh', async () => {
    const sessionId = 'tok_scope_stale'
    const apiFetch = defaultApiFetch({
      teams: [{
        id: 'team_live_1',
        name: 'Live team',
        slug: 'live-team',
        member: { role: 'owner' },
      }],
    })
    const { storage, DarklabTeamScope } = await loadTeamScopeHarness({
      apiFetch,
      sessionId,
      localStorageEntries: { [`active_team_id:${sessionId}`]: 'team_stale_1' },
    })

    await DarklabTeamScope.refreshTeamScopes()

    expect(DarklabTeamScope.getActiveTeamId()).toBe('')
    expect(storage.getItem(`active_team_id:${sessionId}`)).toBeNull()
    expect(document.getElementById('team-scope-label').textContent).toBe('Personal')
    expect(document.getElementById('mobile-team-scope-label').textContent).toBe('Personal')
    expect(document.getElementById('team-scope-status').classList.contains('u-hidden')).toBe(true)
  })

  it('exposes active team capabilities for write affordance guards', async () => {
    const sessionId = 'tok_scope_capabilities'
    const apiFetch = defaultApiFetch({
      teams: [{
        id: 'team_live_1',
        name: 'Live team',
        slug: 'live-team',
        member: { role: 'viewer', capabilities: ['view_team'] },
      }],
    })
    const { DarklabTeamScope } = await loadTeamScopeHarness({
      apiFetch,
      sessionId,
      localStorageEntries: { [`active_team_id:${sessionId}`]: 'team_live_1' },
    })

    await DarklabTeamScope.refreshTeamScopes()

    expect(DarklabTeamScope.getActiveTeam()).toEqual(expect.objectContaining({
      id: 'team_live_1',
      capabilities: ['view_team'],
    }))
    expect(DarklabTeamScope.activeTeamScopeCan('view_team')).toBe(true)
    expect(DarklabTeamScope.activeTeamScopeCan('run_commands')).toBe(false)
    expect(DarklabTeamScope.deniedMessage('run commands in team scope'))
      .toBe("View-only team members can't run commands in team scope. Switch to Personal or ask for operator access.")
  })

  it('restores token-scoped team selection before runtime session handlers are ready', async () => {
    const sessionToken = 'tok_scope_reload'
    const apiFetch = defaultApiFetch({
      teams: [{
        id: 'team_live_1',
        name: 'Live team',
        slug: 'live-team',
        member: { role: 'operator' },
      }],
    })
    const { DarklabTeamScope } = await loadTeamScopeHarness({
      apiFetch,
      sessionId: '',
      localStorageEntries: {
        session_token: sessionToken,
        [`active_team_id:${sessionToken}`]: 'team_live_1',
      },
    })

    await DarklabTeamScope.refreshTeamScopes()

    expect(DarklabTeamScope.getActiveTeamId()).toBe('team_live_1')
    expect(document.getElementById('team-scope-label').textContent).toBe('Live team')
    expect(document.getElementById('mobile-team-scope-label').textContent).toBe('Live team')
  })

  it('renders scope choices as selectable rows with visible state markers', async () => {
    const sessionId = 'tok_scope_options'
    const apiFetch = defaultApiFetch({
      teams: [{
        id: 'team_live_1',
        name: 'Live team',
        slug: 'live-team',
        member: { role: 'operator' },
      }],
    })
    const { DarklabTeamScope } = await loadTeamScopeHarness({
      apiFetch,
      sessionId,
      localStorageEntries: { [`active_team_id:${sessionId}`]: 'team_live_1' },
    })

    DarklabTeamScope.open()

    await vi.waitFor(() => {
      expect(document.querySelector('[data-team-scope-option="team_live_1"]')?.textContent).toContain('Live team')
    })
    const personal = document.querySelector('[data-team-scope-option="personal"]')
    const team = document.querySelector('[data-team-scope-option="team_live_1"]')
    expect(personal.classList.contains('dropdown-item')).toBe(true)
    expect(personal.classList.contains('team-scope-option')).toBe(true)
    expect(personal.classList.contains('selection-row')).toBe(true)
    expect(personal.querySelector('.team-scope-option-marker')?.textContent).toBe('select')
    expect(team.getAttribute('aria-selected')).toBe('true')
    expect(team.classList.contains('is-selected')).toBe(true)
    expect(team.querySelector('.team-scope-option-marker')?.textContent).toBe('active')
  })

  it('clears team state without showing selector noise when team refresh returns 401', async () => {
    const sessionId = 'tok_scope_unauthorized'
    const apiFetch = defaultApiFetch({
      teamResponse: apiResponse({}, { ok: false, status: 401, statusText: 'Unauthorized' }),
    })
    const { DarklabTeamScope, logClientError, storage } = await loadTeamScopeHarness({
      apiFetch,
      sessionId,
      localStorageEntries: { [`active_team_id:${sessionId}`]: 'team_revoked_1' },
    })

    await DarklabTeamScope.refreshTeamScopes()

    expect(DarklabTeamScope.getActiveTeamId()).toBe('')
    expect(storage.getItem(`active_team_id:${sessionId}`)).toBeNull()
    expect(document.getElementById('team-scope-label').textContent).toBe('Personal')
    expect(document.getElementById('team-scope-trigger').classList.contains('is-error')).toBe(false)
    expect(document.getElementById('team-scope-status').classList.contains('u-hidden')).toBe(true)
    expect(logClientError).not.toHaveBeenCalled()
  })

  it('shows an inline error when the open selector cannot refresh teams', async () => {
    const sessionId = 'tok_scope_failed'
    const apiFetch = defaultApiFetch({
      teamResponse: apiResponse(
        { error: 'team refresh failed' },
        { ok: false, status: 500, statusText: 'Internal Server Error' },
      ),
    })
    const { DarklabTeamScope } = await loadTeamScopeHarness({
      apiFetch,
      sessionId,
      localStorageEntries: { [`active_team_id:${sessionId}`]: 'team_cached_1' },
    })

    DarklabTeamScope.open()

    await vi.waitFor(() => {
      expect(document.getElementById('team-scope-status').textContent).toBe('Could not load teams.')
    })
    expect(document.getElementById('team-scope-overlay').classList.contains('open')).toBe(true)
    expect(document.getElementById('team-scope-status').classList.contains('is-error')).toBe(true)
    expect(document.getElementById('team-scope-label').textContent).toBe('Team unavailable')
    expect(document.getElementById('mobile-team-scope-label').textContent).toBe('Team unavailable')
  })

  it('keeps cached teams selectable when a later menu refresh fails', async () => {
    const sessionId = 'tok_scope_cached_retry'
    let failRefresh = false
    const apiFetch = vi.fn(async (url) => {
      if (url === '/session/teams') {
        if (failRefresh) {
          return apiResponse(
            { error: 'team refresh failed' },
            { ok: false, status: 500, statusText: 'Internal Server Error' },
          )
        }
        return apiResponse({
          teams: [{
            id: 'team_cached_1',
            name: 'Cached Team',
            slug: 'cached-team',
            member: { role: 'operator' },
          }],
        })
      }
      return apiResponse({})
    })
    const { DarklabTeamScope } = await loadTeamScopeHarness({ apiFetch, sessionId })
    await DarklabTeamScope.refreshTeamScopes()

    failRefresh = true
    DarklabTeamScope.open()

    await vi.waitFor(() => {
      expect(document.querySelector('[data-team-scope-option="team_cached_1"]')).not.toBeNull()
    })
    expect(document.getElementById('team-scope-status').classList.contains('is-error')).toBe(false)
    expect(document.getElementById('team-scope-label').textContent).toBe('Personal')
    expect(document.getElementById('team-scope-status').textContent).toBe('')
  })

  it('keeps cached teams visible while marking a missing active team unavailable after refresh failure', async () => {
    const sessionId = 'tok_scope_cached_missing'
    let failRefresh = false
    const apiFetch = vi.fn(async (url) => {
      if (url === '/session/teams') {
        if (failRefresh) {
          return apiResponse(
            { error: 'team refresh failed' },
            { ok: false, status: 500, statusText: 'Internal Server Error' },
          )
        }
        return apiResponse({
          teams: [{
            id: 'team_cached_1',
            name: 'Cached Team',
            slug: 'cached-team',
            member: { role: 'operator' },
          }],
        })
      }
      return apiResponse({})
    })
    const { DarklabTeamScope, storage } = await loadTeamScopeHarness({ apiFetch, sessionId })
    await DarklabTeamScope.refreshTeamScopes()

    storage.setItem(`active_team_id:${sessionId}`, 'team_missing_1')
    failRefresh = true
    await DarklabTeamScope.refreshTeamScopes()

    expect(document.querySelector('[data-team-scope-option="team_cached_1"]')).not.toBeNull()
    expect(document.getElementById('team-scope-label').textContent).toBe('Team unavailable')
    expect(document.getElementById('mobile-team-scope-label').textContent).toBe('Team unavailable')
    expect(document.getElementById('team-scope-trigger').classList.contains('is-error')).toBe(true)
  })

  it('reloads scoped surfaces when storage events switch team scope', async () => {
    const sessionId = 'tok_scope_storage'
    const apiFetch = defaultApiFetch({
      teams: [{
        id: 'team_live_1',
        name: 'Live team',
        slug: 'live-team',
        member: { role: 'operator' },
      }],
    })
    const { DarklabTeamScope, surfaces } = await loadTeamScopeHarness({ apiFetch, sessionId })
    await DarklabTeamScope.refreshTeamScopes()
    Object.values(surfaces).forEach((refresh) => refresh.mockClear())

    dispatchScopeStorage(`active_team_id:${sessionId}`, 'team_live_1')

    expect(DarklabTeamScope.getActiveTeamId()).toBe('team_live_1')
    expect(document.getElementById('team-scope-label').textContent).toBe('Live team')
    expectScopedSurfacesReloaded(surfaces)
  })

  it('reloads scoped surfaces when selecting Personal from the scope selector', async () => {
    const sessionId = 'tok_scope_personal'
    const apiFetch = defaultApiFetch({
      teams: [{
        id: 'team_live_1',
        name: 'Live team',
        slug: 'live-team',
        member: { role: 'operator' },
      }],
    })
    const { DarklabTeamScope, storage, surfaces } = await loadTeamScopeHarness({
      apiFetch,
      sessionId,
      localStorageEntries: { [`active_team_id:${sessionId}`]: 'team_live_1' },
    })
    await DarklabTeamScope.refreshTeamScopes()

    Object.values(surfaces).forEach((refresh) => refresh.mockClear())
    DarklabTeamScope.open()
    document.querySelector('[data-team-scope-option="personal"]').click()

    expect(DarklabTeamScope.getActiveTeamId()).toBe('')
    expect(storage.getItem(`active_team_id:${sessionId}`)).toBeNull()
    expect(document.getElementById('team-scope-label').textContent).toBe('Personal')
    expect(document.getElementById('mobile-team-scope-label').textContent).toBe('Personal')
    expectScopedSurfacesReloaded(surfaces)
  })
})
