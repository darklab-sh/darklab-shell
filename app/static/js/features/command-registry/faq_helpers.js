// FAQ and allowed-command helpers kept eager so boot-time FAQ rendering stays small.

var allowedCommandsFaqData = null;
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
        ? `<strong>${_fmtDuration(timeout)}</strong> - commands are automatically killed after this time; a notice appears inline in the output`
        : '<strong>None</strong> - commands run until they finish or you click Kill',
    },
    {
      label: 'Output line limit',
      value: maxLines > 0
        ? `<strong>${maxLines.toLocaleString()} lines</strong> per tab - older lines are dropped from the top when this is reached`
        : '<strong>Unlimited</strong>',
    },
    {
      label: 'Permalink & history retention',
      value: retention > 0
        ? `<strong>${retention} day${retention === 1 ? '' : 's'}</strong> - run history and share links are deleted after this period`
        : '<strong>Unlimited</strong> - run history and share links are kept indefinitely',
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

function wireCommandRegistryOpenButtons(root = document) {
  if (!root) return;
  root.querySelectorAll('[data-command-registry-open]').forEach(btn => {
    if (btn.dataset.commandRegistryOpenWired === '1') return;
    btn.dataset.commandRegistryOpenWired = '1';
    btn.addEventListener('click', () => {
      if (typeof openCommandRegistry === 'function') openCommandRegistry();
    });
  });
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
  allowedCommandsFaqData = data;
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
        a.textContent = 'Loading...';
      } else if (item.ui_kind === 'limits') {
        a.id = 'faq-limits-text';
        a.textContent = 'Loading...';
      } else if (item.answer_html) {
        a.innerHTML = item.answer_html;
      } else {
        a.textContent = item.answer || '';
      }

      q.setAttribute('role', 'button');
      q.setAttribute('tabindex', '0');
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
