// darklab_shell Command Registry modal and command catalog helpers.
import {
  commandCatalogBody as importedCommandCatalogBody,
  commandCatalogOverlay as importedCommandCatalogOverlay,
  commandRegistryBody as importedCommandRegistryBody,
  commandRegistryCategories as importedCommandRegistryCategories,
  commandRegistryOverlay as importedCommandRegistryOverlay,
  commandRegistrySearch as importedCommandRegistrySearch,
  commandRegistrySubtitle as importedCommandRegistrySubtitle,
} from '../../core/dom.js';
import {
  blurVisibleComposerInputIfMobile as importedBlurVisibleComposerInputIfMobile,
  getVisibleComposerInput as importedGetVisibleComposerInput,
  markInteractionSurfaceReady as importedMarkInteractionSurfaceReady,
  refocusComposerAfterAction as importedRefocusComposerAfterAction,
  setComposerValue as importedSetComposerValue,
} from '../../ui/ui_helpers.js';
import { activateFaqCommandChip as importedActivateFaqCommandChip } from './faq_helpers.js';
import { bindPressable as importedBindPressable } from '../../ui/ui_pressable.js';
import { closeMajorOverlays as importedCloseMajorOverlays } from '../../ui/overlay_actions_bridge.js';
import {
  getCommandRegistryData as importedGetCommandRegistryData,
  setCommandRegistryHandlers as importedSetCommandRegistryHandlers,
} from './command_registry_bridge.js';
import {
  apiFetch as importedRuntimeApiFetch,
  hasRuntimeHandler as importedHasRuntimeHandler,
  logClientError as importedRuntimeLogClientError,
} from '../../runtime_bridge.js';

const COMMAND_REGISTRY_GLOBAL = typeof window !== 'undefined' ? window : globalThis;

function _commandRegistryGlobalData() {
  if (typeof importedGetCommandRegistryData === 'function') {
    const data = importedGetCommandRegistryData();
    if (data) return data;
  }
  if (typeof window !== 'undefined' && window.commandRegistryData) return window.commandRegistryData;
  if (typeof globalThis !== 'undefined' && globalThis.commandRegistryData) return globalThis.commandRegistryData;
  return null;
}

let commandRegistryData = _commandRegistryGlobalData();
let commandRegistryCategory = 'All';
let commandRegistryQuery = '';
let commandRegistryCategoryResizeBound = false;
const COMMAND_REGISTRY_CATEGORY_SCROLL_EPSILON = 2;

function _commandRegistryOverlay() {
  if (typeof importedCommandRegistryOverlay !== 'undefined' && importedCommandRegistryOverlay) return importedCommandRegistryOverlay;
  return COMMAND_REGISTRY_GLOBAL.commandRegistryOverlay || null;
}

function _commandRegistryBody() {
  if (typeof importedCommandRegistryBody !== 'undefined' && importedCommandRegistryBody) return importedCommandRegistryBody;
  return COMMAND_REGISTRY_GLOBAL.commandRegistryBody || null;
}

function _commandRegistrySearch() {
  if (typeof importedCommandRegistrySearch !== 'undefined' && importedCommandRegistrySearch) return importedCommandRegistrySearch;
  return COMMAND_REGISTRY_GLOBAL.commandRegistrySearch || null;
}

function _commandRegistryCategoriesEl() {
  if (typeof importedCommandRegistryCategories !== 'undefined' && importedCommandRegistryCategories) return importedCommandRegistryCategories;
  return COMMAND_REGISTRY_GLOBAL.commandRegistryCategories || null;
}

function _commandRegistryCategoryScrollLeftBtn() {
  return document.getElementById('command-registry-categories-scroll-left');
}

function _commandRegistryCategoryScrollRightBtn() {
  return document.getElementById('command-registry-categories-scroll-right');
}

function _commandRegistrySubtitleEl() {
  if (typeof importedCommandRegistrySubtitle !== 'undefined' && importedCommandRegistrySubtitle) return importedCommandRegistrySubtitle;
  return COMMAND_REGISTRY_GLOBAL.commandRegistrySubtitle || null;
}

function _commandCatalogOverlay() {
  if (typeof importedCommandCatalogOverlay !== 'undefined' && importedCommandCatalogOverlay) return importedCommandCatalogOverlay;
  return COMMAND_REGISTRY_GLOBAL.commandCatalogOverlay || null;
}

