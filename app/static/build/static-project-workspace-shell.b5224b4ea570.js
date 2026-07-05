import {
  activeTeamScopeCan,
  teamScopeDeniedMessage
} from "./static-chunk-5i2t3zlu.acdd7b56baea.js";
import {
  showToast
} from "./static-chunk-poi5czx6.3f5c94749765.js";
import "./static-chunk-zpenfczu.1862ffb66041.js";
import "./static-chunk-4m44pm74.0a8001fa1d52.js";
import "./static-chunk-2bgb52uq.a327269283bb.js";
import {
  syncModalOverlayState
} from "./static-chunk-yo5cjr7d.b86e0c93eff0.js";
import "./static-chunk-gwztcp24.e58b5ff85d88.js";
import "./static-chunk-2kxtimik.c9801087c7a7.js";

// app/static/js/features/projects/project_workspace_shell.js
var exportedDarklabProjectWorkspaceShell = null;
(function projectWorkspaceShellModule(global) {
  "use strict";
  function createProjectWorkspaceShellController(context) {
    const ctx = context || {};
    let externalRefreshTimer = null;
    function showOverlay() {
      if (!ctx.projectWorkspaceOverlay) return;
      ctx.projectWorkspaceOverlay.classList.remove("u-hidden");
      ctx.projectWorkspaceOverlay.classList.add("open");
      ctx.projectWorkspaceOverlay.setAttribute("aria-hidden", "false");
      if (typeof syncModalOverlayState === "function") syncModalOverlayState();
    }
    function hideOverlay() {
      if (!ctx.projectWorkspaceOverlay) return;
      ctx.projectWorkspaceOverlay.classList.add("u-hidden");
      ctx.projectWorkspaceOverlay.classList.remove("open");
      ctx.projectWorkspaceOverlay.setAttribute("aria-hidden", "true");
      if (typeof syncModalOverlayState === "function") syncModalOverlayState();
    }
    function isOpen() {
      return !!(ctx.projectWorkspaceOverlay && ctx.projectWorkspaceOverlay.classList.contains("open"));
    }
    function showWorkspaceToast(text, tone = "success") {
      const toastFn = typeof ctx.showToast === "function" ? ctx.showToast : typeof showToast === "function" ? showToast : null;
      if (!toastFn) return false;
      toastFn(text, tone);
      return true;
    }
    function setMessage(text = "", { error = false, toast = true } = {}) {
      if (!ctx.projectWorkspaceMessage) return;
      let messageText = ctx.projectWorkspaceMessage.querySelector(".project-workspace-message-text");
      if (!messageText) {
        ctx.projectWorkspaceMessage.replaceChildren();
        messageText = document.createElement("span");
        messageText.className = "project-workspace-message-text";
        const dismiss = document.createElement("button");
        dismiss.type = "button";
        dismiss.className = "btn btn-ghost btn-compact project-workspace-message-dismiss";
        dismiss.dataset.projectMessageDismiss = "1";
        dismiss.setAttribute("aria-label", "Dismiss project message");
        dismiss.textContent = "✕";
        ctx.projectWorkspaceMessage.append(messageText, dismiss);
      }
      if (text && toast && showWorkspaceToast(text, error ? "error" : "success")) {
        messageText.textContent = "";
        ctx.projectWorkspaceMessage.classList.add("u-hidden");
        ctx.projectWorkspaceMessage.classList.remove("is-error");
        return;
      }
      messageText.textContent = text;
      ctx.projectWorkspaceMessage.classList.toggle("u-hidden", !text);
      ctx.projectWorkspaceMessage.classList.toggle("is-error", !!error);
    }
    function activeTeamScopeCan2(capability) {
      const can = typeof activeTeamScopeCan === "function" ? activeTeamScopeCan : null;
      return typeof can === "function" ? can(capability) : true;
    }
    function teamScopeDeniedMessage2(action) {
      const denied = typeof teamScopeDeniedMessage === "function" ? teamScopeDeniedMessage : null;
      return typeof denied === "function" ? denied(action) : `View-only team members can't ${action}. Switch to Personal or ask for operator access.`;
    }
    function projectWriteDeniedMessage() {
      return teamScopeDeniedMessage2("change team projects");
    }
    function normalizeProjectError(err) {
      if (String(err?.message || "") === "team_forbidden") {
        return new Error(projectWriteDeniedMessage());
      }
      return err;
    }
    function scheduleExternalRefresh() {
      if (!isOpen()) return;
      if (externalRefreshTimer) clearTimeout(externalRefreshTimer);
      externalRefreshTimer = setTimeout(() => {
        externalRefreshTimer = null;
        Promise.resolve(ctx.refreshProjectWorkspace?.()).catch(() => {
        });
      }, 250);
    }
    function notifyChanged(reason = "updated", projectId = "", { local = true } = {}) {
      const payload = {
        reason: String(reason || "updated"),
        project_id: String(projectId || ""),
        ts: Date.now(),
        nonce: Math.random().toString(36).slice(2)
      };
      if (typeof ctx.emitUiEvent === "function") ctx.emitUiEvent("app:project-workspace-mutated", payload);
      if (local) scheduleExternalRefresh();
      try {
        if (typeof localStorage !== "undefined") {
          localStorage.setItem(ctx.projectWorkspaceBroadcastKey, JSON.stringify(payload));
        }
      } catch (_) {
      }
    }
    async function open() {
      if (!ctx.projectWorkspaceOverlay || !ctx.projectWorkspaceBody) return;
      ctx.closeMajorOverlays?.({ skipProjectWorkspace: true });
      ctx.blurVisibleComposerInputIfMobile?.();
      ctx.setProjectWorkspaceTab?.("details");
      showOverlay();
      ctx.markInteractionSurfaceReady?.("projects", ctx.projectWorkspaceOverlay, ctx.projectWorkspaceModal);
      await ctx.refreshProjectWorkspace?.();
      const mobileMode = document.body && document.body.classList.contains("mobile-terminal-mode");
      if (!mobileMode && ctx.projectWorkspaceNameInput) {
        window.setTimeout(() => ctx.projectWorkspaceNameInput.focus(), 0);
      }
    }
    function close({ refocus = true } = {}) {
      Promise.resolve(ctx.flushProjectNotesAutosave?.()).catch(() => {
      });
      ctx.closeProjectTargetEditor?.();
      ctx.closeProjectEntityEditor?.();
      ctx.projectEntitiesController?.().closePicker();
      ctx.closeProjectPackageManifest?.();
      ctx.closeProjectPackageWizard?.({ render: false });
      ctx.closeProjectMobileActionSheet?.({ restoreFocus: false });
      ctx.closeProjectMobileCompareSheet?.({ restoreFocus: false });
      hideOverlay();
      setMessage("");
      if (refocus) ctx.refocusComposerAfterAction?.({ defer: true });
    }
    async function request(url, options = {}) {
      const method = String(options.method || "GET").toUpperCase();
      if (method !== "GET" && method !== "HEAD" && !activeTeamScopeCan2("mutate_projects")) {
        throw new Error(projectWriteDeniedMessage());
      }
      try {
        return await ctx.EntityMetadataClient.entityMetadataRequest(url, options, {
          onWrite: () => notifyChanged("write", ctx.selectedProjectId?.(), { local: false })
        });
      } catch (err) {
        throw normalizeProjectError(err);
      }
    }
    async function responseError(resp, fallback) {
      let message = fallback;
      try {
        const data = await resp.json();
        if (data && data.error) message = data.error;
      } catch (_) {
      }
      if (message === "team_forbidden") message = projectWriteDeniedMessage();
      return new Error(message || fallback);
    }
    async function createProjectFromName(name, input) {
      const normalizedName = String(name || "").trim();
      if (!normalizedName) {
        setMessage("Project name is required.", { error: true });
        return;
      }
      const resp = await request("/projects", {
        method: "POST",
        body: JSON.stringify({ name: normalizedName })
      });
      const data = await resp.json();
      const projectId = data && data.project ? data.project.id : "";
      if (projectId) {
        await request("/projects/active", {
          method: "POST",
          body: JSON.stringify({ project_id: projectId })
        });
      }
      if (projectId) ctx.setSelectedProjectId?.(projectId);
      if (projectId) ctx.setProjectPaginationOffset?.(0);
      ctx.setProjectWorkspaceTab?.("details");
      if (input) input.value = "";
      ctx.setProjectMobileCreateOpen?.(false);
      setMessage("Project created and selected.");
      await ctx.refreshProjectWorkspace?.();
    }
    function bindCreateForms() {
      const bindCreateForm = (form, input) => {
        form?.addEventListener("submit", async (event) => {
          event.preventDefault();
          const name = String(input?.value || "").trim();
          if (!name) {
            setMessage("Project name is required.", { error: true });
            return;
          }
          try {
            await createProjectFromName(name, input);
          } catch (err) {
            setMessage(err.message || "Could not create project.", { error: true });
          }
        });
      };
      bindCreateForm(ctx.projectWorkspaceCreateForm, ctx.projectWorkspaceNameInput);
      bindCreateForm(ctx.projectMobileCreateForm, ctx.projectMobileNameInput);
    }
    return {
      bindCreateForms,
      close,
      createProjectFromName,
      hideOverlay,
      isOpen,
      notifyChanged,
      open,
      request,
      responseError,
      scheduleExternalRefresh,
      setMessage,
      showOverlay
    };
  }
  const DarklabProjectWorkspaceShell = { createProjectWorkspaceShellController };
  exportedDarklabProjectWorkspaceShell = DarklabProjectWorkspaceShell;
})(globalThis);
export {
  exportedDarklabProjectWorkspaceShell as DarklabProjectWorkspaceShell
};
