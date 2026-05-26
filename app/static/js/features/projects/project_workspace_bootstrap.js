// Project workspace binding/bootstrap controller.
// Loaded before shell_chrome.js; shell chrome supplies elements and controller factories.

(function projectWorkspaceBootstrapModule(global) {
  'use strict';

  function optionalFn(value) {
    return typeof value === 'function' ? value : null;
  }

  function createProjectWorkspaceBootstrapController(context) {
    const ctx = context || {};

    function bindCloseButtons() {
      ctx.projectWorkspaceOverlay?.querySelector('.project-workspace-close')?.addEventListener('click', () => {
        ctx.closeProjectWorkspace?.();
      });

      ctx.projectTargetEditorOverlay?.querySelector('.project-target-editor-close')?.addEventListener('click', () => {
        ctx.closeProjectTargetEditor?.();
      });
      ctx.projectTargetEditorOverlay?.querySelector('.project-target-editor-cancel')?.addEventListener('click', () => {
        ctx.closeProjectTargetEditor?.();
      });

      ctx.projectEntityEditorOverlay?.querySelector('.project-entity-editor-close')?.addEventListener('click', () => {
        ctx.closeProjectEntityEditor?.();
      });
      ctx.projectEntityEditorOverlay?.querySelector('.project-entity-editor-cancel')?.addEventListener('click', () => {
        ctx.closeProjectEntityEditor?.();
      });
    }

    function bindPackageWizard() {
      ctx.projectPackageWizardOverlay?.addEventListener('input', (event) => {
        ctx.projectPackagesController?.()?.handleInput(event);
      });
      ctx.projectPackageWizardOverlay?.addEventListener('change', (event) => {
        ctx.projectPackagesController?.()?.handleChange(event);
      });
      ctx.projectPackageWizardOverlay?.addEventListener('click', async (event) => {
        await ctx.projectPackagesController?.()?.handleWizardOverlayClick(event);
      });
    }

    function bindDismissibleOverlays() {
      const bindDismissibleFn = optionalFn(ctx.bindDismissible);
      if (!bindDismissibleFn) return;

      if (ctx.projectTargetEditorOverlay) {
        bindDismissibleFn(ctx.projectTargetEditorOverlay, {
          level: 'modal',
          isOpen: ctx.isProjectTargetEditorOpen,
          onClose: () => ctx.closeProjectTargetEditor?.(),
          closeButtons: null,
        });
      }
      if (ctx.projectEntityEditorOverlay) {
        bindDismissibleFn(ctx.projectEntityEditorOverlay, {
          level: 'modal',
          isOpen: ctx.isProjectEntityEditorOpen,
          onClose: () => ctx.closeProjectEntityEditor?.(),
          closeButtons: null,
        });
      }
      if (ctx.projectPackageWizardOverlay) {
        bindDismissibleFn(ctx.projectPackageWizardOverlay, {
          level: 'modal',
          isOpen: ctx.isProjectPackageWizardOpen,
          onClose: () => ctx.closeProjectPackageWizard?.(),
          closeButtons: null,
        });
      }
      if (ctx.projectPackageManifestOverlay) {
        bindDismissibleFn(ctx.projectPackageManifestOverlay, {
          level: 'modal',
          isOpen: ctx.isProjectPackageManifestOpen,
          onClose: () => ctx.closeProjectPackageManifest?.(),
          closeButtons: [ctx.projectPackageManifestOverlay.querySelector('.project-package-manifest-close')],
        });
      }
    }

    function bindMobileSheets() {
      const bindMobileSheetFn = optionalFn(ctx.bindMobileSheet);
      if (!bindMobileSheetFn) return;

      if (ctx.projectTargetEditorOverlay) {
        bindMobileSheetFn(ctx.projectTargetEditorOverlay.querySelector('#project-target-editor-modal'), {
          onClose: () => ctx.closeProjectTargetEditor?.(),
        });
      }
      if (ctx.projectEntityEditorOverlay) {
        bindMobileSheetFn(ctx.projectEntityEditorOverlay.querySelector('#project-entity-editor-modal'), {
          onClose: () => ctx.closeProjectEntityEditor?.(),
        });
      }
      if (ctx.projectPackageManifestOverlay) {
        bindMobileSheetFn(ctx.projectPackageManifestOverlay.querySelector('#project-package-manifest-modal'), {
          onClose: () => ctx.closeProjectPackageManifest?.(),
        });
      }
      if (ctx.projectPackageWizardOverlay) {
        bindMobileSheetFn(ctx.projectPackageWizardOverlay.querySelector('#project-package-wizard-modal'), {
          onClose: () => ctx.closeProjectPackageWizard?.(),
        });
      }
    }

    function bindAll() {
      ctx.projectWorkspaceShellController?.()?.bindCreateForms();
      ctx.projectTargetsController?.()?.bindEditorEvents();
      ctx.projectDetailsController?.()?.bindFormEvents();
      ctx.projectEntityEditorController?.()?.bindFormEvents();
      ctx.projectWorkspaceEventsController?.()?.bindEvents();

      ctx.projectMobileTabs?.addEventListener('scroll', () => {
        ctx.syncProjectMobileTabEdges?.();
      }, { passive: true });

      bindCloseButtons();
      bindPackageWizard();
      bindDismissibleOverlays();
      bindMobileSheets();
    }

    return {
      bindAll,
    };
  }

  global.DarklabProjectWorkspaceBootstrap = {
    createProjectWorkspaceBootstrapController,
  };
})(globalThis);
