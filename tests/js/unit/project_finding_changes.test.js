// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// @vitest-environment jsdom

import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  comparisonSummary,
  renderProjectFindingChangesSummary,
} from '../../../app/static/js/features/projects/project_finding_changes.js'

const changes = {
  assessment: { id: 'asmt_7', title: 'External assessment', status: 'completed' },
  comparison: {
    status: 'partial',
    total_checks: 4,
    comparable_checks: 2,
    no_baseline_checks: 1,
    incomparable_checks: 1,
  },
  rollup: {
    regressed: 1,
    new: 1,
    persistent: 2,
    not_observed: 1,
    incomparable: 1,
    total: 6,
  },
}

describe('Project finding-change handoff summary', () => {
  beforeEach(() => document.body.replaceChildren())

  it('uses the same remediation rollup and exact-cycle action on desktop and mobile', () => {
    const openAssessment = vi.fn()
    const bindPressable = vi.fn((node, { onActivate }) => {
      node.addEventListener('click', onActivate)
    })
    const desktop = renderProjectFindingChangesSummary({
      changes,
      projectId: 'prj_7',
      onOpenAssessment: openAssessment,
      bindPressable,
    })
    const mobile = renderProjectFindingChangesSummary({
      changes,
      projectId: 'prj_7',
      onOpenAssessment: openAssessment,
      bindPressable,
      mobile: true,
    })
    document.body.append(desktop, mobile)

    expect(desktop.textContent).toContain('2 of 4 checks comparable')
    expect(desktop.textContent).toContain('Regressed: 1')
    expect(desktop.textContent).toContain('Not observed: 1')
    expect(mobile.classList).toContain('is-mobile')
    expect(mobile.querySelectorAll('[data-finding-change-state]')).toHaveLength(5)
    expect(bindPressable).toHaveBeenCalledTimes(2)

    mobile.querySelector('button').click()
    expect(openAssessment).toHaveBeenCalledWith('prj_7', { assessmentId: 'asmt_7' })
  })

  it('describes no-baseline and pending comparisons without implying a fix', () => {
    expect(comparisonSummary({ status: 'no_baseline', no_baseline_checks: 2 })).toBe(
      '2 checks without a baseline',
    )
    expect(comparisonSummary({ status: 'pending' })).toBe('Comparison pending')
  })
})
