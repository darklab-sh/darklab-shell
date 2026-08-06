// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { readFileSync } from 'fs'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'
import { stripEsmExports } from './helpers/extract.js'

const __dirname = dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = resolve(__dirname, '../../..')
const FINDING_TRIAGE_EDITOR_SRC = stripEsmExports(readFileSync(
  resolve(REPO_ROOT, 'app/static/js/features/findings/finding_triage_editor.js'),
  'utf8',
))

function mountEditor() {
  document.body.innerHTML = `
    <div id="finding-triage-overlay" class="modal-overlay mobile-sheet-overlay finding-triage-overlay u-hidden" aria-hidden="true">
      <div id="finding-triage-modal" class="modal-card modal-card-compact mobile-sheet-surface finding-triage-modal">
        <button type="button" id="finding-triage-close"></button>
        <div id="finding-triage-subtitle"></div>
        <div id="finding-triage-message" class="u-hidden"></div>
        <form id="finding-triage-form">
          <textarea id="finding-triage-remediation"></textarea>
          <div id="finding-triage-merge-summary"></div>
          <button type="button" id="finding-triage-merge-toggle" aria-expanded="false"></button>
          <div id="finding-triage-merge-panel" class="u-hidden">
            <input id="finding-triage-merge-search" type="search">
            <div id="finding-triage-merge-results"></div>
            <div id="finding-triage-merge-preview" class="u-hidden"></div>
            <div id="finding-triage-merge-actions" class="u-hidden">
              <button type="button" id="finding-triage-merge-apply"></button>
            </div>
          </div>
          <textarea id="finding-triage-verification-steps"></textarea>
          <select id="finding-triage-status" class="form-select form-control-compact">
            <option value="not_started">Not started</option>
            <option value="ready_to_verify">Ready to verify</option>
            <option value="verified">Verified</option>
            <option value="needs_retest">Needs retest</option>
            <option value="not_applicable">Not applicable</option>
          </select>
          <textarea id="finding-triage-verification-notes"></textarea>
          <button type="button" id="finding-triage-cancel"></button>
          <button type="submit" id="finding-triage-save"></button>
        </form>
        <form id="finding-record-form" class="u-hidden">
          <select id="finding-record-target" class="form-select"></select>
          <input id="finding-record-title">
          <select id="finding-record-severity" class="form-select">
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
            <option value="info">Info</option>
          </select>
          <select id="finding-record-confidence" class="form-select">
            <option value="unknown">Unknown</option>
            <option value="low">Low</option>
            <option value="medium">Medium</option>
            <option value="high">High</option>
          </select>
          <textarea id="finding-record-summary"></textarea>
          <textarea id="finding-record-impact"></textarea>
          <textarea id="finding-record-reproduction"></textarea>
          <input id="finding-record-cves">
          <input id="finding-record-cwes">
          <input id="finding-record-cvss-vector">
          <input id="finding-record-cvss-score">
          <textarea id="finding-record-references"></textarea>
          <section id="finding-record-evidence-section" class="u-hidden">
            <div id="finding-record-evidence"></div>
          </section>
          <button type="button" id="finding-record-cancel"></button>
          <button type="submit" id="finding-record-save"></button>
        </form>
      </div>
    </div>
  `
}

function jsonResponse(data, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(data),
  }
}

function installAppSelectStubs() {
  window.syncAppSelect = vi.fn((select) => {
    const wrap = select?.nextElementSibling;
    if (!wrap?.classList?.contains('app-select')) return;
    const trigger = wrap.querySelector('.app-select-trigger');
    const value = wrap.querySelector('.app-select-value');
    const selected = select.options[select.selectedIndex] || select.options[0] || null;
    if (value) value.textContent = selected ? selected.textContent : '';
    if (trigger) trigger.disabled = !!select.disabled;
    wrap.classList.toggle('disabled', !!select.disabled);
  });
  window.enhanceAppSelects = vi.fn((root = document) => {
    root.querySelectorAll('select.form-select').forEach((select) => {
      if (!select.nextElementSibling?.classList?.contains('app-select')) {
        const wrap = document.createElement('div');
        wrap.className = 'app-select';
        const trigger = document.createElement('button');
        trigger.type = 'button';
        trigger.className = 'app-select-trigger';
        const value = document.createElement('span');
        value.className = 'app-select-value';
        trigger.appendChild(value);
        wrap.appendChild(trigger);
        select.insertAdjacentElement('afterend', wrap);
      }
      window.syncAppSelect(select);
    });
  });
}

