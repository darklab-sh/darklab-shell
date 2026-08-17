// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, expect, it, vi } from 'vitest'
import { DarklabProjectActiveContext } from '../../../app/static/js/features/projects/project_active_context.js'

describe('project active context controller', () => {
  it('shares concurrent active project loads and refreshes again after the request settles', async () => {
    const projects = [
      { id: 'proj_1', name: 'Project One' },
      { id: 'proj_2', name: 'Project Two' },
      { id: 'proj_2', name: 'Project Two updated' },
    ]
    let requestIndex = 0
    const deferred = []
    const apiFetch = vi.fn(() => new Promise(resolve => {
      const index = requestIndex
      requestIndex += 1
      deferred.push(() => resolve({
        ok: true,
        json: vi.fn(async () => ({ project: projects[index] })),
      }))
    }))
    const emitUiEvent = vi.fn()
    const controller = DarklabProjectActiveContext.createProjectActiveContextController({
      apiFetch,
      emitUiEvent,
      projectDisplayName: project => project?.name || '',
      setValueColor: vi.fn(),
      syncProjectNotesForm: vi.fn(),
    })

    const firstLoad = controller.load()
    const secondLoad = controller.load()

    expect(apiFetch).toHaveBeenCalledTimes(1)
    deferred[0]()
    await expect(Promise.all([firstLoad, secondLoad])).resolves.toEqual([projects[0], projects[0]])
    expect(emitUiEvent).toHaveBeenLastCalledWith('app:active-project-changed', {
      project: projects[0],
      changed: true,
    })

    const nextLoad = controller.load()

    expect(apiFetch).toHaveBeenCalledTimes(2)
    deferred[1]()
    await expect(nextLoad).resolves.toBe(projects[1])
    expect(controller.project()).toBe(projects[1])

    const unchangedLoad = controller.load()
    expect(apiFetch).toHaveBeenCalledTimes(3)
    deferred[2]()
    await expect(unchangedLoad).resolves.toBe(projects[2])
    expect(emitUiEvent).toHaveBeenLastCalledWith('app:active-project-changed', {
      project: projects[2],
      changed: false,
    })
  })
})