function _commandCatalogBody() {
  if (typeof importedCommandCatalogBody !== 'undefined' && importedCommandCatalogBody) return importedCommandCatalogBody;
  return COMMAND_REGISTRY_GLOBAL.commandCatalogBody || null;
}

function _commandRegistryRefocusComposerAfterAction(options) {
  const refocus = typeof importedRefocusComposerAfterAction === 'function'
    ? importedRefocusComposerAfterAction
    : (typeof COMMAND_REGISTRY_GLOBAL.refocusComposerAfterAction === 'function' ? COMMAND_REGISTRY_GLOBAL.refocusComposerAfterAction : null);
  if (refocus) refocus(options);
}

function _commandRegistryBlurVisibleComposerInputIfMobile() {
  const blur = typeof importedBlurVisibleComposerInputIfMobile === 'function'
    ? importedBlurVisibleComposerInputIfMobile
    : (typeof COMMAND_REGISTRY_GLOBAL.blurVisibleComposerInputIfMobile === 'function' ? COMMAND_REGISTRY_GLOBAL.blurVisibleComposerInputIfMobile : null);
  if (blur) blur();
}

function _commandRegistryMarkInteractionSurfaceReady(name, overlay, modal) {
  const mark = typeof importedMarkInteractionSurfaceReady === 'function'
    ? importedMarkInteractionSurfaceReady
    : (typeof COMMAND_REGISTRY_GLOBAL.markInteractionSurfaceReady === 'function' ? COMMAND_REGISTRY_GLOBAL.markInteractionSurfaceReady : null);
  if (mark) mark(name, overlay, modal);
}

function _commandRegistryBindPressable(el, options) {
  const bind = typeof importedBindPressable === 'function'
    ? importedBindPressable
    : (typeof COMMAND_REGISTRY_GLOBAL.bindPressable === 'function' ? COMMAND_REGISTRY_GLOBAL.bindPressable : null);
  return bind ? bind(el, options) : null;
}

function _commandRegistryApiFetch(...args) {
  const fetcher = (
    typeof importedHasRuntimeHandler === 'function'
    && importedHasRuntimeHandler('apiFetch')
    && typeof importedRuntimeApiFetch === 'function'
      ? importedRuntimeApiFetch
      : null
  ) || (typeof COMMAND_REGISTRY_GLOBAL.apiFetch === 'function' ? COMMAND_REGISTRY_GLOBAL.apiFetch : null);
  if (!fetcher) return Promise.reject(new Error('apiFetch is not available'));
  return fetcher(...args);
}

function _commandRegistryClientError(context, err) {
  const log = (
    typeof importedHasRuntimeHandler === 'function'
    && importedHasRuntimeHandler('logClientError')
    && typeof importedRuntimeLogClientError === 'function'
      ? importedRuntimeLogClientError
      : null
  ) || (typeof COMMAND_REGISTRY_GLOBAL.logClientError === 'function' ? COMMAND_REGISTRY_GLOBAL.logClientError : null);
  if (log) log(context, err);
}

function _afterCommandRegistryCategoryPaint(callback) {
  if (typeof callback !== 'function') return;
  callback();
  const raf = typeof COMMAND_REGISTRY_GLOBAL.requestAnimationFrame === 'function'
    ? COMMAND_REGISTRY_GLOBAL.requestAnimationFrame
    : null;
  if (raf) {
    raf(callback);
  } else if (typeof COMMAND_REGISTRY_GLOBAL.setTimeout === 'function') {
    COMMAND_REGISTRY_GLOBAL.setTimeout(callback, 0);
  }
}

function _updateCommandRegistryCategoryScrollers() {
  const categoriesEl = _commandRegistryCategoriesEl();
  const left = _commandRegistryCategoryScrollLeftBtn();
  const right = _commandRegistryCategoryScrollRightBtn();
  if (!categoriesEl || !left || !right) return;
  const maxScrollLeft = Math.max(0, (categoriesEl.scrollWidth || 0) - (categoriesEl.clientWidth || 0));
  const hasOverflow = maxScrollLeft > COMMAND_REGISTRY_CATEGORY_SCROLL_EPSILON;
  [left, right].forEach(button => {
    button.classList.toggle('u-hidden', !hasOverflow);
    button.setAttribute('aria-hidden', hasOverflow ? 'false' : 'true');
  });
  left.disabled = !hasOverflow || categoriesEl.scrollLeft <= COMMAND_REGISTRY_CATEGORY_SCROLL_EPSILON;
  right.disabled = !hasOverflow || categoriesEl.scrollLeft >= maxScrollLeft - COMMAND_REGISTRY_CATEGORY_SCROLL_EPSILON;
}

