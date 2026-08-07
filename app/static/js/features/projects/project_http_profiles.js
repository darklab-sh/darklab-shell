// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Assessment-owned HTTP profile list, permissions, and mutations.

import { openActionSheet } from '../../ui/ui_action_sheet.js';
import { openHttpProfileEditor } from './project_http_profile_editor.js';

function createProjectHttpProfileManager(context, hooks = {}) {
  const ctx = context || {};
  const states = new Map();

  function stateFor(projectId) {
    const id = String(projectId || '');
    if (!states.has(id)) {
      states.set(id, {
        profiles: [],
        loaded: false,
        loading: false,
        loadPromise: null,
        error: '',
        mutating: '',
      });
    }
    return states.get(id);
  }

  function renderViews() {
    hooks.renderViews?.();
  }

  function logFailure(message, err, details = {}) {
    ctx.logClientError?.(message, err, { page: 'project_assessment', ...details });
  }

  function restoreFocus(target) {
    if (!target?.isConnected || target.disabled || typeof target.focus !== 'function') return;
    try {
      target.focus({ preventScroll: true });
    } catch (_) {
      target.focus();
    }
  }

  async function responseError(resp, fallback) {
    if (typeof ctx.projectResponseError === 'function') return ctx.projectResponseError(resp, fallback);
    return new Error(fallback);
  }

  async function load(projectId, options = {}) {
    const id = String(projectId || '');
    if (!id) return false;
    const st = stateFor(id);
    if (st.loaded && options.force !== true) return true;
    if (st.loading && st.loadPromise) return st.loadPromise;
    st.loading = true;
    st.error = '';
    const promise = (async () => {
      try {
        const resp = await ctx.projectWorkspaceRequest(
          `/projects/${encodeURIComponent(id)}/http-profiles`,
          { cache: 'no-store' },
        );
        if (!resp.ok) throw await responseError(resp, 'Could not load HTTP profiles.');
        const payload = await resp.json();
        st.profiles = Array.isArray(payload?.profiles) ? payload.profiles : [];
        st.loaded = true;
        return true;
      } catch (err) {
        st.error = err?.message || 'Could not load HTTP profiles.';
        logFailure('PROJECT_ASSESSMENT_CLIENT_HTTP_PROFILES_LOAD_FAILED', err, {
          phase: 'http_profiles',
          project_id: id,
        });
        return false;
      } finally {
        st.loading = false;
        st.loadPromise = null;
        if (options.render !== false) renderViews();
      }
    })();
    st.loadPromise = promise;
    return promise;
  }

  function invalidate(projectId = '') {
    const id = String(projectId || '');
    const targets = id ? [states.get(id)] : Array.from(states.values());
    targets.filter(Boolean).forEach((st) => {
      st.profiles = [];
      st.loaded = false;
      st.error = '';
    });
  }

  function missingReferences(profile) {
    const missing = [];
    (Array.isArray(profile?.headers) ? profile.headers : []).forEach((header) => {
      if (header && header.available === false) missing.push(String(header.secret_name || 'header Secret'));
    });
    Object.values(profile?.secret_refs || {}).forEach((reference) => {
      if (reference && typeof reference === 'object' && reference.available === false) {
        missing.push(String(reference.name || 'Secret'));
      }
    });
    return [...new Set(missing.filter(Boolean))];
  }

  function profileAvailability(profile) {
    if (profile?.enabled === false) return { state: 'disabled', label: 'Disabled', tone: 'muted' };
    if (profile?.protected_references_visible === false) {
      return { state: 'restricted', label: 'Reference access required', tone: 'muted' };
    }
    const missing = missingReferences(profile);
    if (missing.length) return { state: 'missing', label: 'Missing Secret', tone: 'amber', missing };
    if (Array.isArray(profile?.credential_use) && profile.credential_use.length) {
      return { state: 'ready', label: 'Credentials ready', tone: 'green' };
    }
    return { state: 'ready', label: 'No credentials', tone: 'muted' };
  }

  async function openEditor(projectId, profile = null, returnFocus = null) {
    const id = String(projectId || '');
    if (!id) return false;
    if (ctx.canManageSecrets?.() === false) {
      ctx.setProjectWorkspaceMessage?.(
        "You don't have permission to manage HTTP profile references in this team.",
        { error: true },
      );
      return false;
    }
    try {
      return await openHttpProfileEditor(ctx, {
        projectId: id,
        profile,
        returnFocus,
        onSaved: async () => {
          await load(id, { force: true, render: false });
          ctx.setProjectWorkspaceMessage?.(profile ? 'HTTP profile updated.' : 'HTTP profile created.');
          renderViews();
        },
      });
    } catch (err) {
      ctx.setProjectWorkspaceMessage?.(err?.message || 'Could not open the HTTP profile editor.', { error: true });
      logFailure('PROJECT_ASSESSMENT_CLIENT_HTTP_PROFILE_EDITOR_FAILED', err, {
        phase: 'http_profile_editor',
        project_id: id,
        profile_id: String(profile?.id || ''),
      });
      return false;
    }
  }

  async function deleteProfile(projectId, profile, returnFocus = null) {
    const id = String(projectId || '');
    const profileId = String(profile?.id || '');
    if (!id || !profileId || typeof ctx.showConfirm !== 'function') return false;
    if (ctx.canManageSecrets?.() === false) return false;
    const choice = await ctx.showConfirm({
      body: {
        text: `Delete ${profile?.name || 'HTTP profile'}?`,
        note: 'The saved references and scope settings are removed. Secrets and Files stay intact.',
      },
      tone: 'danger',
      actions: [
        { id: 'cancel', label: 'Cancel', role: 'cancel' },
        { id: 'delete', label: 'Delete profile', role: 'destructive' },
      ],
      refocusOnResolve: false,
    });
    if (choice !== 'delete') {
      restoreFocus(returnFocus);
      return false;
    }
    const st = stateFor(id);
    st.mutating = profileId;
    renderViews();
    try {
      const resp = await ctx.projectWorkspaceRequest(
        `/projects/${encodeURIComponent(id)}/http-profiles/${encodeURIComponent(profileId)}`,
        { method: 'DELETE' },
      );
      if (!resp.ok) throw await responseError(resp, 'Could not delete this HTTP profile.');
      await load(id, { force: true, render: false });
      ctx.setProjectWorkspaceMessage?.('HTTP profile deleted.');
      return true;
    } catch (err) {
      ctx.setProjectWorkspaceMessage?.(err?.message || 'Could not delete this HTTP profile.', { error: true });
      logFailure('PROJECT_ASSESSMENT_CLIENT_HTTP_PROFILE_DELETE_FAILED', err, {
        phase: 'http_profile_delete',
        project_id: id,
        profile_id: profileId,
      });
      return false;
    } finally {
      st.mutating = '';
      renderViews();
    }
  }

  function makeElement(tag, className = '', text = '') {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== '') element.textContent = String(text);
    return element;
  }

  function badge(label, tone = 'muted') {
    return makeElement('span', `badge badge-tone-${tone}`, label);
  }

  function profileReferenceCopy(profile, availability) {
    if (availability.state === 'restricted') {
      const counts = profile?.reference_counts || {};
      const total = Number(counts.secret_refs || 0) + Number(counts.file_refs || 0);
      return total ? `${total} protected reference${total === 1 ? '' : 's'}` : 'No protected references';
    }
    if (availability.missing?.length) return `Missing: ${availability.missing.join(', ')}`;
    const uses = Array.isArray(profile?.credential_use) ? profile.credential_use : [];
    return uses.length ? uses.map(value => String(value).replaceAll('_', ' ')).join(', ') : 'Unauthenticated';
  }

  function actionItems(projectId, profile, returnFocus) {
    const disabled = ctx.canManageSecrets?.() === false || stateFor(projectId).mutating === profile.id;
    return [
      {
        label: 'Edit profile',
        disabled,
        action: focusTarget => openEditor(projectId, profile, focusTarget || returnFocus),
      },
      {
        label: 'Delete profile',
        disabled,
        tone: 'danger',
        action: focusTarget => deleteProfile(projectId, profile, focusTarget || returnFocus),
      },
    ];
  }

  function renderProfile(projectId, profile, { mobile = false } = {}) {
    const row = makeElement('article', 'panel-row project-http-profile-row');
    const main = makeElement('div', 'project-http-profile-main');
    const heading = makeElement('div', 'project-http-profile-heading');
    const availability = profileAvailability(profile);
    heading.append(
      makeElement('strong', '', profile?.name || 'HTTP profile'),
      badge(profile?.role || 'anonymous'),
      badge(availability.label, availability.tone),
    );
    const meta = [
      profile?.base_url,
      `${Number(profile?.rate_limit_per_second || 0)}/s`,
      `${Number(profile?.concurrency || 0)} concurrent`,
    ].filter(Boolean).join(' · ');
    main.append(
      heading,
      makeElement('div', 'project-http-profile-meta', meta),
      makeElement('div', 'project-http-profile-references', profileReferenceCopy(profile, availability)),
    );
    if (profile?.proxy_configured || profile?.login_workflow_id || Number(profile?.capture_rule_count || 0)) {
      main.appendChild(makeElement(
        'div',
        'project-http-profile-meta',
        'Additional login, proxy, or capture context is saved and preserved.',
      ));
    }
    const actions = makeElement('div', 'project-http-profile-actions');
    if (mobile) {
      const button = makeElement('button', 'btn btn-secondary btn-compact', 'Profile actions');
      button.type = 'button';
      ctx.bindProjectRuntimePressable?.(button, {
        onActivate: () => openActionSheet({
          title: `${profile?.name || 'HTTP profile'} actions`,
          items: actionItems(projectId, profile, button),
          container: ctx.actionSheetContainer?.() || document.body,
          returnFocus: button,
        }),
      });
      actions.appendChild(button);
    } else {
      actionItems(projectId, profile, null).forEach((item) => {
        const button = makeElement(
          'button',
          item.tone === 'danger' ? 'btn btn-destructive btn-compact' : 'btn btn-secondary btn-compact',
          item.label,
        );
        button.type = 'button';
        button.disabled = item.disabled;
        ctx.bindProjectRuntimePressable?.(button, { onActivate: () => item.action(button) });
        actions.appendChild(button);
      });
    }
    row.append(main, actions);
    return row;
  }

  function renderSection(projectId, { mobile = false } = {}) {
    const st = stateFor(projectId);
    const section = makeElement('section', 'project-assessment-section project-http-profiles');
    const heading = makeElement('div', 'project-assessment-section-heading');
    const copy = makeElement('div');
    copy.append(
      makeElement('h3', '', 'HTTP profiles'),
      makeElement('p', '', 'Reuse a Project-scoped web role without placing credentials in commands, previews, or saved output.'),
    );
    const headerActions = makeElement('div', 'project-http-profile-header-actions');
    const manageSecrets = makeElement('button', 'btn btn-secondary btn-compact', 'Manage Secrets');
    manageSecrets.type = 'button';
    const canManage = ctx.canManageSecrets?.() !== false;
    manageSecrets.disabled = !canManage;
    if (!canManage) manageSecrets.title = 'Secret management permission is required.';
    ctx.bindProjectRuntimePressable?.(manageSecrets, { onActivate: () => ctx.openSecretsOptions?.() });
    const add = makeElement('button', 'btn btn-primary btn-compact', 'New HTTP profile');
    add.type = 'button';
    add.disabled = !canManage || !!st.mutating;
    if (!canManage) add.title = 'Secret management permission is required.';
    ctx.bindProjectRuntimePressable?.(add, { onActivate: () => void openEditor(projectId, null, add) });
    headerActions.append(manageSecrets, add);
    heading.append(copy, headerActions);
    section.appendChild(heading);

    if (st.loading && !st.loaded) {
      section.appendChild(ctx.emptyProjectPanel('Loading HTTP profiles...'));
      return section;
    }
    if (st.error && !st.loaded) {
      const error = ctx.emptyProjectPanel(st.error);
      const retry = makeElement('button', 'btn btn-secondary btn-compact', 'Retry');
      retry.type = 'button';
      ctx.bindProjectRuntimePressable?.(retry, { onActivate: () => void load(projectId, { force: true }) });
      error.appendChild(retry);
      section.appendChild(error);
      return section;
    }
    if (!st.profiles.length) {
      section.appendChild(ctx.emptyProjectPanel(
        canManage
          ? 'No HTTP profiles are saved for this Project yet.'
          : 'No HTTP profiles are available in this Project.',
      ));
      return section;
    }
    const list = makeElement('div', 'project-http-profile-list');
    st.profiles.forEach(profile => list.appendChild(renderProfile(projectId, profile, { mobile })));
    section.appendChild(list);
    return section;
  }

  function profilesForLaunch(projectId) {
    return [...stateFor(projectId).profiles];
  }

  return {
    deleteProfile,
    invalidate,
    load,
    openEditor,
    profileAvailability,
    profilesForLaunch,
    renderSection,
    stateFor,
  };
}

export { createProjectHttpProfileManager };
