// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Lightweight finding triage API. The full editor is loaded only when opened.
import { loadFindingTriageEditor as importedLoadFindingTriageEditor } from '../../core/lazy_assets.js';

const VERIFICATION_STATES = Object.freeze([
  { value: 'not_started', label: 'Not started' },
  { value: 'ready_to_verify', label: 'Ready to verify' },
  { value: 'verified', label: 'Verified' },
  { value: 'needs_retest', label: 'Needs retest' },
  { value: 'not_applicable', label: 'Not applicable' },
]);

let loadedEditor = null;
let loadingEditor = null;

function text(value, fallback = '') {
  const normalized = String(value || '').trim();
  return normalized || fallback;
}

function compactTriage(triage) {
  const item = triage && typeof triage === 'object' ? triage : {};
  return {
    verification_status: String(item.verification_status || 'not_started'),
    has_remediation: !!String(item.remediation || '').trim() || !!item.has_remediation,
    has_verification_steps: !!String(item.verification_steps || '').trim() || !!item.has_verification_steps,
    has_verification_notes: !!String(item.verification_notes || '').trim() || !!item.has_verification_notes,
    remediation_preview: text(item.remediation_preview || item.remediation),
    verification_steps_preview: text(item.verification_steps_preview || item.verification_steps),
  };
}

function verificationStatusLabel(value) {
  const normalized = String(value || 'not_started');
  const found = VERIFICATION_STATES.find(item => item.value === normalized);
  return found ? found.label : normalized;
}

function verificationStatusTone(value) {
  const normalized = String(value || 'not_started');
  if (normalized === 'verified') return 'green';
  if (normalized === 'needs_retest') return 'amber';
  return 'muted';
}

function editorFromModule(moduleApi) {
  if (moduleApi && moduleApi.DarklabFindingTriageEditor) return moduleApi.DarklabFindingTriageEditor;
  return moduleApi || null;
}

async function loadEditor() {
  if (loadedEditor) return loadedEditor;
  if (!loadingEditor) {
    loadingEditor = Promise.resolve()
      .then(() => importedLoadFindingTriageEditor())
      .then((moduleApi) => {
        loadedEditor = editorFromModule(moduleApi);
        return loadedEditor;
      })
      .finally(() => {
        loadingEditor = null;
      });
  }
  return loadingEditor;
}

function isFindingTriageEditorOpen() {
  if (loadedEditor && typeof loadedEditor.isOpen === 'function') return loadedEditor.isOpen();
  const overlay = document.getElementById('finding-triage-overlay');
  return !!overlay?.classList.contains('open');
}

function closeFindingTriageEditor() {
  if (loadedEditor && typeof loadedEditor.close === 'function') return loadedEditor.close();
  const overlay = document.getElementById('finding-triage-overlay');
  if (!overlay) return false;
  overlay.classList.add('u-hidden');
  overlay.classList.remove('open');
  overlay.setAttribute('aria-hidden', 'true');
  return true;
}

async function openFindingTriageEditor(finding, options = {}) {
  const editor = await loadEditor();
  if (!editor || typeof editor.open !== 'function') {
    throw new Error('Finding triage editor is not available.');
  }
  return editor.open(finding, options);
}

const DarklabFindingTriageEditor = {
  compactTriage,
  close: closeFindingTriageEditor,
  isOpen: isFindingTriageEditorOpen,
  open: openFindingTriageEditor,
  verificationStatusLabel,
  verificationStatusTone,
  verificationStates: VERIFICATION_STATES.slice(),
};

export {
  DarklabFindingTriageEditor,
  closeFindingTriageEditor,
  compactTriage,
  isFindingTriageEditorOpen,
  openFindingTriageEditor,
  verificationStatusLabel,
  verificationStatusTone,
  VERIFICATION_STATES as verificationStates,
};
