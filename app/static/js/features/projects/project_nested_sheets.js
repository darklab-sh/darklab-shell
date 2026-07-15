// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Project nested sheet controller.
// Loaded before shell_chrome.js; shell chrome supplies the nested modal elements.
import { useMobileTerminalViewportMode as importedUseMobileTerminalViewportMode } from '../mobile/mobile_shell_layout.js';

let exportedDarklabProjectNestedSheets = null;

(function projectNestedSheetsModule(global) {
  'use strict';

  function createProjectNestedSheetsController(context) {
    const ctx = context || {};
    let keyboardGuardBound = false;

    function mobileModeActive() {
      return !!(
        document.body.classList.contains('mobile-terminal-mode')
        || (typeof importedUseMobileTerminalViewportMode === 'function' && importedUseMobileTerminalViewportMode())
      );
    }

    function nestedSheetOpen() {
      return !!(
        ctx.isProjectTargetEditorOpen?.()
        || ctx.isProjectEntityEditorOpen?.()
        || ctx.isProjectPackageManifestOpen?.()
        || ctx.isProjectPackageWizardOpen?.()
      );
    }

    function syncWorkspaceSuppression() {
      if (!ctx.projectWorkspaceModal) return;
      const suppressed = nestedSheetOpen();
      ctx.projectWorkspaceModal.classList.toggle('is-backgrounded-by-project-sheet', suppressed);
      if ('inert' in ctx.projectWorkspaceModal) {
        ctx.projectWorkspaceModal.inert = suppressed;
      }
      ctx.projectWorkspaceModal.setAttribute('aria-hidden', suppressed ? 'true' : 'false');
    }

    function sheetFocusTarget(overlay, preferred = null) {
      if (!overlay) return preferred;
      if (mobileModeActive()) {
        return overlay.querySelector('.sheet-grab.gesture-handle') || preferred;
      }
      return preferred || overlay.querySelector('button, input, select, textarea, [tabindex]:not([tabindex="-1"])');
    }

    function openKeyboardSheet() {
      if (ctx.isProjectTargetEditorOpen?.()) return ctx.projectTargetEditorOverlay?.querySelector('#project-target-editor-modal');
      if (ctx.isProjectEntityEditorOpen?.()) return ctx.projectEntityEditorOverlay?.querySelector('#project-entity-editor-modal');
      if (ctx.isProjectPackageWizardOpen?.()) return ctx.projectPackageWizardOverlay?.querySelector('#project-package-wizard-modal');
      return null;
    }

    function syncMobileFocusedField() {
      if (!mobileModeActive()) return;
      const sheet = openKeyboardSheet();
      if (!sheet) return;
      const active = document.activeElement;
      if (!active || !sheet.contains(active)) return;
      if (!active.matches?.('input, textarea, select, [contenteditable="true"]')) return;
      [0, 90, 220].forEach((delay) => {
        window.setTimeout(() => {
          if (!active.isConnected || !openKeyboardSheet()?.contains(active)) return;
          active.scrollIntoView?.({ block: 'center', inline: 'nearest' });
        }, delay);
      });
    }

    function focusNestedSheet(overlay, preferred = null) {
      const target = sheetFocusTarget(overlay, preferred);
      window.setTimeout(() => {
        const active = document.activeElement;
        const activeIsEditable = active instanceof HTMLInputElement
          || active instanceof HTMLTextAreaElement
          || active instanceof HTMLSelectElement
          || active?.isContentEditable;
        if (activeIsEditable && overlay?.contains(active)) {
          syncWorkspaceSuppression();
          syncMobileFocusedField();
          return;
        }
        if (target && target.isConnected && typeof target.focus === 'function') {
          try { target.focus({ preventScroll: true }); } catch (_) { target.focus(); }
        }
        syncWorkspaceSuppression();
        syncMobileFocusedField();
      }, 0);
    }

    function installKeyboardGuards() {
      if (keyboardGuardBound) return;
      keyboardGuardBound = true;
      [
        ctx.projectTargetEditorOverlay,
        ctx.projectEntityEditorOverlay,
        ctx.projectPackageWizardOverlay,
      ].forEach((overlay) => {
        overlay?.addEventListener('focusin', () => syncMobileFocusedField());
      });
      if (window.visualViewport && typeof window.visualViewport.addEventListener === 'function') {
        window.visualViewport.addEventListener('resize', () => syncMobileFocusedField());
      }
    }

    return {
      focusNestedSheet,
      installKeyboardGuards,
      mobileModeActive,
      nestedSheetOpen,
      syncMobileFocusedField,
      syncWorkspaceSuppression,
    };
  }

  const DarklabProjectNestedSheets = {
    createProjectNestedSheetsController,
  };
  exportedDarklabProjectNestedSheets = DarklabProjectNestedSheets;
})(globalThis);

export {
  exportedDarklabProjectNestedSheets as DarklabProjectNestedSheets,};
