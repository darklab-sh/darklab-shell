// darklab_shell Command Registry modal and command catalog helpers.

function _commandRegistryGlobalData() {
  if (typeof window !== 'undefined' && window.commandRegistryData) return window.commandRegistryData;
  if (typeof globalThis !== 'undefined' && globalThis.commandRegistryData) return globalThis.commandRegistryData;
  return null;
}

let commandRegistryData = _commandRegistryGlobalData();
let commandRegistryCategory = 'All';
let commandRegistryQuery = '';

function showCommandRegistryOverlay() {
  if (!commandRegistryOverlay) return;
  commandRegistryOverlay.classList.remove('u-hidden');
  commandRegistryOverlay.classList.add('open');
  commandRegistryOverlay.setAttribute('aria-hidden', 'false');
}

function hideCommandRegistryOverlay() {
  if (!commandRegistryOverlay) return;
  commandRegistryOverlay.classList.add('u-hidden');
  commandRegistryOverlay.classList.remove('open');
  commandRegistryOverlay.setAttribute('aria-hidden', 'true');
}

function isCommandRegistryOverlayOpen() {
  return !!(commandRegistryOverlay && commandRegistryOverlay.classList.contains('open'));
}

function closeCommandRegistry() {
  hideCommandRegistryOverlay();
  refocusComposerAfterAction({ defer: true });
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
  if (!commandRegistryCategories) return;
  commandRegistryCategories.replaceChildren();
  _commandRegistryCategories().forEach(category => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'command-registry-category chip chip-action';
    button.dataset.commandRegistryCategory = category;
    button.textContent = category;
    button.setAttribute('aria-pressed', category === commandRegistryCategory ? 'true' : 'false');
    if (category === commandRegistryCategory) button.classList.add('active');
    button.addEventListener('click', () => {
      commandRegistryCategory = category;
      renderCommandRegistry();
    });
    commandRegistryCategories.appendChild(button);
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
  if (typeof bindPressable === 'function') {
    bindPressable(row, {
      onActivate: openDetails,
      clearPressStyle: true,
    });
  } else {
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
  if (!commandRegistryBody) return;
  const globalData = _commandRegistryGlobalData();
  if (globalData) {
    commandRegistryData = globalData;
  }
  renderCommandRegistryCategories();
  const total = _commandRegistryCommands().length;
  if (commandRegistrySubtitle) {
    commandRegistrySubtitle.textContent = total
      ? `${total} supported command${total === 1 ? '' : 's'} from the command registry.`
      : 'Browse supported tools, examples, flags, and subcommands.';
  }
  commandRegistryBody.replaceChildren();
  if (!commandRegistryData) {
    const loading = document.createElement('div');
    loading.className = 'command-registry-empty';
    loading.textContent = 'Loading command registry...';
    commandRegistryBody.appendChild(loading);
    return;
  }
  const commands = _commandRegistryFilteredCommands();
  if (!commands.length) {
    const empty = document.createElement('div');
    empty.className = 'command-registry-empty';
    empty.textContent = total
      ? 'No commands match that search.'
      : 'No command registry entries are available right now.';
    commandRegistryBody.appendChild(empty);
  } else {
    commands.forEach(command => {
      const row = makeCommandRegistryRow(command);
      if (row) commandRegistryBody.appendChild(row);
    });
  }
  const pipeSection = makeCommandRegistryPipeSection(commandRegistryData?.pipe_helpers);
  if (pipeSection) commandRegistryBody.appendChild(pipeSection);
}

function openCommandRegistry() {
  if (!commandRegistryOverlay || !commandRegistryBody) return;
  _closeMajorOverlays();
  if (typeof blurVisibleComposerInputIfMobile === 'function') blurVisibleComposerInputIfMobile();
  renderCommandRegistry();
  showCommandRegistryOverlay();
  if (typeof markInteractionSurfaceReady === 'function') {
    markInteractionSurfaceReady('command-registry', commandRegistryOverlay, document.getElementById('command-registry-modal'));
  }
  const mobileMode = document.body && document.body.classList.contains('mobile-terminal-mode');
  if (!mobileMode && commandRegistrySearch) {
    window.setTimeout(() => commandRegistrySearch.focus(), 0);
  }
}

commandRegistrySearch?.addEventListener('input', () => {
  commandRegistryQuery = commandRegistrySearch.value || '';
  renderCommandRegistry();
});

function showCommandCatalogOverlay() {
  if (!commandCatalogOverlay) return;
  commandCatalogOverlay.classList.remove('u-hidden');
  commandCatalogOverlay.classList.add('open');
  commandCatalogOverlay.setAttribute('aria-hidden', 'false');
}

function hideCommandCatalogOverlay() {
  if (!commandCatalogOverlay) return;
  commandCatalogOverlay.classList.add('u-hidden');
  commandCatalogOverlay.classList.remove('open');
  commandCatalogOverlay.setAttribute('aria-hidden', 'true');
}

function isCommandCatalogOverlayOpen() {
  return !!(commandCatalogOverlay && commandCatalogOverlay.classList.contains('open'));
}

function closeCommandCatalogModal() {
  hideCommandCatalogOverlay();
  refocusComposerAfterAction({ defer: true });
}

function commandCatalogText(value, fallback = '') {
  return String(value || fallback || '').trim();
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

function wireCommandCatalogExamples(root = commandCatalogBody) {
  if (!root) return;
  root.querySelectorAll('[data-command-example]').forEach(chip => {
    if (chip.dataset.commandExampleWired === '1') return;
    chip.dataset.commandExampleWired = '1';
    const activate = () => {
      if (typeof window.activateFaqCommandChip === 'function') {
        window.activateFaqCommandChip(chip.dataset.commandExample || '');
      }
    };
    chip.addEventListener('click', activate);
    chip.addEventListener('keydown', e => {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      e.preventDefault();
      activate();
    });
  });
}

function renderCommandCatalogModal(data) {
  if (!commandCatalogBody) return;
  commandCatalogBody.replaceChildren();
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
  commandCatalogBody.appendChild(summary);

  appendCommandCatalogSection(commandCatalogBody, 'Examples', data?.examples || [], makeCommandCatalogExampleRow);
  appendCommandCatalogSection(commandCatalogBody, 'Arguments', data?.arguments || [], makeCommandCatalogArgumentRow);
  (data?.subcommands || []).forEach(item => appendCommandCatalogSubcommand(commandCatalogBody, data?.root, item));
  appendCommandCatalogSection(commandCatalogBody, 'Flags', data?.flags || [], makeCommandCatalogFlagRow);
  appendCommandCatalogSection(commandCatalogBody, 'Workspace File Flags', data?.workspace_flags || [], item => (
    makeCommandCatalogRow(item?.flag, [item?.mode, item?.value].map(value => commandCatalogText(value)).filter(Boolean).join(' · '))
  ));
  appendCommandCatalogSection(commandCatalogBody, 'App Handling', data?.runtime_notes || [], makeCommandCatalogNoteRow);

  const knowledge = data?.knowledge || {};
  appendCommandCatalogSection(commandCatalogBody, 'Notes', knowledge.notes || [], makeCommandCatalogNoteRow);
  appendCommandCatalogSection(commandCatalogBody, 'Gotchas', knowledge.gotchas || [], makeCommandCatalogNoteRow);
  appendCommandCatalogSection(commandCatalogBody, 'Safe Defaults', knowledge.safe_defaults || [], makeCommandCatalogNoteRow);
  appendCommandCatalogSection(commandCatalogBody, 'Common Flags', knowledge.common_flags || [], makeCommandCatalogNoteRow);
  if (knowledge.artifact_behavior) {
    appendCommandCatalogSection(commandCatalogBody, 'Artifact Behavior', [knowledge.artifact_behavior], makeCommandCatalogNoteRow);
  }

  wireCommandCatalogExamples(commandCatalogBody);
}

async function openCommandCatalogModal(cmd) {
  const root = commandCatalogText(cmd).toLowerCase();
  if (!root || !commandCatalogOverlay || !commandCatalogBody) return;
  const title = document.getElementById('command-catalog-title');
  if (title) title.textContent = root.toUpperCase();
  commandCatalogBody.textContent = 'Loading...';
  showCommandCatalogOverlay();
  try {
    const resp = await apiFetch(`/commands/catalog/${encodeURIComponent(root)}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    renderCommandCatalogModal(await resp.json());
  } catch (err) {
    logClientError('failed to load command catalog details', err);
    commandCatalogBody.textContent = 'Command details are unavailable right now.';
  }
}

window.showCommandRegistryOverlay = showCommandRegistryOverlay;
window.hideCommandRegistryOverlay = hideCommandRegistryOverlay;
window.isCommandRegistryOverlayOpen = isCommandRegistryOverlayOpen;
window.closeCommandRegistry = closeCommandRegistry;
window.renderCommandRegistry = renderCommandRegistry;
window.openCommandRegistry = openCommandRegistry;
window.showCommandCatalogOverlay = showCommandCatalogOverlay;
window.hideCommandCatalogOverlay = hideCommandCatalogOverlay;
window.closeCommandCatalogModal = closeCommandCatalogModal;
window.isCommandCatalogOverlayOpen = isCommandCatalogOverlayOpen;
window.wireCommandCatalogExamples = wireCommandCatalogExamples;
window.renderCommandCatalogModal = renderCommandCatalogModal;
window.openCommandCatalogModal = openCommandCatalogModal;