function _scrollCommandRegistryCategories(direction) {
  const categoriesEl = _commandRegistryCategoriesEl();
  if (!categoriesEl) return;
  const amount = Math.max(128, Math.floor((categoriesEl.clientWidth || 180) * 0.75));
  const delta = direction * amount;
  if (typeof categoriesEl.scrollBy === 'function') {
    categoriesEl.scrollBy({ left: delta, behavior: 'smooth' });
  } else {
    categoriesEl.scrollLeft += delta;
  }
  _afterCommandRegistryCategoryPaint(_updateCommandRegistryCategoryScrollers);
}

function _bindCommandRegistryCategoryScrollers() {
  const categoriesEl = _commandRegistryCategoriesEl();
  const left = _commandRegistryCategoryScrollLeftBtn();
  const right = _commandRegistryCategoryScrollRightBtn();
  if (categoriesEl && categoriesEl.dataset.categoryScrollBound !== 'true') {
    categoriesEl.dataset.categoryScrollBound = 'true';
    categoriesEl.addEventListener('scroll', _updateCommandRegistryCategoryScrollers, { passive: true });
  }
  if (left && left.dataset.categoryScrollBound !== 'true') {
    left.dataset.categoryScrollBound = 'true';
    left.addEventListener('click', event => {
      event.preventDefault();
      _scrollCommandRegistryCategories(-1);
    });
  }
  if (right && right.dataset.categoryScrollBound !== 'true') {
    right.dataset.categoryScrollBound = 'true';
    right.addEventListener('click', event => {
      event.preventDefault();
      _scrollCommandRegistryCategories(1);
    });
  }
  if (COMMAND_REGISTRY_GLOBAL && !commandRegistryCategoryResizeBound) {
    commandRegistryCategoryResizeBound = true;
    COMMAND_REGISTRY_GLOBAL.addEventListener?.('resize', _updateCommandRegistryCategoryScrollers, { passive: true });
  }
}

function showCommandRegistryOverlay() {
  const overlay = _commandRegistryOverlay();
  if (!overlay) return;
  overlay.classList.remove('u-hidden');
  overlay.classList.add('open');
  overlay.setAttribute('aria-hidden', 'false');
}

function hideCommandRegistryOverlay() {
  const overlay = _commandRegistryOverlay();
  if (!overlay) return;
  overlay.classList.add('u-hidden');
  overlay.classList.remove('open');
  overlay.setAttribute('aria-hidden', 'true');
}

function isCommandRegistryOverlayOpen() {
  const overlay = _commandRegistryOverlay();
  return !!(overlay && overlay.classList.contains('open'));
}

function closeCommandRegistry() {
  hideCommandRegistryOverlay();
  _commandRegistryRefocusComposerAfterAction({ defer: true });
}

function _commandRegistryCommands() {
  if (!commandRegistryData || !Array.isArray(commandRegistryData.commands)) return [];
  return commandRegistryData.commands.filter(item => item && item.root);
}

function _commandRegistryCategories() {
  const categories = new Set();
  _commandRegistryCommands().forEach(item => {
    const category = commandCatalogText(item.category, 'Allowed commands');
    if (category) categories.add(category);
  });
  return ['All', ...Array.from(categories)];
}

function _commandRegistryMatches(command, query) {
  if (!query) return true;
  const haystack = [
    command.root,
    command.category,
    command.description,
  ].map(value => String(value || '').toLowerCase()).join(' ');
  return haystack.includes(query);
}

function _commandRegistryFilteredCommands() {
  const query = commandRegistryQuery.trim().toLowerCase();
  return _commandRegistryCommands().filter(command => {
    const category = commandCatalogText(command.category, 'Allowed commands');
    if (commandRegistryCategory !== 'All' && category !== commandRegistryCategory) return false;
    return _commandRegistryMatches(command, query);
  });
}

function _commandRegistrySummaryText(command) {
  const bits = [];
  const examples = Number(command.example_count || 0);
  const subcommands = Number(command.subcommand_count || 0);
  const flags = Number(command.flag_count || 0);
  if (examples > 0) bits.push(`${examples} example${examples === 1 ? '' : 's'}`);
  if (subcommands > 0) bits.push(`${subcommands} subcommand${subcommands === 1 ? '' : 's'}`);
  if (flags > 0) bits.push(`${flags} flag${flags === 1 ? '' : 's'}`);
  return bits.join(' · ');
}

