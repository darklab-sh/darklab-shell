(function initTeamScope(global) {
  if (typeof document === 'undefined') return;

  const trigger = document.getElementById('team-scope-trigger');
  const hudLabel = document.getElementById('team-scope-label');
  const mobileLabel = document.getElementById('mobile-team-scope-label');
  const mobileScopeRow = mobileLabel?.closest?.('.mobile-scope-row') || mobileLabel?.closest?.('[data-menu-action="scope"]');
  const overlay = document.getElementById('team-scope-overlay');
  const modal = document.getElementById('team-scope-modal');
  const currentEl = document.getElementById('team-scope-current');
  const statusEl = document.getElementById('team-scope-status');
  const announcerEl = document.getElementById('team-scope-announcer');
  const listEl = document.getElementById('team-scope-list');
  const closeBtn = overlay?.querySelector?.('.team-scope-close');
  const grabHandle = overlay?.querySelector?.('.sheet-grab');
  const STORAGE_PREFIX = 'active_team_id:';
  const PERSONAL_SCOPE_OPTION = 'personal';
  const MENU_ID = 'team-scope-menu';
  let teams = [];
  let activeTeamId = '';
  let refreshing = null;
  let teamScopesResolved = false;
  let scopeLoadError = false;
  let dismissibleBound = false;
  let menu = null;
  let menuList = null;
  let menuNote = null;
  let menuOutsideBound = false;

  function storageKey() {
    const sessionId = typeof SESSION_ID !== 'undefined' ? SESSION_ID : 'anonymous';
    return `${STORAGE_PREFIX}${sessionId || 'anonymous'}`;
  }

  function storageKeySuffix(key = storageKey()) {
    const value = String(key || '');
    const suffix = value.startsWith(STORAGE_PREFIX) ? value.slice(STORAGE_PREFIX.length) : value;
    return suffix.length > 8 ? suffix.slice(-8) : suffix;
  }

  function errorMessage(err) {
    if (err && typeof err.message === 'string') return err.message;
    return String(err || '');
  }

  function logTeamScopeClientEvent(event, fields = {}, level = 'debug') {
    if (typeof apiFetch !== 'function') return;
    apiFetch('/log', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        event,
        level,
        context: event,
        message: JSON.stringify(fields),
      }),
    }).catch(() => {});
  }

  function logStorageUnavailable(operation, key, err) {
    logTeamScopeClientEvent('TEAM_SCOPE_STORAGE_UNAVAILABLE', {
      operation,
      key_suffix: storageKeySuffix(key),
      message: errorMessage(err),
    });
  }

  function logRefreshFailure(surface, err) {
    const details = {
      surface,
      team_id: activeTeamId || '',
      message: errorMessage(err),
    };
    if (typeof logClientError === 'function') {
      const wrapped = err instanceof Error ? err : new Error(details.message);
      logClientError(`TEAM_SCOPE_REFRESH_FAILED ${JSON.stringify({
        surface: details.surface,
        team_id: details.team_id,
      })}`, wrapped);
      return;
    }
    logTeamScopeClientEvent('TEAM_SCOPE_REFRESH_FAILED', details, 'warning');
  }

  function getStoredTeamId() {
    const key = storageKey();
    try { return localStorage.getItem(key) || ''; } catch (err) {
      logStorageUnavailable('read', key, err);
      return '';
    }
  }

  function storeTeamId(teamId) {
    const key = storageKey();
    try {
      if (teamId) localStorage.setItem(key, teamId);
      else localStorage.removeItem(key);
    } catch (err) {
      logStorageUnavailable(teamId ? 'write' : 'remove', key, err);
    }
  }

  function normalizeTeamId(teamId) {
    const value = String(teamId || '').trim();
    return value === PERSONAL_SCOPE_OPTION ? '' : value;
  }

  function getActiveTeamId() {
    return activeTeamId || '';
  }

  function getActiveTeam() {
    if (!activeTeamId) return null;
    return teams.find(item => item.id === activeTeamId) || null;
  }

  function getActiveTeamCapabilities() {
    const team = getActiveTeam();
    return Array.isArray(team?.capabilities) ? team.capabilities : [];
  }

  function activeTeamScopeCan(capability) {
    if (!activeTeamId) return true;
    const wanted = String(capability || '').trim();
    if (!wanted) return true;
    return getActiveTeamCapabilities().includes(wanted);
  }

  function teamScopeDeniedMessage(action = 'make this change') {
    const text = String(action || 'make this change').trim() || 'make this change';
    return `View-only team members can't ${text}. Switch to Personal or ask for operator access.`;
  }

  function activeLabel() {
    return activeScopeState().label;
  }

  function activeScopeState() {
    if (!activeTeamId) return { label: 'Personal', tone: '' };
    const team = teams.find(item => item.id === activeTeamId);
    if (team) return { label: team.name, tone: '' };
    if (scopeLoadError) return { label: 'Team unavailable', tone: 'error' };
    if (!teamScopesResolved || refreshing) return { label: 'Loading...', tone: 'loading' };
    return { label: 'Team unavailable', tone: 'error' };
  }

  function applyScopeTone(el, tone = '') {
    if (!el) return;
    el.classList.toggle('is-loading', tone === 'loading');
    el.classList.toggle('is-error', tone === 'error');
  }

  function optionLabel(team) {
    return team.name || team.slug || 'Team';
  }

  function showStatus(message = '', tone = '') {
    if (!statusEl) return;
    statusEl.textContent = String(message || '');
    statusEl.classList.toggle('u-hidden', !message);
    statusEl.classList.toggle('is-error', tone === 'error');
  }

  function announceScopeChange(label) {
    if (!announcerEl) return;
    announcerEl.textContent = '';
    window.setTimeout(() => {
      announcerEl.textContent = `Active scope changed to ${label}.`;
    }, 0);
  }

  function renderButton(team = null) {
    const active = team ? team.id === activeTeamId : !activeTeamId;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = `dropdown-item dropdown-item-touch team-scope-option${active ? ' is-active' : ''}`;
    button.dataset.teamScopeOption = team ? team.id : PERSONAL_SCOPE_OPTION;
    button.setAttribute('role', 'option');
    button.setAttribute('aria-selected', active ? 'true' : 'false');

    const main = document.createElement('span');
    main.className = 'team-scope-option-main';
    const name = document.createElement('span');
    name.className = 'team-scope-option-name';
    name.textContent = team ? optionLabel(team) : 'Personal';
    main.appendChild(name);
    if (team?.role) {
      const meta = document.createElement('span');
      meta.className = 'team-scope-option-meta';
      meta.textContent = team.role;
      main.appendChild(meta);
    }

    const marker = document.createElement('span');
    marker.className = 'team-scope-option-marker';
    marker.textContent = active ? 'active' : 'select';
    button.append(main, marker);
    return button;
  }

  function renderMenuButton(team = null) {
    const active = team ? team.id === activeTeamId : !activeTeamId;
    const label = team ? optionLabel(team) : 'Personal';
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'dropdown-item dropdown-item-compact team-scope-menu-option';
    button.dataset.teamScopeMenuOption = team ? team.id : PERSONAL_SCOPE_OPTION;
    button.setAttribute('role', 'menuitemradio');
    button.setAttribute('aria-checked', active ? 'true' : 'false');
    button.textContent = active ? `${label} (active)` : label;
    button.title = active ? `Active scope: ${label}` : `Switch to ${label}`;
    button.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();
      setActiveTeamId(button.dataset.teamScopeMenuOption || '', { source: 'selector' });
      closeScopeMenu();
    });
    return button;
  }

  function isModalOpen() {
    return !!(overlay && overlay.classList.contains('open'));
  }

  function isScopeMenuOpen() {
    return !!(menu && !menu.classList.contains('u-hidden'));
  }

  function setScopeMenuNote(text = '') {
    if (!menuNote) return;
    menuNote.textContent = String(text || '');
    menuNote.classList.toggle('u-hidden', !text);
  }

  function renderMenuOptions() {
    if (!menuList) return;
    menuList.replaceChildren();
    menuList.appendChild(renderMenuButton(null));
    teams.forEach(team => {
      menuList.appendChild(renderMenuButton(team));
    });
    if (refreshing && !teamScopesResolved) setScopeMenuNote('Loading teams...');
    else if (!teams.length) setScopeMenuNote('No teams yet.');
    else setScopeMenuNote('');
  }

  function renderOptions() {
    if (listEl) {
      listEl.innerHTML = '';
      listEl.appendChild(renderButton(null));
      teams.forEach(team => {
        listEl.appendChild(renderButton(team));
      });
    }
    renderMenuOptions();
  }

  function render() {
    const state = activeScopeState();
    const label = state.label;
    if (hudLabel) hudLabel.textContent = label;
    if (mobileLabel) mobileLabel.textContent = label;
    if (currentEl) currentEl.textContent = label;
    applyScopeTone(trigger, state.tone);
    applyScopeTone(mobileScopeRow, state.tone);
    applyScopeTone(currentEl, state.tone);
    if (trigger) trigger.title = `Active scope: ${label}`;
    renderOptions();
  }

  function reloadScopedSurfaces() {
    [
      ['history', () => (typeof reloadSessionHistory === 'function' ? reloadSessionHistory() : null)],
      ['recent_values', () => (typeof loadRecentValues === 'function' ? loadRecentValues() : null)],
      ['workspace_files', () => (typeof refreshWorkspaceFileCache === 'function' ? refreshWorkspaceFileCache() : null)],
      ['active_project', () => (typeof window.refreshActiveProjectContext === 'function' ? window.refreshActiveProjectContext() : null)],
      ['options_secrets', () => (typeof global.invalidateOptionsSecrets === 'function' ? global.invalidateOptionsSecrets() : null)],
      ['active_runs', () => (typeof refreshActiveRuns === 'function' ? refreshActiveRuns() : null)],
      ['status_monitor', () => (typeof window.refreshStatusMonitor === 'function' ? window.refreshStatusMonitor() : null)],
    ].forEach(([surface, refresh]) => {
      try {
        const result = refresh();
        if (result && typeof result.catch === 'function') {
          result.catch(err => logRefreshFailure(surface, err));
        }
      } catch (err) {
        logRefreshFailure(surface, err);
      }
    });
  }

  function setActiveTeamId(teamId, { persist = true, emit = true, allowPending = false, source = 'direct' } = {}) {
    const normalized = normalizeTeamId(teamId);
    if (activeTeamId === normalized) return true;
    const knownTeam = !normalized || teams.some(team => team.id === normalized);
    if (!knownTeam && !allowPending) return false;
    activeTeamId = normalized;
    if (normalized && !knownTeam) {
      teamScopesResolved = false;
      scopeLoadError = false;
    }
    if (persist) storeTeamId(activeTeamId);
    render();
    const label = activeLabel();
    if (emit) {
      logTeamScopeClientEvent('TEAM_SCOPE_CHANGED', {
        team_id: activeTeamId,
        scope: activeTeamId ? 'team' : 'personal',
        persisted: !!persist,
        source,
      });
      document.dispatchEvent(new CustomEvent('app:scope-changed', {
        detail: { team_id: activeTeamId, label },
      }));
      announceScopeChange(label);
      reloadScopedSurfaces();
    }
    if (normalized && !knownTeam) {
      refreshTeamScopes().catch(() => {});
    }
    return true;
  }

  function isOpen() {
    return isModalOpen() || isScopeMenuOpen();
  }

  function positionScopeMenu() {
    if (!menu || !trigger || !isScopeMenuOpen()) return;
    const anchor = trigger.closest?.('.hud-cell') || trigger;
    const rect = anchor.getBoundingClientRect();
    const menuWidth = menu.offsetWidth || 260;
    const viewportWidth = global.innerWidth || document.documentElement.clientWidth || 0;
    const left = Math.max(8, Math.min(rect.left, Math.max(8, viewportWidth - menuWidth - 8)));
    menu.style.left = `${left}px`;
    menu.style.bottom = `${Math.max(8, (global.innerHeight || 0) - rect.top - 1)}px`;
  }

  function closeScopeMenu({ restoreFocus = false } = {}) {
    if (!menu) return;
    menu.classList.add('u-hidden');
    trigger?.classList.remove('open');
    trigger?.setAttribute('aria-expanded', 'false');
    setScopeMenuNote('');
    if (restoreFocus && trigger && typeof trigger.focus === 'function') {
      trigger.focus({ preventScroll: true });
    }
  }

  function focusScopeMenuItem(delta) {
    if (!menu) return;
    const items = Array.from(menu.querySelectorAll('.dropdown-item:not([disabled])'));
    if (!items.length) return;
    const currentIdx = items.indexOf(document.activeElement);
    const fallbackIdx = delta > 0 ? -1 : 0;
    const nextIdx = (currentIdx >= 0 ? currentIdx : fallbackIdx) + delta;
    items[(nextIdx + items.length) % items.length]?.focus({ preventScroll: true });
  }

  function ensureScopeMenu() {
    if (menu) return menu;
    const popup = document.createElement('div');
    popup.id = MENU_ID;
    popup.className = 'hud-project-menu team-scope-menu dropdown-surface dropdown-up u-hidden';
    popup.setAttribute('role', 'menu');
    popup.setAttribute('aria-label', 'Active data scope');

    const section = document.createElement('div');
    section.className = 'hud-project-menu-section';
    popup.appendChild(section);

    const note = document.createElement('div');
    note.className = 'hud-project-menu-note u-hidden';
    popup.appendChild(note);

    popup.addEventListener('click', event => event.stopPropagation());
    popup.addEventListener('keydown', event => {
      event.stopPropagation();
      if (event.key === 'Escape') {
        event.preventDefault();
        closeScopeMenu({ restoreFocus: true });
      } else if (event.key === 'ArrowDown') {
        event.preventDefault();
        focusScopeMenuItem(1);
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        focusScopeMenuItem(-1);
      } else if (event.key === 'Tab') {
        closeScopeMenu();
      }
    });

    document.body.appendChild(popup);
    menu = popup;
    menuList = section;
    menuNote = note;

    if (typeof global.bindOutsideClickClose === 'function') {
      global.bindOutsideClickClose(menu, {
        capture: true,
        triggers: trigger,
        isOpen: isScopeMenuOpen,
        onClose: () => closeScopeMenu(),
      });
    } else if (!menuOutsideBound) {
      menuOutsideBound = true;
      document.addEventListener('click', event => {
        if (!isScopeMenuOpen()) return;
        const target = event.target;
        if (target instanceof Node && (menu.contains(target) || trigger?.contains?.(target))) return;
        closeScopeMenu();
      }, true);
    }
    return menu;
  }

  function setOverlayAccessible(open) {
    if (!overlay) return;
    if (!open && typeof overlay.contains === 'function' && overlay.contains(document.activeElement)) {
      document.activeElement?.blur?.();
    }
    overlay.setAttribute('aria-hidden', open ? 'false' : 'true');
    overlay.toggleAttribute('inert', !open);
  }

  function closeTeamScopeSelector({ refocus = true } = {}) {
    closeScopeMenu();
    if (!overlay) return;
    setOverlayAccessible(false);
    overlay.classList.add('u-hidden');
    overlay.classList.remove('open');
    showStatus('');
    if (typeof global.syncModalOverlayState === 'function') global.syncModalOverlayState();
    if (refocus && typeof global.refocusComposerAfterAction === 'function') {
      global.refocusComposerAfterAction({ defer: true });
    }
  }

  function showTeamScopeSelector() {
    if (!overlay) return false;
    closeScopeMenu();
    bindModalDismissal();
    if (typeof global._closeMajorOverlays === 'function') global._closeMajorOverlays();
    if (typeof global.blurVisibleComposerInputIfMobile === 'function') global.blurVisibleComposerInputIfMobile();
    setOverlayAccessible(true);
    overlay.classList.remove('u-hidden');
    overlay.classList.add('open');
    showStatus('');
    render();
    if (typeof global.syncModalOverlayState === 'function') global.syncModalOverlayState();
    const active = listEl?.querySelector?.('.team-scope-option.is-active');
    (active || closeBtn || modal)?.focus?.({ preventScroll: true });
    return true;
  }

  function toggleScopeMenu(event) {
    event?.preventDefault?.();
    event?.stopPropagation?.();
    if (isScopeMenuOpen()) {
      closeScopeMenu({ restoreFocus: true });
      return true;
    }
    if (typeof global._closeMajorOverlays === 'function') global._closeMajorOverlays();
    closeTeamScopeSelector({ refocus: false });
    ensureScopeMenu();
    render();
    menu.classList.remove('u-hidden');
    trigger?.classList.add('open');
    trigger?.setAttribute('aria-expanded', 'true');
    positionScopeMenu();
    requestAnimationFrame(positionScopeMenu);
    const active = menu.querySelector?.('[aria-checked="true"]');
    const first = menu.querySelector?.('.dropdown-item:not([disabled])');
    (active || first || menu)?.focus?.({ preventScroll: true });
    refreshTeamScopes().catch(() => {});
    return true;
  }

  function bindModalDismissal() {
    if (!overlay || dismissibleBound) return;
    dismissibleBound = true;
    const closeButtons = Array.from(overlay.querySelectorAll('.team-scope-close'));
    if (typeof global.bindDismissible === 'function') {
      global.bindDismissible(overlay, {
        level: 'modal',
        isOpen,
        onClose: closeTeamScopeSelector,
        closeButtons,
      });
    } else {
      closeButtons.forEach(button => {
        button.addEventListener('click', () => closeTeamScopeSelector());
      });
      overlay.addEventListener('click', event => {
        if (event.target === overlay) closeTeamScopeSelector();
      });
    }
    if (typeof global.bindMobileSheet === 'function' && modal) {
      global.bindMobileSheet(modal, { onClose: closeTeamScopeSelector });
    } else {
      grabHandle?.addEventListener('click', () => closeTeamScopeSelector());
    }
  }

  function normalizeTeams(payload) {
    const rows = Array.isArray(payload?.teams) ? payload.teams : [];
    return rows.map((team) => ({
      id: String(team.id || ''),
      name: String(team.name || team.slug || 'Team'),
      slug: String(team.slug || ''),
      role: String(team.member?.role || ''),
      capabilities: Array.isArray(team.member?.capabilities)
        ? team.member.capabilities.map(item => String(item || '')).filter(Boolean)
        : [],
    })).filter(team => team.id);
  }

  function replaceTeamScopes(payload) {
    teams = normalizeTeams(payload);
    const stored = normalizeTeamId(getStoredTeamId());
    activeTeamId = teams.some(team => team.id === stored) ? stored : '';
    teamScopesResolved = true;
    scopeLoadError = false;
    if (!activeTeamId) storeTeamId('');
    render();
    document.dispatchEvent(new CustomEvent('app:scope-capabilities-changed', {
      detail: { team_id: activeTeamId },
    }));
    return teams;
  }

  async function refreshTeamScopes() {
    if (refreshing) return refreshing;
    const storedBeforeRefresh = normalizeTeamId(getStoredTeamId());
    if (storedBeforeRefresh && !activeTeamId) activeTeamId = storedBeforeRefresh;
    scopeLoadError = false;
    if (activeTeamId && !teams.some(team => team.id === activeTeamId)) {
      teamScopesResolved = false;
    }
    render();
    if (typeof apiFetch !== 'function') {
      teamScopesResolved = true;
      scopeLoadError = !!activeTeamId;
      render();
      return Promise.resolve([]);
    }
    refreshing = apiFetch('/session/teams', { cache: 'no-store' })
      .then(async (resp) => {
        if (resp.status === 401) {
          teams = [];
          teamScopesResolved = true;
          scopeLoadError = false;
          showStatus('');
          setActiveTeamId('', { persist: true, emit: false });
          render();
          return teams;
        }
        const payload = await resp.json().catch(() => ({}));
        if (!resp.ok) throw new Error(payload.error || resp.statusText || resp.status);
        return replaceTeamScopes(payload);
      })
      .catch((err) => {
        logRefreshFailure('teams', err);
        teams = [];
        if (!activeTeamId) activeTeamId = normalizeTeamId(getStoredTeamId());
        teamScopesResolved = true;
        scopeLoadError = !!activeTeamId;
        render();
        if (isModalOpen()) showStatus('Could not load teams.', 'error');
        if (isScopeMenuOpen()) setScopeMenuNote('Could not load teams.');
        return teams;
      })
      .finally(() => { refreshing = null; });
    return refreshing;
  }

  trigger?.addEventListener('click', toggleScopeMenu);
  trigger?.addEventListener('keydown', event => {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') toggleScopeMenu(event);
    else if (event.key === 'Escape' && isScopeMenuOpen()) {
      event.preventDefault();
      closeScopeMenu({ restoreFocus: true });
    }
  });

  listEl?.addEventListener('click', event => {
    const option = event.target.closest?.('[data-team-scope-option]');
    if (!option) return;
    event.preventDefault();
    if (setActiveTeamId(option.dataset.teamScopeOption || '', { source: 'selector' })) closeTeamScopeSelector();
  });

  global.getActiveTeamId = getActiveTeamId;
  global.getActiveTeam = getActiveTeam;
  global.getActiveTeamCapabilities = getActiveTeamCapabilities;
  global.activeTeamScopeCan = activeTeamScopeCan;
  global.teamScopeDeniedMessage = teamScopeDeniedMessage;
  global.setActiveTeamId = setActiveTeamId;
  global.refreshTeamScopes = refreshTeamScopes;
  global.replaceTeamScopes = replaceTeamScopes;
  global.isTeamScopeSelectorOpen = isOpen;
  global.openTeamScopeSelector = () => {
    const opened = showTeamScopeSelector();
    refreshTeamScopes().catch(() => {});
    return opened;
  };
  global.closeTeamScopeSelector = closeTeamScopeSelector;
  global.DarklabTeamScope = {
    getActiveTeamId,
    getActiveTeam,
    getActiveTeamCapabilities,
    activeTeamScopeCan,
    deniedMessage: teamScopeDeniedMessage,
    setActiveTeamId,
    refreshTeamScopes,
    replaceTeamScopes,
    isOpen,
    open: global.openTeamScopeSelector,
    close: closeTeamScopeSelector,
  };

  window.addEventListener('storage', (event) => {
    if (event.key === storageKey()) {
      const nextTeamId = normalizeTeamId(event.newValue);
      if (nextTeamId !== activeTeamId) {
        setActiveTeamId(nextTeamId, { persist: false, allowPending: true, source: 'storage' });
      }
    }
  });
  window.addEventListener('resize', positionScopeMenu);
  document.addEventListener('DOMContentLoaded', () => {
    bindModalDismissal();
    refreshTeamScopes().catch(() => {});
  });
})(window);
