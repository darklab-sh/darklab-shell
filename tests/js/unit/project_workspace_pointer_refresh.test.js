// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// @vitest-environment jsdom

import { afterEach, expect, it, vi } from 'vitest'
import { DarklabProjectWorkspaceRenderer } from '../../../app/static/js/features/projects/project_workspace_renderer.js'

afterEach(() => { document.body.replaceChildren(); vi.useRealTimers() })

function pointer(type, pointerId = 1) {
  const event = new MouseEvent(type, { bubbles: true, button: 0 })
  Object.defineProperty(event, 'pointerId', { value: pointerId })
  return event
}

it.each(['pointerup', 'pointercancel', 'blur'])('keeps a pressed Project action until %s, then applies the latest render', (end) => {
  vi.useFakeTimers()
  const body = document.createElement('div')
  document.body.append(body)
  let label = 'Create finding'
  const activated = vi.fn()
  const renderProjectFindings = vi.fn((container) => {
    const button = document.createElement('button')
    button.dataset.projectAction = 'create-manual-finding'
    button.textContent = label
    button.addEventListener('click', activated)
    container.append(button)
  })
  const renderer = DarklabProjectWorkspaceRenderer.createProjectWorkspaceRendererController({
    projectExplorerBody: body,
    workspaceTab: () => 'findings',
    ensureSelectedProject: vi.fn(),
    selectedProject: () => ({ id: 'project-1' }),
    projectSummary: () => ({}),
    projectWorkspaceLoading: () => false,
    syncProjectForms: vi.fn(),
    renderProjectHeader: () => [document.createElement('header'), document.createElement('nav')],
    renderProjectFilterBar: () => null,
    renderProjectFindings,
    projectFindingServerFiltersActive: () => false,
    loadProjectFindings: async () => {},
  })
  renderer.renderExplorer()
  const opening = body.querySelector('button')
  opening.dispatchEvent(pointer('pointerdown'))
  label = 'Updated finding action'
  renderer.renderExplorer()
  renderer.renderExplorer()
  expect(opening.isConnected).toBe(true)
  expect(renderProjectFindings).toHaveBeenCalledTimes(1)
  // Releasing a different contact must not end the active pointer gesture.
  document.dispatchEvent(pointer('pointerup', 2))
  vi.runAllTimers()
  expect(opening.isConnected).toBe(true)
  if (end === 'blur') window.dispatchEvent(new Event('blur'))
  else document.dispatchEvent(pointer(end))
  expect(opening.isConnected).toBe(true)
  if (end === 'pointerup') opening.click()
  vi.runAllTimers()
  expect(activated).toHaveBeenCalledTimes(end === 'pointerup' ? 1 : 0)
  expect(body.textContent).toContain('Updated finding action')
  expect(opening.isConnected).toBe(false)
  expect(renderProjectFindings).toHaveBeenCalledTimes(2)
})
