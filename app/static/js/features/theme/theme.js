// ── Theme ──
import { APP_CONFIG as importedAppConfig } from '../../core/config.js';
import { themeSelect as importedThemeSelect } from '../../core/dom.js';
import { emitUiEvent as importedEmitUiEvent } from '../../core/state.js';
import { buildPromptLabel as importedBuildPromptLabel } from '../../output.js';
import { logClientError as importedLogClientError } from '../../session.js';
import {
  _persistCurrentSessionPreferences as importedPersistCurrentSessionPreferences,
  getPreference as importedGetPreference,
} from '../preferences/preferences.js';

function _themeSelectEl() {
  return (typeof importedThemeSelect !== 'undefined' && importedThemeSelect)
    || (typeof document !== 'undefined' ? document.getElementById('theme-select') : null);
}

function _themeLogClientError(message, err) {
  const log = typeof importedLogClientError === 'function' ? importedLogClientError : null;
  if (log) log(message, err);
}

function _getThemeRegistry() {
  // Prefer the runtime /themes payload when present, then fall back to the
  // bootstrapped globals so the selector still works during partial failures.
  if (typeof window !== 'undefined' && window.ThemeRegistry && typeof window.ThemeRegistry === 'object') {
    return window.ThemeRegistry;
  }
  const currentThemeName = (document.body && document.body.dataset && document.body.dataset.theme) || _savedThemeName() || '';
  const currentThemeVars = typeof window !== 'undefined' && window.ThemeCssVars && window.ThemeCssVars.current
    && typeof window.ThemeCssVars.current === 'object'
    ? window.ThemeCssVars.current
    : {};
  return {
    current: currentThemeName
      ? { name: currentThemeName, label: currentThemeName, source: 'fallback', vars: currentThemeVars }
      : null,
    themes: [],
  };
}

function _getThemeThemes() {
  const registry = _getThemeRegistry();
  return Array.isArray(registry.themes) ? registry.themes : [];
}

function _normalizeThemeName(name) {
  const value = typeof name === 'string' ? name.trim() : '';
  return value.endsWith('.yaml') ? value.slice(0, -5) : value;
}

function _themeEntryMatches(entry, name) {
  const needle = _normalizeThemeName(name);
  if (!needle) return false;
  return _normalizeThemeName(entry?.name) === needle || _normalizeThemeName(entry?.filename) === needle;
}

function _themeEntryGroup(entry) {
  const group = typeof entry?.group === 'string' ? entry.group.trim() : '';
  return group || 'Other';
}

function _themeEntrySortValue(entry) {
  const value = Number(entry?.sort);
  return Number.isFinite(value) ? value : Number.POSITIVE_INFINITY;
}

function _compareThemeEntries(a, b) {
  const sortA = _themeEntrySortValue(a);
  const sortB = _themeEntrySortValue(b);
  if (sortA !== sortB) return sortA - sortB;
  const groupA = _themeEntryGroup(a).toLowerCase();
  const groupB = _themeEntryGroup(b).toLowerCase();
  if (groupA !== groupB) return groupA.localeCompare(groupB);
  const labelA = String(a?.label || a?.name || '').toLowerCase();
  const labelB = String(b?.label || b?.name || '').toLowerCase();
  if (labelA !== labelB) return labelA.localeCompare(labelB);
  return String(a?.name || '').localeCompare(String(b?.name || ''));
}

function _findThemeEntry(name) {
  const needle = _normalizeThemeName(name);
  if (!needle) return null;
  const registry = _getThemeRegistry();
  if (registry.current && _themeEntryMatches(registry.current, needle)) return registry.current;
  return _getThemeThemes().find(theme => theme && _themeEntryMatches(theme, needle)) || null;
}

function _defaultThemeEntry() {
  const registry = _getThemeRegistry();
  const appConfig = typeof importedAppConfig !== 'undefined' ? importedAppConfig : null;
  return registry.current || _findThemeEntry(appConfig?.default_theme || '') || {
    name: 'dark',
    label: 'Dark',
    source: 'built-in',
    vars: (window.ThemeCssVars && window.ThemeCssVars.fallback) || {},
    theme_vars: (window.ThemeCssVars && window.ThemeCssVars.fallback) || {},
  };
}

