// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Active Project HUD/context controller.
// Loaded before shell_chrome.js; shell chrome supplies HUD elements and refresh hooks.

let exportedDarklabProjectActiveContext = null;

(function projectActiveContextModule(global) {
  'use strict';

  function createProjectActiveContextController(context) {
    const ctx = context || {};
    let activeProject = null;
    let activeProjectLoadPromise = null;

    function project() {
      return activeProject;
    }

    function setProject(nextProject) {
      activeProject = nextProject && typeof nextProject === 'object' ? nextProject : null;
      render();
      ctx.syncProjectNotesForm?.();
      ctx.emitUiEvent?.('app:active-project-changed', { project: activeProject });
      return activeProject;
    }

    function render() {
      const name = ctx.projectDisplayName(activeProject);
      const visible = !!name;
      if (ctx.hudProjectCell) {
        ctx.hudProjectCell.classList.remove('u-hidden');
        ctx.hudProjectCell.classList.toggle('hud-project-empty', !visible);
      }
      if (ctx.hudProjectEl) {
        ctx.hudProjectEl.textContent = visible ? name : 'No project';
        ctx.hudProjectEl.title = visible ? `Active project: ${name}` : 'No active project';
        ctx.setValueColor(ctx.hudProjectEl, visible ? null : 'hud-muted');
      }
    }

    async function load(options = {}) {
      if (typeof ctx.apiFetch !== 'function') return null;
      if (activeProjectLoadPromise && options.force !== true) return activeProjectLoadPromise;
      const request = (async () => {
        try {
          const resp = await ctx.apiFetch('/projects/active', { cache: 'no-store' });
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          const data = await resp.json();
          activeProject = data && data.project && typeof data.project === 'object' ? data.project : null;
        } catch (err) {
          activeProject = null;
          ctx.logClientError?.('failed to load /projects/active', err);
        }
        render();
        ctx.syncProjectNotesForm?.();
        ctx.emitUiEvent?.('app:active-project-changed', { project: activeProject });
        return activeProject;
      })();
      activeProjectLoadPromise = request;
      try {
        return await request;
      } finally {
        if (activeProjectLoadPromise === request) activeProjectLoadPromise = null;
      }
    }

    function targetDiscoveryMessage(count) {
      const total = Number(count || 0);
      if (total === 1) return '1 project target discovered.';
      return `${total.toLocaleString()} project targets discovered.`;
    }

    function pulseNavTargets() {
      const controls = [];
      ctx.railNav?.querySelectorAll('[data-action="projects"]').forEach(control => controls.push(control));
      const mobileProjectsButton = document.querySelector('#mobile-menu-sheet [data-menu-action="projects"]');
      if (mobileProjectsButton) controls.push(mobileProjectsButton);
      controls.forEach((control) => {
        control.classList.add('has-project-target-discovery');
        window.setTimeout(() => {
          control.classList.remove('has-project-target-discovery');
        }, 5000);
      });
    }

    function bindTargetDiscoveryEvent() {
      if (typeof document === 'undefined' || typeof document.addEventListener !== 'function') return;
      document.addEventListener('app:project-target-discovered', (event) => {
        const detail = event && event.detail && typeof event.detail === 'object' ? event.detail : {};
        const count = Number(detail.count || detail.target_count || 0);
        if (!Number.isFinite(count) || count <= 0) return;
        pulseNavTargets();
        ctx.showToast?.(targetDiscoveryMessage(count));
        if (ctx.isProjectWorkspaceOpen?.()) {
          ctx.refreshProjectWorkspace?.().catch(() => {});
        }
      });
    }

    return {
      bindTargetDiscoveryEvent,
      load,
      project,
      pulseNavTargets,
      render,
      setProject,
      targetDiscoveryMessage,
    };
  }

  const DarklabProjectActiveContext = {
    createProjectActiveContextController,
  };
  exportedDarklabProjectActiveContext = DarklabProjectActiveContext;
})(globalThis);

export {
  exportedDarklabProjectActiveContext as DarklabProjectActiveContext,};
