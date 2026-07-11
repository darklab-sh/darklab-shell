// Project workspace binding/bootstrap controller.
// Loaded before shell_chrome.js; shell chrome supplies elements and controller factories.

let exportedDarklabProjectWorkspaceBootstrap = null;

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
        const controller = ctx.projectPackagesController?.();
        controller?.handleInput(event);
      });
      ctx.projectPackageWizardOverlay?.addEventListener('change', (event) => {
        const controller = ctx.projectPackagesController?.();
        controller?.handleChange(event);
      });
      ctx.projectPackageWizardOverlay?.addEventListener('click', async (event) => {
        const controller = ctx.projectPackagesController?.();
        if (controller) await controller.handleWizardOverlayClick(event);
      });
    }

    function bindDismissibleOverlays() {
      const bindDismissibleFn = optionalFn(ctx.bindDismissible);
      if (!bindDismissibleFn) return;

      if (ctx.projectWorkspaceOverlay) {
        bindDismissibleFn(ctx.projectWorkspaceOverlay, {
          level: 'modal',
          isOpen: ctx.isProjectWorkspaceOpen,
          onClose: () => ctx.closeProjectWorkspace?.(),
          closeButtons: null,
        });
      }
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

      if (ctx.projectWorkspaceModal) {
        bindMobileSheetFn(ctx.projectWorkspaceModal, {
          onClose: () => ctx.closeProjectWorkspace?.(),
        });
      }
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

    function bindFocusTraps() {
      const bindFocusTrapFn = optionalFn(ctx.bindFocusTrap);
      if (!bindFocusTrapFn) return;
      [
        ctx.projectWorkspaceModal,
        ctx.projectTargetEditorOverlay?.querySelector('#project-target-editor-modal'),
        ctx.projectEntityEditorOverlay?.querySelector('#project-entity-editor-modal'),
        ctx.projectPackageManifestOverlay?.querySelector('#project-package-manifest-modal'),
        ctx.projectPackageWizardOverlay?.querySelector('#project-package-wizard-modal'),
      ].forEach((card) => {
        if (card) bindFocusTrapFn(card);
      });
    }

    function bindAll() {
      ctx.projectWorkspaceShellController?.()?.bindCreateForms();
      ctx.projectTargetsController?.()?.bindEditorEvents();
      ctx.projectDetailsController?.()?.bindFormEvents();
      ctx.projectEntityEditorController?.()?.bindFormEvents();
      ctx.projectWorkspaceEventsController?.()?.bindEvents();
      const projectMobileRoot = ctx.projectWorkspaceModal?.querySelector('#project-mobile-root');
      projectMobileRoot?.addEventListener('click', (event) => {
        void ctx.projectWorkspaceEventsController?.()?.handleClick(event);
      }, true);

      ctx.projectMobileTabs?.addEventListener('scroll', () => {
        ctx.syncProjectMobileTabEdges?.();
      }, { passive: true });

      bindCloseButtons();
      bindPackageWizard();
      bindDismissibleOverlays();
      bindMobileSheets();
      bindFocusTraps();
    }

    return {
      bindAll,
    };
  }

  const DarklabProjectWorkspaceBootstrap = {
    createProjectWorkspaceBootstrapController,
  };
  exportedDarklabProjectWorkspaceBootstrap = DarklabProjectWorkspaceBootstrap;
})(globalThis);

export {
  exportedDarklabProjectWorkspaceBootstrap as DarklabProjectWorkspaceBootstrap,};
