// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import path from 'node:path'

const template = readFileSync(path.resolve(process.cwd(), 'app/templates/diag_audit.html'), 'utf8')

describe('diagnostics audit viewer template', () => {
  it('keeps the filter and export controls in the real template', () => {
    expect(template).toContain('<form class="diag-audit-filter-form" method="get" action="/diag/audit">')
    expect(template).toContain('name="event_type"')
    expect(template).toContain('name="actor"')
    expect(template).toContain('name="team_id"')
    expect(template).toContain('name="project_id"')
    expect(template).toContain('name="target_type"')
    expect(template).toContain('name="target_id"')
    expect(template).toContain('name="correlation_id"')
    expect(template).toContain('name="date_from"')
    expect(template).toContain('name="date_to"')
    expect(template).toContain(
      'href="/diag/audit/export{% if data.export_query %}?{{ data.export_query }}{% endif %}"',
    )
    expect(template).toContain(
      'href="/diag/audit/export?format=json{% if data.export_query %}&amp;{{ data.export_query }}{% endif %}"',
    )
  })

  it('keeps the audit table columns in the real template', () => {
    expect(template).toContain('<table class="diag-table diag-audit-table">')
    expect(template).toContain('<col class="diag-audit-col-created">')
    expect(template).toContain('<col class="diag-audit-col-event">')
    expect(template).toContain('<col class="diag-audit-col-actor">')
    expect(template).toContain('<col class="diag-audit-col-target">')
    expect(template).toContain('<col class="diag-audit-col-scope">')
    expect(template).toContain('<col class="diag-audit-col-details">')
    expect(template).toContain('<td class="diag-audit-time">{{ event.created }}</td>')
    expect(template).toContain('<td class="diag-audit-target">')
    expect(template).toContain('<td class="diag-audit-scope">')
    expect(template).toContain('<td class="diag-audit-details-cell">')
  })

  it('keeps the native details drawer in the real template', () => {
    expect(template).toContain('<details class="diag-audit-details">')
    expect(template).toContain('<summary>details</summary>')
    expect(template).toContain('<pre>{{ event.details_json }}</pre>')
  })

  it('keeps disabled, empty, and pagination states in the real template', () => {
    expect(template).toContain('Audit logging is disabled.')
    expect(template).toContain('No audit events match these filters.')
    expect(template).toContain('Previous')
    expect(template).toContain('Next')
    expect(template).toContain('Exports cap at {{ data.export_max_rows }} rows')
  })
})