function renderCommandRegistryCategories() {
  const categoriesEl = _commandRegistryCategoriesEl();
  if (!categoriesEl) return;
  _bindCommandRegistryCategoryScrollers();
  categoriesEl.replaceChildren();
  let activeButton = null;
  _commandRegistryCategories().forEach(category => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'command-registry-category chip chip-action';
    button.dataset.commandRegistryCategory = category;
    button.textContent = category;
    button.setAttribute('aria-pressed', category === commandRegistryCategory ? 'true' : 'false');
    if (category === commandRegistryCategory) {
      button.classList.add('active');
      activeButton = button;
    }
    button.addEventListener('click', () => {
      commandRegistryCategory = category;
      renderCommandRegistry();
    });
    categoriesEl.appendChild(button);
  });
  _afterCommandRegistryCategoryPaint(() => {
    if (activeButton && typeof activeButton.scrollIntoView === 'function') {
      activeButton.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    }
    _updateCommandRegistryCategoryScrollers();
  });
}

function makeCommandRegistryRow(command) {
  const root = commandCatalogText(command.root);
  if (!root) return null;
  const row = document.createElement('button');
  row.type = 'button';
  row.className = 'command-registry-row';
  row.dataset.commandRegistryRoot = root;
  row.title = `View ${root} details`;

  const rootEl = document.createElement('span');
  rootEl.className = 'command-registry-root';
  rootEl.textContent = root;

  const text = document.createElement('span');
  text.className = 'command-registry-text';
  const desc = document.createElement('span');
  desc.className = 'command-registry-description';
  desc.textContent = commandCatalogText(command.description, 'No description is available yet.');
  const meta = document.createElement('span');
  meta.className = 'command-registry-meta';
  const summary = _commandRegistrySummaryText(command);
  meta.textContent = [
    commandCatalogText(command.category, 'Allowed commands'),
    summary,
  ].filter(Boolean).join(' · ');
  text.append(desc, meta);

  const chev = document.createElement('span');
  chev.className = 'command-registry-chev';
  chev.setAttribute('aria-hidden', 'true');
  chev.textContent = '›';

  row.append(rootEl, text, chev);
  const openDetails = () => openCommandCatalogModal(root);
  if (_commandRegistryBindPressable(row, {
      onActivate: openDetails,
      clearPressStyle: true,
    })) {
    return row;
  }
  {
    row.addEventListener('click', openDetails);
  }
  return row;
}

function makeCommandRegistryPipeSection(pipes) {
  if (!Array.isArray(pipes)) return null;
  const validPipes = pipes.filter(p => commandCatalogText(p?.root));
  if (!validPipes.length) return null;
  const section = document.createElement('section');
  section.className = 'command-catalog-section';
  const heading = document.createElement('div');
  heading.className = 'command-catalog-section-title';
  heading.textContent = 'App-native pipe helpers';
  const disclaimer = document.createElement('p');
  disclaimer.className = 'command-catalog-note';
  disclaimer.textContent = 'App-managed filters — not arbitrary shell pipelines.';
  const list = document.createElement('div');
  list.className = 'command-catalog-list';
  validPipes.forEach(pipe => {
    const row = makeCommandCatalogRow(
      String(pipe.root || '').trim(),
      String(pipe.description || '').trim(),
    );
    if (row) list.appendChild(row);
  });
  if (!list.childElementCount) return null;
  section.append(heading, disclaimer, list);
  return section;
}

function renderCommandRegistry() {
  const body = _commandRegistryBody();
  if (!body) return;
  const globalData = _commandRegistryGlobalData();
  if (globalData) {
    commandRegistryData = globalData;
  }
  renderCommandRegistryCategories();
  const total = _commandRegistryCommands().length;
  const subtitle = _commandRegistrySubtitleEl();
  if (subtitle) {
    subtitle.textContent = total
      ? `${total} supported command${total === 1 ? '' : 's'} from the command registry.`
      : 'Browse supported tools, examples, flags, and subcommands.';
  }
  body.replaceChildren();
  if (!commandRegistryData) {
    const loading = document.createElement('div');
    loading.className = 'command-registry-empty';
    loading.textContent = 'Loading command registry...';
    body.appendChild(loading);
    return;
  }
  const commands = _commandRegistryFilteredCommands();
  if (!commands.length) {
    const empty = document.createElement('div');
    empty.className = 'command-registry-empty';
    empty.textContent = total
      ? 'No commands match that search.'
      : 'No command registry entries are available right now.';
    body.appendChild(empty);
  } else {
    commands.forEach(command => {
      const row = makeCommandRegistryRow(command);
      if (row) body.appendChild(row);
    });
  }
  const pipeSection = makeCommandRegistryPipeSection(commandRegistryData?.pipe_helpers);
  if (pipeSection) body.appendChild(pipeSection);
}

