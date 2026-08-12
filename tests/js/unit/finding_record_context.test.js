// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// @vitest-environment jsdom

import { describe, expect, it, vi } from 'vitest'
import { fromDomScripts } from './helpers/extract.js'

function response(payload, ok = true) {
  return { ok, json: vi.fn(async () => payload) }
}

function loadContext(openFindingRecordEditor = vi.fn(async options => options)) {
  return {
    ...fromDomScripts(
      ['app/static/js/features/findings/finding_record_context.js'],
      { openFindingRecordEditor },
      `({ loadConfirmedProjectTargets, openContextualFindingRecord })`,
      'globalThis.openFindingRecordEditor = openFindingRecordEditor;',
    ),
    openFindingRecordEditor,
  }
}

describe('contextual finding record launcher', () => {
  it('pages confirmed targets and passes the bounded list into the shared editor', async () => {
    const { openContextualFindingRecord, openFindingRecordEditor } = loadContext()
    const firstPage = Array.from({ length: 100 }, (_, index) => ({
      id: `target-${index}`,
      review_state: index === 12 ? 'pending' : 'confirmed',
    }))
    const request = vi.fn(async (url) => {
      if (url.includes('offset=0')) return response({ targets: firstPage, total: 101 })
      return response({ targets: [{ id: 'target-100', review_state: 'confirmed' }], total: 101 })
    })

    await openContextualFindingRecord({
      projectId: 'project-1',
      targetId: 'target-100',
      request,
      evidence: [{ evidence_type: 'atlas_entity', evidence_id: 'target-100' }],
    })

    expect(request).toHaveBeenCalledTimes(2)
    expect(openFindingRecordEditor).toHaveBeenCalledWith(expect.objectContaining({
      projectId: 'project-1',
      targetId: 'target-100',
      targets: expect.arrayContaining([{ id: 'target-100', review_state: 'confirmed' }]),
    }))
    expect(openFindingRecordEditor.mock.calls[0][0].targets).toHaveLength(100)
    expect(openFindingRecordEditor.mock.calls[0][0].targets.some(item => item.id === 'target-12')).toBe(false)
  })

  it('rejects unconfirmed contextual targets before opening the editor', async () => {
    const { loadConfirmedProjectTargets } = loadContext()
    const request = vi.fn(async () => response({
      targets: [{ id: 'target-pending', review_state: 'pending' }],
      total: 1,
    }))

    await expect(loadConfirmedProjectTargets('project-1', {
      request,
      requiredTargetId: 'target-pending',
    })).rejects.toThrow('Confirm this entity as a Project target')
  })

  it('prefills a launch target only when the source surface resolves one exact match', async () => {
    const { openContextualFindingRecord, openFindingRecordEditor } = loadContext()
    const targets = [
      { id: 'target-1', source_run_id: 'run-1' },
      { id: 'target-2', source_run_id: 'run-2' },
    ]

    await openContextualFindingRecord({
      projectId: 'project-1',
      targets,
      selectTargetId: items => items.find(item => item.source_run_id === 'run-2')?.id,
    })

    expect(openFindingRecordEditor).toHaveBeenCalledWith(expect.objectContaining({
      projectId: 'project-1',
      targetId: 'target-2',
      targets,
    }))
    expect(openFindingRecordEditor.mock.calls[0][0]).not.toHaveProperty('selectTargetId')
  })
})
