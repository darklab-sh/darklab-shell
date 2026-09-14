// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// @vitest-environment jsdom

import { afterEach, expect, it, vi } from 'vitest'
import { DarklabProjectWorkspaceBootstrap } from '../../../app/static/js/features/projects/project_workspace_bootstrap.js'
import { DarklabProjectWorkspaceEvents } from '../../../app/static/js/features/projects/project_workspace_events.js'

afterEach(() => { document.body.innerHTML = ''; vi.restoreAllMocks() })

it('handles each mobile or desktop Project click once across capture and bubbling', async () => {
  document.body.innerHTML = '<div id="project-workspace-modal"><div id="project-mobile-root"></div><div id="desktop-project"></div></div>'
  const modal = document.getElementById('project-workspace-modal')
  // Document-level dismissal is independent of this dispatch regression.
  vi.spyOn(document, 'addEventListener').mockImplementation(() => {})
  const linkLastRunToProject = vi.fn(async () => {})
  const events = DarklabProjectWorkspaceEvents.createProjectWorkspaceEventsController({
    projectWorkspaceModal: modal,
    linkLastRunToProject,
  })
  const bootstrap = DarklabProjectWorkspaceBootstrap.createProjectWorkspaceBootstrapController({
    projectWorkspaceModal: modal,
    projectWorkspaceEventsController: () => events,
  })
  bootstrap.bindAll()
  for (const containerId of ['project-mobile-root', 'desktop-project']) {
    const button = document.createElement('button')
    button.dataset.projectAction = 'link-last-run'
    button.dataset.projectId = containerId
    document.getElementById(containerId).appendChild(button)
    button.click()
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(linkLastRunToProject.mock.calls.filter(([id]) => id === containerId)).toHaveLength(1)
    button.click()
    await new Promise(resolve => setTimeout(resolve, 0))
    expect(linkLastRunToProject.mock.calls.filter(([id]) => id === containerId)).toHaveLength(2)
  }
})
