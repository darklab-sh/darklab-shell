// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, it, vi } from 'vitest'
import { startShellSession } from '../../../app/static/js/core/shell_startup.js'

function pending() {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

function setup() {
  const preferences = pending(), history = pending(), active = pending()
  const callbacks = {
    loadPreferences: vi.fn(() => preferences.promise),
    loadHistory: vi.fn(() => history.promise),
    loadActive: vi.fn(() => active.promise),
    hydrate: vi.fn(), restore: vi.fn(), onError: vi.fn(),
  }
  return { preferences, history, active, callbacks, startup: startShellSession(callbacks) }
}

describe('shell startup ordering', () => {
  it('restores without waiting for recall, after both preferences and active runs', async () => {
    const { preferences, history, active, callbacks, startup } = setup()
    active.resolve({ runs: [{ run_id: 'active' }] })
    await Promise.resolve()
    expect(callbacks.restore).not.toHaveBeenCalled()
    preferences.resolve()
    await startup.ready
    expect(callbacks.restore).toHaveBeenCalledExactlyOnceWith([{ run_id: 'active' }])
    expect(callbacks.hydrate).not.toHaveBeenCalled()
    history.resolve({ runs: [{ command: 'saved' }] })
    await vi.waitFor(() => expect(callbacks.hydrate).toHaveBeenCalledExactlyOnceWith([{ command: 'saved' }]))
  })

  it('holds fast recall until restored tabs are ready and recovers failed reads', async () => {
    const { preferences, history, active, callbacks, startup } = setup()
    history.resolve({ runs: [{ command: 'saved' }] })
    await Promise.resolve()
    expect(callbacks.hydrate).not.toHaveBeenCalled()
    preferences.resolve()
    active.reject(new Error('offline'))
    await startup.ready
    await vi.waitFor(() => expect(callbacks.hydrate).toHaveBeenCalledOnce())
    expect(callbacks.restore).toHaveBeenCalledExactlyOnceWith([])
    expect(callbacks.onError).toHaveBeenCalledWith('failed to load /history/active', expect.any(Error))
  })

  it('discards out-of-order responses after a scope change during startup', async () => {
    const { preferences, history, active, callbacks, startup } = setup()
    callbacks.loadPreferences.mockResolvedValueOnce(null)
    callbacks.loadActive.mockResolvedValueOnce({ runs: [{ run_id: 'new-scope' }] })
    callbacks.loadHistory.mockResolvedValueOnce({ runs: [{ command: 'new-scope' }] })
    startup.scopeChanged()
    await vi.waitFor(() => expect(callbacks.restore).toHaveBeenCalledExactlyOnceWith([{ run_id: 'new-scope' }]))
    preferences.resolve()
    active.resolve({ runs: [{ run_id: 'old-scope' }] })
    history.resolve({ runs: [{ command: 'old-scope' }] })
    await startup.ready
    await Promise.resolve()
    expect(callbacks.restore).toHaveBeenCalledOnce()
    expect(callbacks.hydrate).toHaveBeenCalledExactlyOnceWith([{ command: 'new-scope' }])
  })

  it('does not restore again or publish late recall after a post-startup identity change', async () => {
    const { preferences, history, active, callbacks, startup } = setup()
    preferences.resolve()
    active.resolve({ runs: [] })
    await startup.ready
    startup.scopeChanged()
    history.resolve({ runs: [{ command: 'old-scope' }] })
    await Promise.resolve()
    await Promise.resolve()
    expect(callbacks.loadPreferences).toHaveBeenCalledOnce()
    expect(callbacks.restore).toHaveBeenCalledOnce()
    expect(callbacks.hydrate).not.toHaveBeenCalled()
  })
})