async function flushPromises(count = 5) {
  for (let index = 0; index < count; index += 1) {
    await Promise.resolve()
  }
}

function loadEditor() {
  new Function(FINDING_TRIAGE_EDITOR_SRC)()
}

describe('finding triage editor', () => {
  beforeEach(() => {
    mountEditor()
    delete window.DarklabFindingTriageEditor
    window.bindDismissible = vi.fn()
    window.bindMobileSheet = vi.fn()
    window.bindFocusTrap = vi.fn(() => ({ dispose: vi.fn() }))
    installAppSelectStubs()
    window.refocusComposerAfterAction = vi.fn()
    window.showConfirm = vi.fn(() => Promise.resolve('merge'))
  })

  it('loads, saves, and compacts remediation and verification details', async () => {
    const finding = { id: 'finding-1', title: 'Weak SMB signing' }
    const saved = vi.fn()
    const apiFetch = vi.fn((url, options = {}) => {
      if (url === '/findings/finding-1/triage' && !options.method) {
        return Promise.resolve(jsonResponse({
          triage: {
            remediation: 'Enable SMB signing.',
            verification_steps: 'Run nmap smb-security-mode again.',
            verification_status: 'ready_to_verify',
            verification_notes: 'Waiting on maintenance window.',
            remediation_id: 'rmd_smb_signing',
            remediation_source: 'remediation_group',
            remediation_updated_at: '2026-08-05T12:00:00+00:00',
          },
        }))
      }
      if (url === '/findings/finding-1/triage' && options.method === 'PUT') {
        return Promise.resolve(jsonResponse({
          triage: {
            remediation: JSON.parse(options.body).remediation,
            verification_steps: JSON.parse(options.body).verification_steps,
            verification_status: JSON.parse(options.body).verification_status,
            verification_notes: JSON.parse(options.body).verification_notes,
            remediation_id: 'rmd_smb_signing',
            remediation_source: 'remediation_group',
            remediation_updated_at: '2026-08-05T12:05:00+00:00',
          },
        }))
      }
      return Promise.resolve(jsonResponse({ error: 'unexpected request' }, 404))
    })
    window.apiFetch = apiFetch
    loadEditor()

    await window.DarklabFindingTriageEditor.open(finding, { onSaved: saved })
    await flushPromises()

    expect(document.getElementById('finding-triage-overlay').classList.contains('open')).toBe(true)
    expect(document.getElementById('finding-triage-remediation').value).toBe('Enable SMB signing.')
    expect(document.getElementById('finding-triage-status').value).toBe('ready_to_verify')

    document.getElementById('finding-triage-remediation').value = 'Require SMB signing.'
    document.getElementById('finding-triage-verification-steps').value = 'Retest port 445.'
    document.getElementById('finding-triage-status').value = 'verified'
    document.getElementById('finding-triage-form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises()

    expect(apiFetch).toHaveBeenCalledWith('/findings/finding-1/triage', expect.objectContaining({ method: 'PUT' }))
    const putCall = apiFetch.mock.calls.find(([, options]) => options?.method === 'PUT')
    expect(JSON.parse(putCall[1].body)).toEqual(expect.objectContaining({
      remediation: 'Require SMB signing.',
      verification_steps: 'Retest port 445.',
      verification_status: 'verified',
    }))
    expect(finding.triage).toEqual(expect.objectContaining({
      verification_status: 'verified',
      has_remediation: true,
      has_verification_steps: true,
      remediation_id: 'rmd_smb_signing',
      remediation_source: 'remediation_group',
      remediation_updated_at: '2026-08-05T12:05:00+00:00',
    }))
    expect(window.DarklabFindingTriageEditor.verificationStatusTone('verified')).toBe('green')
    expect(window.DarklabFindingTriageEditor.verificationStatusTone('needs_retest')).toBe('amber')
    expect(window.DarklabFindingTriageEditor.verificationStatusTone('ready_to_verify')).toBe('muted')
    expect(window.DarklabFindingTriageEditor.verificationStatusTone('not_applicable')).toBe('muted')
    expect(saved).toHaveBeenCalled()
    expect(document.getElementById('finding-triage-overlay').classList.contains('open')).toBe(false)
  })

  it('keeps view-only triage read-only and rejects oversized text before saving', async () => {
    const finding = { id: 'finding-2', title: 'Public exploit exposure' }
    const apiFetch = vi.fn((url, options = {}) => {
      if (url === '/findings/finding-2/triage' && !options.method) {
        return Promise.resolve(jsonResponse({
          triage: {
            remediation: 'Patch Samba.',
            verification_steps: '',
            verification_status: 'not_started',
            verification_notes: '',
          },
        }))
      }
      return Promise.resolve(jsonResponse({ triage: {} }))
    })
    window.apiFetch = apiFetch
    loadEditor()

    await window.DarklabFindingTriageEditor.open(finding, { canEdit: false })
    await flushPromises()

    expect(document.getElementById('finding-triage-save').disabled).toBe(true)
    expect(document.getElementById('finding-triage-remediation').disabled).toBe(true)
    expect(document.getElementById('finding-triage-merge-toggle').disabled).toBe(false)
    expect(document.getElementById('finding-triage-merge-search').disabled).toBe(false)
    expect(document.getElementById('finding-triage-merge-apply').disabled).toBe(true)
    expect(document.getElementById('finding-triage-message').textContent).toContain('cannot save changes')
    document.getElementById('finding-triage-form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises()
    expect(apiFetch).toHaveBeenCalledTimes(1)

    window.DarklabFindingTriageEditor.close()
    await window.DarklabFindingTriageEditor.open(finding)
    await flushPromises()
    document.getElementById('finding-triage-remediation').value = 'x'.repeat(20001)
    document.getElementById('finding-triage-form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises()

    expect(document.getElementById('finding-triage-save').disabled).toBe(false)
    expect(document.getElementById('finding-triage-message').textContent).toContain('20,000 characters')
    expect(apiFetch).toHaveBeenCalledTimes(2)
  })

  it('syncs the enhanced verification select across reopened findings and view-only mode', async () => {
    const apiFetch = vi.fn((url, options = {}) => {
      if (url === '/findings/finding-a/triage' && !options.method) {
        return Promise.resolve(jsonResponse({
          triage: {
            verification_status: 'ready_to_verify',
            remediation: '',
            verification_steps: '',
            verification_notes: '',
          },
        }))
      }
      if (url === '/findings/finding-b/triage' && !options.method) {
        return Promise.resolve(jsonResponse({
          triage: {
            verification_status: 'verified',
            remediation: 'Patched.',
            verification_steps: '',
            verification_notes: '',
          },
        }))
      }
      return Promise.resolve(jsonResponse({ error: 'unexpected request' }, 404))
    })
    window.apiFetch = apiFetch
    loadEditor()

    await window.DarklabFindingTriageEditor.open(
      { id: 'finding-a', title: 'Finding A', verification_status: 'not_started' },
    )
    await flushPromises()

    const statusSelect = document.getElementById('finding-triage-status')
    const appSelect = statusSelect.nextElementSibling
    expect(appSelect.querySelector('.app-select-value').textContent).toBe('Ready to verify')
    expect(appSelect.querySelector('.app-select-trigger').disabled).toBe(false)

    window.DarklabFindingTriageEditor.close()
    await window.DarklabFindingTriageEditor.open(
      { id: 'finding-b', title: 'Finding B', verification_status: 'verified' },
      { canEdit: false },
    )
    await flushPromises()

    expect(statusSelect.value).toBe('verified')
    expect(appSelect.querySelector('.app-select-value').textContent).toBe('Verified')
    expect(appSelect.querySelector('.app-select-trigger').disabled).toBe(true)
    expect(appSelect.classList.contains('disabled')).toBe(true)
    expect(window.syncAppSelect).toHaveBeenCalledWith(statusSelect)

    window.DarklabFindingTriageEditor.close()
    window.bindFocusTrap.mockClear()
    window.enhanceAppSelects.mockClear()
    window.apiFetch = vi.fn(() => Promise.resolve(jsonResponse({ error: 'Could not load details.' }, 500)))
    loadEditor()

    await window.DarklabFindingTriageEditor.open({ id: 'finding-error', title: 'Finding error' })
    await flushPromises()

    expect(document.getElementById('finding-triage-overlay').classList.contains('open')).toBe(true)
    expect(document.getElementById('finding-triage-message').textContent).toBe('Could not load details.')
    expect(window.enhanceAppSelects).toHaveBeenCalledWith(document.getElementById('finding-triage-overlay'))
    expect(window.bindFocusTrap).not.toHaveBeenCalled()
    expect(appSelect.querySelector('.app-select-trigger').disabled).toBe(true)
  })

  it('previews and explicitly merges remediation groups without changing verification fields', async () => {
    let triageReads = 0
    const saved = vi.fn()
    const apiFetch = vi.fn((url, options = {}) => {
      if (url === '/findings/finding-source/triage' && !options.method) {
        triageReads += 1
        return Promise.resolve(jsonResponse({
          triage: {
            remediation: 'Patch the shared service.',
            verification_steps: 'Retest the source observation.',
            verification_status: 'ready_to_verify',
            verification_notes: 'Keep this note separate.',
            remediation_id: 'rmd_source',
            remediation_group_id: triageReads > 1 ? 'rmg_explicit' : 'rmd_source',
            remediation_group_merged: triageReads > 1,
            remediation_group_member_count: triageReads > 1 ? 2 : 1,
          },
        }))
      }
      if (url.endsWith('/remediation-merge/candidates')) {
        return Promise.resolve(jsonResponse({ candidates: [{
          finding_id: 'finding-target',
          title: 'Imported shared issue',
          vulnerability_id: 'CVE-2026-12345',
          affected_subject: 'entity:target-2',
        }] }))
      }
      if (url.endsWith('/remediation-merge/preview')) {
        return Promise.resolve(jsonResponse({ preview: {
          source: { title: 'Source issue' },
          target: {
            title: 'Imported shared issue',
            review_state: 'important',
            has_remediation: true,
            remediation_preview: 'Apply the target-side patch.',
          },
          member_count: 2,
          observation_count: 2,
          preview_token: 'preview-token',
          observations: [
            { observation_id: 'obs_source', title: 'Source issue', validation_method: 'active_confirmation', vulnerability_id: 'CVE-2026-12345' },
            { observation_id: 'obs_target', title: 'Imported shared issue', validation_method: 'imported_assertion', vulnerability_id: 'CVE-2026-12345' },
          ],
        } }))
      }
      if (url.endsWith('/remediation-merge')) {
        return Promise.resolve(jsonResponse({ merge: { member_count: 2, observation_count: 2 } }))
      }
      return Promise.resolve(jsonResponse({ error: 'unexpected request' }, 404))
    })
    window.apiFetch = apiFetch
    loadEditor()

    await window.DarklabFindingTriageEditor.open(
      { id: 'finding-source', title: 'Source issue' },
      { onSaved: saved },
    )
    await flushPromises()

    document.getElementById('finding-triage-merge-toggle').click()
    const search = document.getElementById('finding-triage-merge-search')
    search.value = 'shared issue'
    search.dispatchEvent(new Event('input', { bubbles: true }))
    await new Promise(resolve => setTimeout(resolve, 275))
    await flushPromises()

    document.querySelector('.finding-triage-merge-candidate').click()
    await flushPromises()
    expect(document.getElementById('finding-triage-merge-preview').textContent).toContain('2 observations')
    expect(document.getElementById('finding-triage-merge-preview').textContent).toContain('verification steps, status, and notes will stay separate')
    expect(document.getElementById('finding-triage-merge-preview').textContent).toContain('current review state is Important')
    expect(document.getElementById('finding-triage-merge-preview').textContent).toContain('Apply the target-side patch.')

    document.getElementById('finding-triage-merge-apply').click()
    await flushPromises(10)

    const applyCall = apiFetch.mock.calls.find(([url]) => url.endsWith('/remediation-merge'))
    expect(JSON.parse(applyCall[1].body)).toEqual({
      target_finding_id: 'finding-target',
      preview_token: 'preview-token',
    })
    expect(window.showConfirm).toHaveBeenCalledWith(expect.objectContaining({ tone: 'warning' }))
    expect(document.getElementById('finding-triage-remediation').value).toBe('Patch the shared service.')
    expect(document.getElementById('finding-triage-verification-notes').value).toBe('Keep this note separate.')
    expect(document.getElementById('finding-triage-merge-summary').textContent).toContain('2 explicitly merged')
    expect(saved).toHaveBeenCalled()
  })

  it('creates a reviewed manual finding with normalized details and bounded source evidence', async () => {
    const saved = vi.fn()
    const apiFetch = vi.fn((url, options = {}) => Promise.resolve(jsonResponse({
      finding: {
        id: 'finding-manual',
        origin: 'manual',
        manual_revision: 1,
        ...JSON.parse(options.body),
      },
    }, 201)))
    window.apiFetch = apiFetch
    loadEditor()

    await window.DarklabFindingTriageEditor.openRecord({
      projectId: 'project-1',
      targets: [
        { id: 'target-confirmed', type: 'domain', value: 'app.example.test', review_state: 'confirmed' },
        { id: 'target-pending', type: 'domain', value: 'pending.example.test', review_state: 'pending' },
      ],
      defaults: {
        title: 'Finding from saved run output',
        summary: 'Two saved lines were selected as evidence.',
        severity: 'medium',
        confidence: 'unknown',
      },
      evidence: [{
        evidence_type: 'run_line',
        evidence_id: 'run-1',
        line_number: 7,
        snippet: '<script>alert(1)</script> admin endpoint',
        label: 'Line 8',
      }],
      onSaved: saved,
    })

    expect(document.getElementById('finding-record-form').classList.contains('u-hidden')).toBe(false)
    expect(document.getElementById('finding-triage-form').classList.contains('u-hidden')).toBe(true)
    expect([...document.getElementById('finding-record-target').options].map(option => option.value)).toEqual([
      'target-confirmed',
    ])
    expect(document.getElementById('finding-record-evidence').textContent).toContain('<script>alert(1)</script>')
    expect(document.getElementById('finding-record-evidence').querySelector('script')).toBeNull()
    expect(document.getElementById('finding-record-title').value).toBe('Finding from saved run output')
    expect(document.getElementById('finding-record-summary').value).toBe('Two saved lines were selected as evidence.')

    document.getElementById('finding-record-title').value = 'Unauthenticated admin console'
    document.getElementById('finding-record-severity').value = 'high'
    document.getElementById('finding-record-confidence').value = 'high'
    document.getElementById('finding-record-summary').value = 'The console is public.'
    document.getElementById('finding-record-impact').value = 'Anyone can administer the service.'
    document.getElementById('finding-record-reproduction').value = 'Open the endpoint without credentials.'
    document.getElementById('finding-record-cves').value = 'cve-2026-12345, CVE-2026-12345'
    document.getElementById('finding-record-cwes').value = 'cwe-306'
    document.getElementById('finding-record-cvss-vector').value = 'CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H'
    document.getElementById('finding-record-cvss-score').value = '9.8'
    document.getElementById('finding-record-references').value = 'javascript:alert(1)'
    document.getElementById('finding-record-form')
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises()
    expect(document.getElementById('finding-triage-message').textContent).toContain('safe HTTP(S) URLs')
    expect(apiFetch).not.toHaveBeenCalled()

    document.getElementById('finding-record-references').value = 'https://example.test/advisory\nhttps://example.test/advisory'
    document.getElementById('finding-record-form')
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises(10)

    expect(apiFetch).toHaveBeenCalledWith('/projects/project-1/findings', expect.objectContaining({ method: 'POST' }))
    const payload = JSON.parse(apiFetch.mock.calls[0][1].body)
    expect(payload).toEqual({
      target_id: 'target-confirmed',
      title: 'Unauthenticated admin console',
      severity: 'high',
      summary: 'The console is public.',
      impact: 'Anyone can administer the service.',
      reproduction_steps: 'Open the endpoint without credentials.',
      confidence: 'high',
      cve_ids: ['CVE-2026-12345'],
      cwe_ids: ['CWE-306'],
      cvss_vector: 'CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H',
      cvss_score: 9.8,
      references: ['https://example.test/advisory'],
      evidence: [{
        evidence_type: 'run_line',
        evidence_id: 'run-1',
        line_number: 7,
        snippet: '<script>alert(1)</script> admin endpoint',
      }],
      allow_duplicate: false,
    })
    expect(saved).toHaveBeenCalledWith(expect.objectContaining({ id: 'finding-manual' }), expect.any(Object))
    expect(document.getElementById('finding-triage-overlay').classList.contains('open')).toBe(false)
  })

  it('requires explicit duplicate override and rejects stale manual-finding edits', async () => {
    let createCalls = 0
    const onConflict = vi.fn()
    const apiFetch = vi.fn((url, options = {}) => {
      const payload = JSON.parse(options.body)
      if (options.method === 'POST') {
        createCalls += 1
        if (!payload.allow_duplicate) {
          return Promise.resolve(jsonResponse({
            conflict: 'possible_duplicate',
            duplicates: [{ id: 'existing-1', title: 'Existing admin finding' }],
          }, 409))
        }
        return Promise.resolve(jsonResponse({ finding: { id: 'finding-override', origin: 'manual' } }, 201))
      }
      return Promise.resolve(jsonResponse({
        conflict: 'stale_revision',
        current_revision: 4,
      }, 409))
    })
    window.apiFetch = apiFetch
    window.showConfirm = vi.fn(() => Promise.resolve('override'))
    loadEditor()

    const targets = [{ id: 'target-1', type: 'domain', value: 'app.example.test', review_state: 'confirmed' }]
    await window.DarklabFindingTriageEditor.openRecord({ projectId: 'project-1', targets })
    document.getElementById('finding-record-title').value = 'Possible duplicate'
    document.getElementById('finding-record-form')
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises(16)

    expect(createCalls).toBe(2)
    expect(window.showConfirm).toHaveBeenCalledWith(expect.objectContaining({ tone: 'warning' }))
    expect(JSON.parse(apiFetch.mock.calls[1][1].body).allow_duplicate).toBe(true)

    await window.DarklabFindingTriageEditor.openRecord({
      projectId: 'project-1',
      targets,
      finding: {
        id: 'finding-manual',
        origin: 'manual',
        target_id: 'target-1',
        title: 'Manual finding',
        severity: 'medium',
        confidence: 'unknown',
        manual_revision: 3,
      },
      onConflict,
    })
    expect(document.getElementById('finding-record-target').disabled).toBe(true)
    document.getElementById('finding-record-title').value = 'Updated manual finding'
    document.getElementById('finding-record-form')
      .dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }))
    await flushPromises(10)

    const patchCall = apiFetch.mock.calls.find(([, options]) => options.method === 'PATCH')
    expect(JSON.parse(patchCall[1].body)).toEqual(expect.objectContaining({
      expected_revision: 3,
      title: 'Updated manual finding',
    }))
    expect(document.getElementById('finding-triage-message').textContent).toContain('current revision 4')
    expect(onConflict).toHaveBeenCalled()
    expect(document.getElementById('finding-triage-overlay').classList.contains('open')).toBe(true)
  })

  it('returns focus to the launch control when the editor closes over another surface', async () => {
    const launch = document.createElement('button')
    launch.type = 'button'
    launch.textContent = 'Create finding'
    document.body.appendChild(launch)
    launch.focus()
    loadEditor()

    await window.DarklabFindingTriageEditor.openRecord({
      projectId: 'project-1',
      targets: [{ id: 'target-1', type: 'domain', value: 'app.example.test', review_state: 'confirmed' }],
    })
    document.getElementById('finding-record-cancel').click()
    await new Promise(resolve => setTimeout(resolve, 0))

    expect(document.activeElement).toBe(launch)
    expect(window.refocusComposerAfterAction).not.toHaveBeenCalled()
  })
})