function _applyThemeVars(entry) {
  if (!entry || !entry.vars || !document.documentElement) return;
  Object.entries(entry.vars).forEach(([name, value]) => {
    document.documentElement.style.setProperty(name, value);
  });
  document.documentElement.style.colorScheme = entry.color_scheme || 'light dark';
  const colorSchemeMeta = document.querySelector('meta[name="color-scheme"]');
  if (colorSchemeMeta) colorSchemeMeta.setAttribute('content', entry.color_scheme || 'light dark');
}

function _applyThemePreviewVars(target, vars) {
  if (!target || !vars || !target.style) return;
  Object.entries(vars).forEach(([name, value]) => {
    target.style.setProperty(name, value);
  });
}

function _persistThemeEntry(entry) {
  if (!entry) return;
  try {
    if (typeof importedPersistCurrentSessionPreferences === 'function') {
      void importedPersistCurrentSessionPreferences();
    }
  } catch (err) {
    _themeLogClientError('failed to persist theme preference', err);
  }
}

function _savedThemeName() {
  const getPreference = typeof importedGetPreference === 'function' ? importedGetPreference : null;
  return (getPreference ? getPreference('pref_theme_name') : '')
    || localStorage.getItem('theme')
    || (getPreference ? getPreference('pref_theme') : '')
    || '';
}

function _resolveThemeEntry(name) {
  return _findThemeEntry(name) || _defaultThemeEntry();
}

function _buildThemePreviewCard(theme) {
  const card = document.createElement('button');
  const themeName = theme?.name || '';
  const themeLabel = theme?.label || themeName;
  card.type = 'button';
  card.className = 'theme-card';
  card.dataset.themeName = themeName;
  card.dataset.themeLabel = themeLabel;
  card.setAttribute('aria-label', `${themeLabel} theme`);
  card.setAttribute('aria-pressed', 'false');
  _applyThemePreviewVars(card, theme?.vars || {});
  const preview = document.createElement('span');
  preview.className = 'theme-card-preview';
  preview.setAttribute('aria-hidden', 'true');

  const rail = document.createElement('span');
  rail.className = 'theme-card-preview-rail';
  for (let i = 0; i < 3; i += 1) {
    const railSection = document.createElement('span');
    railSection.className = 'theme-card-preview-rail-section';
    const railHeader = document.createElement('span');
    railHeader.className = 'theme-card-preview-rail-header';
    railSection.appendChild(railHeader);
    for (let j = 0; j < 2; j += 1) {
      const railLine = document.createElement('span');
      railLine.className = 'theme-card-preview-rail-line';
      railSection.appendChild(railLine);
    }
    rail.appendChild(railSection);
  }

  const shell = document.createElement('span');
  shell.className = 'theme-card-preview-shell';

  const tabbar = document.createElement('span');
  tabbar.className = 'theme-card-preview-tabbar';
  const activeTab = document.createElement('span');
  activeTab.className = 'theme-card-preview-tab theme-card-preview-tab-active';
  const idleTab = document.createElement('span');
  idleTab.className = 'theme-card-preview-tab';
  tabbar.appendChild(activeTab);
  tabbar.appendChild(idleTab);

  const content = document.createElement('span');
  content.className = 'theme-card-preview-content';
  const prompt = document.createElement('span');
  prompt.className = 'theme-card-preview-prompt';
  prompt.textContent = typeof importedBuildPromptLabel === 'function'
    ? importedBuildPromptLabel()
    : 'anon@darklab.sh:~ $';
  content.appendChild(prompt);
  for (let index = 0; index < 4; index += 1) {
    const line = document.createElement('span');
    line.className = 'theme-card-preview-line';
    line.style.setProperty('--theme-preview-line-width', `${86 - (index * 13)}%`);
    content.appendChild(line);
  }

  const modal = document.createElement('span');
  modal.className = 'theme-card-preview-modal';
  const modalHeader = document.createElement('span');
  modalHeader.className = 'theme-card-preview-modal-header';
  const modalBody = document.createElement('span');
  modalBody.className = 'theme-card-preview-modal-body';
  const modalActions = document.createElement('span');
  modalActions.className = 'theme-card-preview-modal-actions';
  for (let i = 0; i < 2; i += 1) {
    const modalButton = document.createElement('span');
    modalButton.className = 'theme-card-preview-modal-button';
    modalActions.appendChild(modalButton);
  }
  modal.appendChild(modalHeader);
  modal.appendChild(modalBody);
  modal.appendChild(modalActions);

  const hud = document.createElement('span');
  hud.className = 'theme-card-preview-hud';
  for (let i = 0; i < 5; i += 1) {
    const cell = document.createElement('span');
    cell.className = 'theme-card-preview-hud-cell';
    hud.appendChild(cell);
  }

  shell.appendChild(tabbar);
  shell.appendChild(content);
  shell.appendChild(modal);
  shell.appendChild(hud);
  preview.appendChild(rail);
  preview.appendChild(shell);

  const label = document.createElement('span');
  label.className = 'theme-card-label';
  label.textContent = themeLabel;
  card.appendChild(preview);
  card.appendChild(label);
  card.addEventListener('click', () => {
    applyThemeSelection(themeName);
  });
  return card;
}

