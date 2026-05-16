// darklab_shell Command Registry and FAQ command helpers.

let allowedCommandsFaqData = null;
let commandRegistryData = null;
let commandRegistryCategory = 'All';
let commandRegistryQuery = '';
let faqHandleRegistry = [];
const FAQ_CATEGORY_ORDER = [
  'Getting started',
  'Core features',
  'Privacy & sessions',
  'Keyboard & controls',
  'Tool-specific behavior',
  'Limits & retention',
  'Other',
];
const FAQ_CATEGORY_OTHER = 'Other';

function faqSlug(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/&/g, ' and ')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'item';
}

function normalizeFaqCategory(category) {
  const text = String(category || '').trim();
  return FAQ_CATEGORY_ORDER.includes(text) ? text : FAQ_CATEGORY_OTHER;
}

function getFaqHashTarget() {
  const hash = String(window.location.hash || '').replace(/^#/, '');
  if (!hash) return null;
  const params = new URLSearchParams(hash);
  const question = params.get('faq');
  const section = params.get('faq-section');
  if (question) return { kind: 'question', slug: question };
  if (section) return { kind: 'section', slug: section };
  return null;
}

function replaceFaqHash(kind, slug) {
  if (!window.history || typeof window.history.replaceState !== 'function') return;
  const base = `${window.location.pathname}${window.location.search}`;
  window.history.replaceState(null, '', `${base}#${kind}=${encodeURIComponent(slug)}`);
}

function clearFaqHash() {
  const target = getFaqHashTarget();
  if (!target || !window.history || typeof window.history.replaceState !== 'function') return;
  window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}`);
}

function applyFaqHashTarget() {
  if (!faqBody) return false;
  const target = getFaqHashTarget();
  if (!target) return false;
  if (target.kind === 'question') {
    const matched = faqHandleRegistry.find(handle => handle.panel.dataset.faqQuestion === target.slug);
    if (!matched) return false;
    matched.open();
    if (typeof matched.panel.scrollIntoView === 'function') matched.panel.scrollIntoView({ block: 'start' });
    return true;
  }
  if (target.kind === 'section') {
    const section = [...faqBody.querySelectorAll('[data-faq-section]')]
      .find(el => el.dataset.faqSection === target.slug);
    if (!section) return false;
    if (typeof section.scrollIntoView === 'function') section.scrollIntoView({ block: 'start' });
    return true;
  }
  return false;
}

function _buildFaqLimitsContent(cfg) {
  if (!cfg) return '';
  function _fmtDuration(s) {
    if (s >= 3600 && s % 3600 === 0) return (s / 3600) + (s / 3600 === 1 ? ' hour' : ' hours');
    if (s >= 60 && s % 60 === 0) return (s / 60) + (s / 60 === 1 ? ' minute' : ' minutes');
    return s + (s === 1 ? ' second' : ' seconds');
  }
  const timeout = cfg.command_timeout_seconds || 0;
  const maxLines = cfg.max_output_lines || 0;
  const retention = cfg.permalink_retention_days || 0;

  const rows = [
    {
      label: 'Command timeout',
      value: timeout > 0
        ? `<strong>${_fmtDuration(timeout)}</strong> — commands are automatically killed after this time; a notice appears inline in the output`
        : '<strong>None</strong> — commands run until they finish or you click ■ Kill',
    },
    {
      label: 'Output line limit',
      value: maxLines > 0
        ? `<strong>${maxLines.toLocaleString()} lines</strong> per tab — older lines are dropped from the top when this is reached`
        : '<strong>Unlimited</strong>',
    },
    {
      label: 'Permalink & history retention',
      value: retention > 0
        ? `<strong>${retention} day${retention === 1 ? '' : 's'}</strong> — run history and share links are deleted after this period`
        : '<strong>Unlimited</strong> — run history and share links are kept indefinitely',
    },
  ];

  const frag = document.createDocumentFragment();
  const list = document.createElement('div');
  list.className = 'faq-limits-list';
  rows.forEach(r => {
    const row = document.createElement('div');
    row.className = 'faq-limits-row';

    const labelEl = document.createElement('div');
    labelEl.className = 'faq-limits-label';
    labelEl.textContent = r.label;

    const valueEl = document.createElement('div');
    valueEl.className = 'faq-limits-value';
    valueEl.innerHTML = r.value;

    row.appendChild(labelEl);
    row.appendChild(valueEl);
    list.appendChild(row);
  });
  frag.appendChild(list);
  return frag;
}

function renderFaqLimits(cfg) {
  const limitsEl = document.getElementById('faq-limits-text');
  if (!limitsEl || !cfg) return;
  limitsEl.replaceChildren(_buildFaqLimitsContent(cfg));
}

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
  row.addEventListener('click', () => openCommandCatalogModal(root));
  return row;
}

function renderCommandRegistry() {
  if (!commandRegistryBody) return;
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
    return;
  }
  commands.forEach(command => {
    const row = makeCommandRegistryRow(command);
    if (row) commandRegistryBody.appendChild(row);
  });
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

function wireCommandRegistryOpenButtons(root = document) {
  if (!root) return;
  root.querySelectorAll('[data-command-registry-open]').forEach(btn => {
    if (btn.dataset.commandRegistryOpenWired === '1') return;
    btn.dataset.commandRegistryOpenWired = '1';
    btn.addEventListener('click', () => openCommandRegistry());
  });
}

commandRegistrySearch?.addEventListener('input', () => {
  commandRegistryQuery = commandRegistrySearch.value || '';
  renderCommandRegistry();
});

function openAutocompleteForVisibleComposer() {
  if (typeof isActiveTabRunning === 'function' && isActiveTabRunning()) {
    if (typeof acHide === 'function') acHide();
    return false;
  }
  const input = typeof getVisibleComposerInput === 'function' ? getVisibleComposerInput() : null;
  if (!input || typeof input.value !== 'string') return false;
  const value = input.value;
  const cursor = typeof input.selectionStart === 'number' ? input.selectionStart : value.length;
  if (!value.trim() || typeof getAutocompleteMatches !== 'function') return false;
  const matches = getAutocompleteMatches(value, cursor);
  acFiltered = typeof limitAutocompleteMatchesForDisplay === 'function'
    ? limitAutocompleteMatchesForDisplay(matches, 12)
    : matches.slice(0, 12);
  acIndex = -1;
  if (!acFiltered.length) {
    if (typeof acHide === 'function') acHide();
    return false;
  }
  if (typeof acShow === 'function') acShow(acFiltered);
  return true;
}

function activateFaqCommandChip(cmd) {
  if (!cmd) return;
  if (typeof isActiveTabRunning === 'function' && isActiveTabRunning()) {
    if (typeof acHide === 'function') acHide();
    return;
  }
  const next = `${cmd} `;
  setComposerValue(next, next.length, next.length, { dispatch: false });
  _closeMajorOverlays();
  refocusComposerAfterAction({ defer: true });
  setTimeout(() => {
    openAutocompleteForVisibleComposer();
  }, 0);
}
if (typeof globalThis !== 'undefined') globalThis.activateFaqCommandChip = activateFaqCommandChip;

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
    const activate = () => activateFaqCommandChip(chip.dataset.commandExample || '');
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

function wireFaqCommandChips(root = faqBody) {
  if (!root) return;
  root.querySelectorAll('.faq-chip[data-faq-command]').forEach(chip => {
    if (chip.dataset.faqWired === '1') return;
    chip.dataset.faqWired = '1';
    chip.addEventListener('click', () => {
      activateFaqCommandChip(chip.dataset.faqCommand || '');
    });
    chip.addEventListener('keydown', e => {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      e.preventDefault();
      activateFaqCommandChip(chip.dataset.faqCommand || '');
    });
  });
}

function shouldShowVisualTourFaqLink() {
  if (!(APP_CONFIG && APP_CONFIG.tour_enabled === true)) return false;
  if (typeof useMobileTerminalViewportMode === 'function' && useMobileTerminalViewportMode()) return false;
  const chapters = Array.isArray(APP_CONFIG.tour_chapters) ? APP_CONFIG.tour_chapters : [];
  return chapters.some(chapter => chapter && typeof chapter === 'object');
}

function appendVisualTourFaqLink() {
  if (!faqBody || !shouldShowVisualTourFaqLink()) return null;
  const item = document.createElement('div');
  item.className = 'faq-tour-entry';

  const title = document.createElement('div');
  title.className = 'faq-tour-entry-title';
  title.textContent = 'Tour the app';

  const body = document.createElement('div');
  body.className = 'faq-tour-entry-body';
  const copy = document.createElement('span');
  copy.textContent = 'Open a quick visual walkthrough of the shell, history, projects, workflows, and other core features.';
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'btn btn-secondary btn-compact faq-tour-open';
  button.textContent = 'Open visual tour';
  button.setAttribute('aria-label', 'Open the visual tour');
  const activate = () => {
    if (typeof openTourModal === 'function') {
      const opened = openTourModal({ source: 'faq' });
      if (opened && typeof isFaqOverlayOpen === 'function' && isFaqOverlayOpen()) {
        clearFaqHash();
        hideFaqOverlay();
      }
    }
  };
  if (typeof bindPressable === 'function') {
    bindPressable(button, {
      refocusComposer: false,
      clearPressStyle: true,
      onActivate: activate,
    });
  } else {
    button.addEventListener('click', activate);
  }
  body.append(copy, button);
  item.append(title, body);
  faqBody.prepend(item);
  return item;
}

function renderAllowedCommandsFaq(data) {
  const el = document.getElementById('faq-allowed-text');
  if (!el || !data) return;
  el.replaceChildren();
  const intro = document.createElement('div');
  intro.className = 'allowed-intro';
  const count = Array.isArray(data.commands) ? data.commands.length : 0;
  intro.textContent = count
    ? `Open the Command Registry to browse ${count} supported command${count === 1 ? '' : 's'}, examples, flags, and subcommands.`
    : 'Open the Command Registry to browse supported commands, examples, flags, and subcommands.';
  el.appendChild(intro);
  const actions = document.createElement('div');
  actions.className = 'allowed-actions';
  const openBtn = document.createElement('button');
  openBtn.type = 'button';
  openBtn.className = 'btn btn-secondary btn-compact';
  openBtn.textContent = 'Open Command Registry';
  openBtn.dataset.commandRegistryOpen = '1';
  actions.appendChild(openBtn);
  const cliHint = document.createElement('span');
  cliHint.className = 'allowed-cli-hint';
  cliHint.textContent = 'Terminal helpers: commands, commands --external, commands info <command>';
  actions.appendChild(cliHint);
  el.appendChild(actions);
  wireCommandRegistryOpenButtons(el);
}

function renderFaqItems(items) {
  // FAQ content is backend-driven so operators can extend it, but chips and
  // special UI sections are still wired client-side after the HTML is inserted.
  if (!faqBody) return;
  faqBody.innerHTML = '';
  const faqHandles = [];
  const grouped = new Map(FAQ_CATEGORY_ORDER.map(category => [category, []]));
  (items || []).forEach(item => {
    if (!item || typeof item !== 'object') return;
    const category = normalizeFaqCategory(item && item.category);
    grouped.get(category).push(item);
  });

  FAQ_CATEGORY_ORDER.forEach(category => {
    const sectionItems = grouped.get(category) || [];
    if (!sectionItems.length) return;

    const section = document.createElement('section');
    section.className = 'faq-section';
    section.id = `faq-section-${faqSlug(category)}`;
    section.dataset.faqSection = faqSlug(category);

    const header = document.createElement('div');
    header.className = 'faq-section-header';
    header.textContent = category;
    header.setAttribute('tabindex', '-1');
    section.appendChild(header);

    sectionItems.forEach(item => {
      const div = document.createElement('div');
      div.className = 'faq-item';
      const questionSlug = faqSlug(item.question);
      div.id = `faq-${questionSlug}`;
      div.dataset.faqQuestion = questionSlug;

      const q = document.createElement('div');
      q.className = 'faq-q';
      q.textContent = item.question || '';

      const a = document.createElement('div');
      a.className = 'faq-a';
      if (item.ui_kind === 'allowed_commands') {
        a.id = 'faq-allowed-text';
        a.textContent = 'Loading…';
      } else if (item.ui_kind === 'limits') {
        a.id = 'faq-limits-text';
        a.textContent = 'Loading…';
      } else if (item.answer_html) {
        a.innerHTML = item.answer_html;
      } else {
        a.textContent = item.answer || '';
      }

      q.setAttribute('role', 'button');
      q.setAttribute('tabindex', '0');
      // FAQ question is a disclosure trigger. role="button" divs never receive
      // DOM focus from click, so the pressable's blur is a no-op — the
      // disclosure helper inherits clearPressStyle to punch through sticky
      // :hover highlights.
      const handle = bindDisclosure(q, {
        panel: div,
        openClass: 'faq-open',
        clearPressStyle: true,
        onToggle: (open) => {
          if (open && typeof isFaqOverlayOpen === 'function' && isFaqOverlayOpen()) {
            replaceFaqHash('faq', questionSlug);
          }
        },
      });
      if (handle) faqHandles.push({ ...handle, panel: div });

      div.appendChild(q);
      div.appendChild(a);
      section.appendChild(div);
    });
    faqBody.appendChild(section);
  });

  faqHandleRegistry = faqHandles;
  const openedFromHash = applyFaqHashTarget();
  if (!openedFromHash && faqHandles[0]) faqHandles[0].open();

  appendVisualTourFaqLink();
  renderAllowedCommandsFaq(allowedCommandsFaqData);
  renderFaqLimits(APP_CONFIG);
  wireFaqCommandChips(faqBody);
}
