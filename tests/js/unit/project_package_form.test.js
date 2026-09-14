// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// @vitest-environment jsdom

import { afterEach, expect, it, vi } from 'vitest'

import { DarklabProjectPackages } from '../../../app/static/js/features/projects/project_packages.js'

afterEach(() => document.body.replaceChildren())

it.each(['presets', 'assessments'])('keeps typing in the same package notes field when %s arrive', async (pendingKind) => {
  const overlay = document.createElement('div')
  const body = document.createElement('div')
  overlay.append(body)
  document.body.append(overlay)
  let finishLoad
  const pending = new Promise((resolve) => { finishLoad = resolve })
  const summary = { project: { id: 'project-1', name: 'Evidence' }, counts: {} }
  const renderProjectExplorer = vi.fn()
  const controller = DarklabProjectPackages.createProjectPackagesController({
    apiFetch: vi.fn(async (url) => {
      if (url.includes(pendingKind)) await pending
      return { ok: true, json: async () => ({ presets: [], assessments: [] }) }
    }),
    wizardOverlay: overlay,
    wizardBody: body,
    getSelectedProjectId: () => 'project-1',
    selectedProject: () => summary.project,
    projectSummary: () => summary,
    projectRunItems: () => [],
    projectArtifactItems: () => [],
    projectTargetItems: () => [],
    projectFindingItems: () => [],
    projectFindingsLoaded: () => true,
    projectFilesEnabled: () => true,
    renderProjectExplorer,
    emptyProjectPanel: (text) => {
      const panel = document.createElement('div')
      panel.textContent = text
      return panel
    },
    makeProjectButton: (label, action) => {
      const button = document.createElement('button')
      button.textContent = label
      button.dataset.projectAction = action
      return button
    },
  })
  overlay.addEventListener('input', event => controller.handleInput(event))
  controller.openWizard('project-1')
  // Settle the other background read before focusing a live text entry.
  await new Promise(resolve => setTimeout(resolve, 0))
  const notes = body.querySelector('[data-project-package-field="notes"]')
  notes.focus()
  notes.value = 'Package notes'
  notes.dispatchEvent(new Event('input', { bubbles: true }))
  notes.setSelectionRange(8, 13)
  const rendered = body.firstElementChild

  finishLoad()
  await vi.waitFor(() => expect(body.firstElementChild).not.toBe(rendered))

  expect(notes.isConnected).toBe(true)
  expect(document.activeElement).toBe(notes)
  expect(notes.value).toBe('Package notes')
  expect([notes.selectionStart, notes.selectionEnd]).toEqual([8, 13])
  notes.setRangeText('handoff', notes.selectionStart, notes.selectionEnd, 'end')
  notes.dispatchEvent(new Event('input', { bubbles: true }))
  await controller.handleAction(body.querySelector('[data-project-action="package-wizard-next"]'))
  await controller.handleAction(body.querySelector('[data-project-action="package-wizard-back"]'))
  expect(body.querySelector('[data-project-package-field="notes"]').value).toBe('Package handoff')
})
