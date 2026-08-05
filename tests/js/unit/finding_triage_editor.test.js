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
})