function openCommandRegistry() {
  const overlay = _commandRegistryOverlay();
  const body = _commandRegistryBody();
  if (!overlay || !body) return;
  const close = (typeof importedCloseMajorOverlays === 'function' && importedCloseMajorOverlays)
    || COMMAND_REGISTRY_GLOBAL._closeMajorOverlays;
  if (typeof close === 'function') close();
  _commandRegistryBlurVisibleComposerInputIfMobile();
  renderCommandRegistry();
  showCommandRegistryOverlay();
  _commandRegistryMarkInteractionSurfaceReady('command-registry', overlay, document.getElementById('command-registry-modal'));
  const mobileMode = document.body && document.body.classList.contains('mobile-terminal-mode');
  const search = _commandRegistrySearch();
  if (!mobileMode && search) {
    window.setTimeout(() => search.focus(), 0);
  }
}

_commandRegistrySearch()?.addEventListener('input', () => {
  commandRegistryQuery = _commandRegistrySearch()?.value || '';
  renderCommandRegistry();
});

function showCommandCatalogOverlay() {
  const overlay = _commandCatalogOverlay();
  if (!overlay) return;
  overlay.classList.remove('u-hidden');
  overlay.classList.add('open');
  overlay.setAttribute('aria-hidden', 'false');
}

function hideCommandCatalogOverlay() {
  const overlay = _commandCatalogOverlay();
  if (!overlay) return;
  overlay.classList.add('u-hidden');
  overlay.classList.remove('open');
  overlay.setAttribute('aria-hidden', 'true');
}

function isCommandCatalogOverlayOpen() {
  const overlay = _commandCatalogOverlay();
  return !!(overlay && overlay.classList.contains('open'));
}

function closeCommandCatalogModal() {
  hideCommandCatalogOverlay();
  _commandRegistryRefocusComposerAfterAction({ defer: true });
}

function commandCatalogText(value, fallback = '') {
  return String(value || fallback || '').trim();
}

function activateCommandCatalogExample(value) {
  const command = commandCatalogText(value);
  if (!command) return;
  const next = `${command} `;
  if (typeof importedActivateFaqCommandChip === 'function') {
    importedActivateFaqCommandChip(command);
  }
  const mobileInput = document.getElementById('mobile-cmd');
  const desktopInput = document.getElementById('cmd');
  const visibleInput = typeof importedGetVisibleComposerInput === 'function'
    ? importedGetVisibleComposerInput()
    : null;
  const target = document.body?.classList?.contains('mobile-terminal-mode')
    ? (mobileInput || visibleInput || desktopInput)
    : (visibleInput || mobileInput || desktopInput);
  if (target && target.value !== next) {
    if (typeof importedSetComposerValue === 'function') {
      importedSetComposerValue(next, next.length, next.length, { dispatch: false });
    }
    target.value = next;
    if (typeof target.setSelectionRange === 'function') target.setSelectionRange(next.length, next.length);
  }
  if (mobileInput && mobileInput.value !== next) {
    mobileInput.value = next;
    if (typeof mobileInput.setSelectionRange === 'function') {
      mobileInput.setSelectionRange(next.length, next.length);
    }
  }
}

function appendCommandCatalogSection(body, title, items, rowBuilder) {
  if (!body || !Array.isArray(items) || !items.length) return;
  const section = document.createElement('section');
  section.className = 'command-catalog-section';
  const heading = document.createElement('div');
  heading.className = 'command-catalog-section-title';
  heading.textContent = title;
  section.appendChild(heading);
  const list = document.createElement('div');
  list.className = 'command-catalog-list';
  items.forEach(item => {
    const row = rowBuilder(item);
    if (row) list.appendChild(row);
  });
  if (!list.childElementCount) return;
  section.appendChild(list);
  body.appendChild(section);
}