function renderThemeSelectionOptions() {
  const themeSelect = _themeSelectEl();
  if (!themeSelect || themeSelect.dataset.wired === '1') return;
  const themes = [..._getThemeThemes()].sort(_compareThemeEntries);
  themeSelect.innerHTML = '';
  if (!themes.length) {
    const empty = document.createElement('div');
    empty.className = 'theme-picker-empty';
    empty.textContent = 'No themes available';
    themeSelect.appendChild(empty);
    themeSelect.dataset.wired = '1';
    return;
  }
  const groupCounts = themes.reduce((counts, theme) => {
    const themeGroup = _themeEntryGroup(theme);
    counts[themeGroup] = (counts[themeGroup] || 0) + 1;
    return counts;
  }, {});
  const maxColumns = Math.max(1, ...Object.values(groupCounts));
  const desktopColumns = Math.max(1, Math.min(maxColumns, 2));
  themeSelect.style.setProperty('--theme-picker-columns', String(desktopColumns));
  const mobileColumns = Math.max(1, Math.min(maxColumns, 2));
  themeSelect.style.setProperty('--theme-picker-columns-mobile', String(mobileColumns));
  let currentGroup = null;
  let groupSection = null;
  let groupGrid = null;
  themes.forEach(theme => {
    const themeGroup = _themeEntryGroup(theme);
    if (themeGroup !== currentGroup) {
      currentGroup = themeGroup;
      groupSection = document.createElement('section');
      groupSection.className = 'theme-picker-group';
      groupSection.dataset.themeGroup = themeGroup;
      const groupTitle = document.createElement('div');
      groupTitle.className = 'theme-picker-group-title';
      groupTitle.textContent = themeGroup;
      groupGrid = document.createElement('div');
      groupGrid.className = 'theme-picker-group-grid';
      groupSection.appendChild(groupTitle);
      groupSection.appendChild(groupGrid);
      themeSelect.appendChild(groupSection);
    }
    if (groupGrid) groupGrid.appendChild(_buildThemePreviewCard(theme));
  });
  themeSelect.dataset.wired = '1';
}

function syncThemeSelectionControls() {
  const current = _resolveThemeEntry(document.body?.dataset?.theme || _savedThemeName());
  const themeName = current?.name || '';
  const themeSelect = _themeSelectEl();
  if (!themeSelect) return;
  themeSelect.dataset.theme = themeName;
  themeSelect.querySelectorAll('[data-theme-name]').forEach(card => {
    const active = card.dataset.themeName === themeName;
    card.classList.toggle('theme-card-active', active);
    card.classList.toggle('is-selected-card', active);
    card.setAttribute('aria-pressed', active ? 'true' : 'false');
  });
}

function applyThemeSelection(themeName, persist = true) {
  // Theme preview uses the same resolved-entry path as persisted selection, so
  // the drawer/modal never shows a palette the runtime cannot actually apply.
  const entry = _resolveThemeEntry(themeName);
  if (!entry) return;
  if (document.body) document.body.dataset.theme = entry.name;
  _applyThemeVars(entry);
  if (typeof window !== 'undefined') {
    const registry = _getThemeRegistry();
    registry.current = entry;
    window.ThemeRegistry = registry;
    if (window.ThemeCssVars && typeof window.ThemeCssVars === 'object') {
      window.ThemeCssVars.current = entry.vars || {};
    }
  }
  if (persist) _persistThemeEntry(entry);
  syncThemeSelectionControls();
  if (typeof importedEmitUiEvent === 'function') {
    importedEmitUiEvent('app:theme-changed', { theme: entry.name });
  }
}

export {
  _compareThemeEntries,
  _defaultThemeEntry,
  _findThemeEntry,
  _getThemeRegistry,
  _getThemeThemes,
  _normalizeThemeName,
  _resolveThemeEntry,
  _savedThemeName,
  applyThemeSelection,
  renderThemeSelectionOptions,
  syncThemeSelectionControls,
};