function makeCommandCatalogRow(value, description = '') {
  const token = commandCatalogText(value);
  if (!token) return null;
  const row = document.createElement('div');
  row.className = 'command-catalog-row';
  const left = document.createElement('span');
  left.className = 'command-catalog-token';
  left.textContent = token;
  const right = document.createElement('span');
  right.className = 'command-catalog-note';
  right.textContent = commandCatalogText(description);
  row.append(left, right);
  return row;
}

function makeCommandCatalogExampleRow(item) {
  const value = commandCatalogText(item?.value);
  if (!value) return null;
  const row = document.createElement('div');
  row.className = 'command-catalog-row command-catalog-example-row';
  const chip = document.createElement('span');
  chip.className = 'allowed-chip faq-chip chip chip-action';
  chip.tabIndex = 0;
  chip.setAttribute('role', 'button');
  chip.title = 'Load this example into the prompt';
  chip.textContent = value;
  chip.dataset.commandExample = value;
  const activate = () => activateCommandCatalogExample(value);
  chip.addEventListener('click', activate);
  chip.addEventListener('keydown', e => {
    if (e.key !== 'Enter' && e.key !== ' ') return;
    e.preventDefault();
    activate();
  });
  chip.dataset.commandExampleWired = '1';
  const description = document.createElement('span');
  description.className = 'command-catalog-note';
  description.textContent = commandCatalogText(item?.description);
  row.append(chip, description);
  return row;
}

function commandCatalogHintText(item) {
  const bits = [];
  const valueType = commandCatalogText(item?.value_type);
  const wordlistCategory = item?.wordlist_category;
  if (valueType) bits.push(valueType);
  if (Array.isArray(wordlistCategory) && wordlistCategory.length) {
    bits.push(`wordlists: ${wordlistCategory.map(value => commandCatalogText(value)).filter(Boolean).join(', ')}`);
  } else if (wordlistCategory) {
    bits.push(`wordlist: ${commandCatalogText(wordlistCategory)}`);
  }
  return bits.join(' · ');
}

function makeCommandCatalogArgumentRow(item) {
  const value = commandCatalogText(item?.value);
  if (!value) return null;
  const description = [
    commandCatalogText(item?.description),
    commandCatalogHintText(item),
  ].filter(Boolean).join(' · ');
  return makeCommandCatalogRow(value, description);
}

function makeCommandCatalogFlagRow(item) {
  const value = commandCatalogText(item?.value);
  if (!value) return null;
  const hints = Array.isArray(item?.value_hints) ? item.value_hints : [];
  const hintText = hints
    .map(hint => commandCatalogText(hint?.value))
    .filter(Boolean)
    .join(', ');
  const suffix = item?.takes_value ? ` ${hintText || '<value>'}` : '';
  const description = [
    commandCatalogText(item?.description),
    hintText && item?.takes_value ? `values: ${hintText}` : '',
  ].filter(Boolean).join(' · ');
  return makeCommandCatalogRow(`${value}${suffix}`, description);
}

function makeCommandCatalogNoteRow(item) {
  return makeCommandCatalogRow(item, '');
}

function appendCommandCatalogSubcommand(body, root, item) {
  const name = commandCatalogText(item?.name);
  if (!body || !name) return;
  const section = document.createElement('section');
  section.className = 'command-catalog-section command-catalog-subcommand';

  const heading = document.createElement('div');
  heading.className = 'command-catalog-section-title';
  heading.textContent = `Subcommand: ${root ? `${root} ` : ''}${name}`;
  section.appendChild(heading);

  const description = commandCatalogText(item?.description);
  if (description) {
    const desc = document.createElement('div');
    desc.className = 'command-catalog-description';
    desc.textContent = description;
    section.appendChild(desc);
  }

  appendCommandCatalogSection(section, 'Examples', item?.examples || [], makeCommandCatalogExampleRow);
  appendCommandCatalogSection(section, 'Arguments', item?.arguments || [], makeCommandCatalogArgumentRow);
  appendCommandCatalogSection(section, 'Flags', item?.flags || [], makeCommandCatalogFlagRow);
  body.appendChild(section);
}

function wireCommandCatalogExamples(root = _commandCatalogBody()) {
  if (!root) return;
  root.querySelectorAll('[data-command-example]').forEach(chip => {
    if (chip.dataset.commandExampleWired === '1') return;
    chip.dataset.commandExampleWired = '1';
    const activate = () => activateCommandCatalogExample(chip.dataset.commandExample || '');
    chip.addEventListener('click', activate);
    chip.addEventListener('keydown', e => {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      e.preventDefault();
      activate();
    });
  });
}

function renderCommandCatalogModal(data) {
  const body = _commandCatalogBody();
  if (!body) return;
  body.replaceChildren();
  const rootLabel = [
    commandCatalogText(data?.root, 'command'),
    commandCatalogText(data?.subcommand),
  ].filter(Boolean).join(' ');
  const summary = document.createElement('section');
  summary.className = 'command-catalog-summary';
  const root = document.createElement('div');
  root.className = 'command-catalog-root';
  root.textContent = rootLabel;
  const description = document.createElement('div');
  description.className = 'command-catalog-description';
  description.textContent = commandCatalogText(data?.description, 'No description is available yet.');
  const meta = document.createElement('div');
  meta.className = 'command-catalog-meta';
  meta.textContent = commandCatalogText(data?.category, 'Allowed command');
  summary.append(root, description, meta);
  body.appendChild(summary);

  appendCommandCatalogSection(body, 'Examples', data?.examples || [], makeCommandCatalogExampleRow);
  appendCommandCatalogSection(body, 'Arguments', data?.arguments || [], makeCommandCatalogArgumentRow);
  (data?.subcommands || []).forEach(item => appendCommandCatalogSubcommand(body, data?.root, item));
  appendCommandCatalogSection(body, 'Flags', data?.flags || [], makeCommandCatalogFlagRow);
  appendCommandCatalogSection(body, 'Workspace File Flags', data?.workspace_flags || [], item => (
    makeCommandCatalogRow(item?.flag, [item?.mode, item?.value].map(value => commandCatalogText(value)).filter(Boolean).join(' · '))
  ));
  appendCommandCatalogSection(body, 'App Handling', data?.runtime_notes || [], makeCommandCatalogNoteRow);

  const knowledge = data?.knowledge || {};
  appendCommandCatalogSection(body, 'Notes', knowledge.notes || [], makeCommandCatalogNoteRow);
  appendCommandCatalogSection(body, 'Gotchas', knowledge.gotchas || [], makeCommandCatalogNoteRow);
  appendCommandCatalogSection(body, 'Safe Defaults', knowledge.safe_defaults || [], makeCommandCatalogNoteRow);
  appendCommandCatalogSection(body, 'Common Flags', knowledge.common_flags || [], makeCommandCatalogNoteRow);
  if (knowledge.artifact_behavior) {
    appendCommandCatalogSection(body, 'Artifact Behavior', [knowledge.artifact_behavior], makeCommandCatalogNoteRow);
  }

  wireCommandCatalogExamples(body);
}

async function openCommandCatalogModal(cmd) {
  const root = commandCatalogText(cmd).toLowerCase();
  const overlay = _commandCatalogOverlay();
  const body = _commandCatalogBody();
  if (!root || !overlay || !body) return;
  const title = document.getElementById('command-catalog-title');
  if (title) title.textContent = root.toUpperCase();
  body.textContent = 'Loading...';
  showCommandCatalogOverlay();
  try {
    const resp = await _commandRegistryApiFetch(`/commands/catalog/${encodeURIComponent(root)}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    renderCommandCatalogModal(await resp.json());
  } catch (err) {
    _commandRegistryClientError('failed to load command catalog details', err);
    body.textContent = 'Command details are unavailable right now.';
  }
}

if (typeof importedSetCommandRegistryHandlers === 'function') {
  importedSetCommandRegistryHandlers({
    openCommandRegistry,
    closeCommandRegistry,
    closeCommandCatalogModal,
    hideCommandCatalogOverlay,
    isCommandCatalogOverlayOpen,
    isCommandRegistryOverlayOpen,
    renderCommandRegistry,
  });
}

export {
  showCommandRegistryOverlay,
  hideCommandRegistryOverlay,
  isCommandRegistryOverlayOpen,
  closeCommandRegistry,
  renderCommandRegistry,
  openCommandRegistry,
  showCommandCatalogOverlay,
  hideCommandCatalogOverlay,
  closeCommandCatalogModal,
  isCommandCatalogOverlayOpen,
  wireCommandCatalogExamples,
  renderCommandCatalogModal,
  openCommandCatalogModal,
};
