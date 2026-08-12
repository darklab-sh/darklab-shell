// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Durable workflow definition editor.
import { bindPressable } from '../../ui/ui_pressable.js';
import { syncAppSelect as importedSyncAppSelect } from '../../ui/ui_helpers.js';

const WORKFLOW_INPUT_TYPES = [
  ['text', 'Text'],
  ['target', 'Target'],
  ['domain', 'Domain'],
  ['host', 'Host'],
  ['url', 'URL'],
  ['port', 'Port'],
  ['port_set', 'Port set'],
  ['workspace_path', 'Files path'],
  ['wordlist', 'Wordlist'],
];
const WORKFLOW_CAPTURE_SOURCES = [
  ['first_nonempty_line', 'First non-empty line'],
  ['first_line_containing', 'First line containing'],
  ['entity', 'First structured entity'],
  ['json_pointer', 'JSON Pointer'],
];
const WORKFLOW_CAPTURE_KINDS = [
  ['scalar', 'Single value'],
  ['collection', 'Collection'],
];
const WORKFLOW_FANOUT_FAILURE_MODES = [
  ['fail_fast', 'Stop after first failure'],
  ['continue', 'Continue within failure limit'],
];
const WORKFLOW_COLLECTION_ITEM_LIMIT = 32;
const WORKFLOW_FANOUT_LIMITS = {
  retries: [0, 3],
  maxParallel: [1, 8],
  maxFailures: [0, 32],
};

function editorRefs() {
  return {
    overlay: document.getElementById('workflow-editor-overlay'),
    form: document.getElementById('workflow-editor-form'),
    title: document.getElementById('workflow-editor-title'),
    titleInput: document.getElementById('workflow-editor-title-input'),
    descriptionInput: document.getElementById('workflow-editor-description-input'),
    parameters: document.getElementById('workflow-editor-parameters'),
    steps: document.getElementById('workflow-editor-steps'),
    msg: document.getElementById('workflow-editor-msg'),
    saveBtn: document.getElementById('workflow-editor-save-btn'),
  };
}

function textInput(className, value = '', placeholder = '', maxLength = 120) {
  const input = document.createElement('input');
  input.className = `form-control ${className}`;
  input.type = 'text';
  input.autocomplete = 'off';
  input.autocapitalize = 'none';
  input.autocorrect = 'off';
  input.spellcheck = false;
  input.inputMode = 'text';
  input.value = String(value || '');
  input.placeholder = placeholder;
  input.maxLength = maxLength;
  return input;
}

function numberInput(className, value, min, max) {
  const input = document.createElement('input');
  input.className = `form-control ${className}`;
  input.type = 'number';
  input.inputMode = 'numeric';
  input.min = String(min);
  input.max = String(max);
  input.step = '1';
  input.value = String(value);
  return input;
}

function optionSelect(className, label, options, value) {
  const select = document.createElement('select');
  select.className = `form-select ${className}`;
  select.setAttribute('aria-label', label);
  options.forEach(([optionValue, optionLabel]) => addTransitionOption(
    select,
    optionValue,
    optionLabel,
  ));
  select.value = String(value || options[0]?.[0] || '');
  return select;
}

function field(labelText, control, path, { wide = false } = {}) {
  const label = document.createElement('label');
  label.className = `workflow-editor-field${wide ? ' is-wide' : ''}`;
  label.dataset.workflowField = path;
  const labelEl = document.createElement('span');
  labelEl.className = 'workflow-input-label';
  labelEl.textContent = labelText;
  const error = document.createElement('span');
  error.className = 'form-error u-hidden';
  error.setAttribute('aria-live', 'polite');
  label.append(labelEl, control, error);
  return label;
}

function iconButton(symbol, label, className, onActivate) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = `btn btn-ghost btn-icon-only btn-compact ${className}`;
  button.textContent = symbol;
  button.title = label;
  button.setAttribute('aria-label', label);
  bindPressable(button, { onActivate, refocusComposer: false });
  return button;
}

function stepRows() {
  return [...(editorRefs().steps?.querySelectorAll('[data-workflow-editor-step]') || [])];
}

function parameterRows() {
  return [...(editorRefs().parameters?.querySelectorAll('[data-workflow-editor-parameter]') || [])];
}

function createInputTypeSelect(value) {
  const select = document.createElement('select');
  select.className = 'form-select workflow-editor-parameter-type';
  select.setAttribute('aria-label', 'Parameter type');
  WORKFLOW_INPUT_TYPES.forEach(([type, label]) => {
    const option = document.createElement('option');
    option.value = type;
    option.textContent = label;
    select.appendChild(option);
  });
  select.value = value === 'path' ? 'workspace_path' : String(value || 'text');
  return select;
}

function createRequiredControl(required) {
  const label = document.createElement('label');
  label.className = 'form-check workflow-editor-required';
  const input = document.createElement('input');
  input.className = 'workflow-editor-parameter-required';
  input.type = 'checkbox';
  input.checked = !!required;
  const text = document.createElement('span');
  text.textContent = 'Required';
  label.append(input, text);
  return label;
}

function createSensitiveControl(sensitive) {
  const label = document.createElement('label');
  label.className = 'form-check workflow-editor-sensitive';
  const input = document.createElement('input');
  input.className = 'workflow-editor-parameter-sensitive';
  input.type = 'checkbox';
  input.checked = !!sensitive;
  const text = document.createElement('span');
  text.textContent = 'Sensitive value';
  label.append(input, text);
  return label;
}

function createParameterRow(input = {}, index = 0, callbacks = {}) {
  const row = document.createElement('div');
  row.className = 'workflow-editor-parameter panel-row';
  row.dataset.workflowEditorParameter = '1';

  const header = document.createElement('div');
  header.className = 'workflow-editor-item-header';
  const title = document.createElement('span');
  title.className = 'workflow-editor-item-title';
  title.textContent = `Parameter ${index + 1}`;
  const actions = document.createElement('div');
  actions.className = 'workflow-editor-item-actions';
  actions.append(
    iconButton('↑', 'Move parameter up', 'workflow-editor-move-up', () => callbacks.move?.(row, -1)),
    iconButton('↓', 'Move parameter down', 'workflow-editor-move-down', () => callbacks.move?.(row, 1)),
    iconButton('×', 'Remove parameter', 'workflow-editor-remove-parameter', () => callbacks.remove?.(row)),
  );
  header.append(title, actions);

  const fields = document.createElement('div');
  fields.className = 'workflow-editor-parameter-fields';
  fields.append(
    field('ID', textInput('workflow-editor-parameter-id', input.id, 'target', 64), `inputs.${index}.id`),
    field('Label', textInput('workflow-editor-parameter-label', input.label, 'Target', 120), `inputs.${index}.label`),
    field('Type', createInputTypeSelect(input.type), `inputs.${index}.type`),
    field('Default', textInput('workflow-editor-parameter-default', input.default, 'Optional', 4096), `inputs.${index}.default`),
    field('Placeholder', textInput('workflow-editor-parameter-placeholder', input.placeholder, 'Shown when empty', 240), `inputs.${index}.placeholder`),
    field('Help', textInput('workflow-editor-parameter-help', input.help, 'Optional guidance', 500), `inputs.${index}.help`, { wide: true }),
  );
  const options = document.createElement('div');
  options.className = 'workflow-editor-parameter-options';
  options.dataset.workflowField = `inputs.${index}.sensitive`;
  const optionsError = document.createElement('span');
  optionsError.className = 'form-error u-hidden';
  optionsError.setAttribute('aria-live', 'polite');
  options.append(
    createRequiredControl(input.required),
    createSensitiveControl(input.sensitive),
    optionsError,
  );
  row.append(header, fields, options);
  return row;
}

function transitionSelect(className, label) {
  const select = document.createElement('select');
  select.className = `form-select ${className}`;
  select.setAttribute('aria-label', label);
  return select;
}

function captureRows(stepRow) {
  return [...(stepRow?.querySelectorAll('[data-workflow-editor-capture]') || [])];
}

function exitCodeRows(stepRow) {
  return [...(stepRow?.querySelectorAll('[data-workflow-editor-exit-code]') || [])];
}

function createCaptureSourceSelect(value) {
  const select = document.createElement('select');
  select.className = 'form-select workflow-editor-capture-source';
  select.setAttribute('aria-label', 'Capture selector');
  WORKFLOW_CAPTURE_SOURCES.forEach(([source, label]) => addTransitionOption(select, source, label));
  select.value = String(value || 'first_nonempty_line');
  return select;
}

function updateCaptureKind(row) {
  const kind = row.querySelector('.workflow-editor-capture-kind')?.value || 'scalar';
  const limitField = row.querySelector('.workflow-editor-capture-limit-field');
  if (limitField) limitField.hidden = kind !== 'collection';
  row.classList.toggle('is-collection', kind === 'collection');
  refreshCollectionOptions();
}

function captureOption(source) {
  if (source === 'first_line_containing') {
    return { field: 'contains', label: 'Contains', placeholder: 'Literal text' };
  }
  if (source === 'entity') {
    return { field: 'entity_type', label: 'Entity type', placeholder: 'domain' };
  }
  if (source === 'json_pointer') {
    return { field: 'pointer', label: 'JSON Pointer', placeholder: '/result/value' };
  }
  return null;
}

function updateCaptureOption(row, stepIndex, captureIndex) {
  const stepRow = row.closest('[data-workflow-editor-step]');
  const currentStepIndex = stepRows().indexOf(stepRow);
  const currentCaptureIndex = captureRows(stepRow).indexOf(row);
  if (currentStepIndex >= 0) stepIndex = currentStepIndex;
  if (currentCaptureIndex >= 0) captureIndex = currentCaptureIndex;
  const source = row.querySelector('.workflow-editor-capture-source')?.value || 'first_nonempty_line';
  const option = captureOption(source);
  const host = row.querySelector('.workflow-editor-capture-option-host');
  if (!host) return;
  const previousInput = host.querySelector('.workflow-editor-capture-option');
  if (previousInput?.dataset.captureOptionField) {
    row._workflowOptionValues[previousInput.dataset.captureOptionField] = previousInput.value;
  }
  host.innerHTML = '';
  if (!option) return;
  const input = textInput(
    'workflow-editor-capture-option',
    row._workflowOptionValues[option.field] || '',
    option.placeholder,
    500,
  );
  input.dataset.captureOptionField = option.field;
  host.appendChild(field(
    option.label,
    input,
    `steps.${stepIndex}.captures.${captureIndex}.${option.field}`,
  ));
}

function createCaptureRow(capture = {}, stepIndex = 0, captureIndex = 0, onRemove = null) {
  const row = document.createElement('div');
  row.className = 'workflow-editor-capture';
  row.dataset.workflowEditorCapture = '1';
  row._workflowOptionValues = {
    contains: String(capture.contains || ''),
    entity_type: String(capture.entity_type || ''),
    pointer: String(capture.pointer || ''),
  };

  const header = document.createElement('div');
  header.className = 'workflow-editor-item-header';
  const title = document.createElement('span');
  title.className = 'workflow-editor-capture-title';
  title.textContent = `Capture ${captureIndex + 1}`;
  header.append(
    title,
    iconButton('×', 'Remove output capture', 'workflow-editor-remove-capture', () => onRemove?.(row)),
  );

  const nameInput = textInput('workflow-editor-capture-name', capture.name, 'resolved_ip', 64);
  const sourceSelect = createCaptureSourceSelect(capture.source);
  const kindSelect = optionSelect(
    'workflow-editor-capture-kind',
    'Capture value shape',
    WORKFLOW_CAPTURE_KINDS,
    capture.kind === 'collection' || capture.mode === 'collection' ? 'collection' : 'scalar',
  );
  const limitInput = numberInput(
    'workflow-editor-capture-item-limit',
    capture.item_limit || WORKFLOW_COLLECTION_ITEM_LIMIT,
    1,
    WORKFLOW_COLLECTION_ITEM_LIMIT,
  );
  const limitField = field(
    'Item limit',
    limitInput,
    `steps.${stepIndex}.captures.${captureIndex}.item_limit`,
  );
  limitField.classList.add('workflow-editor-capture-limit-field');
  const optionHost = document.createElement('div');
  optionHost.className = 'workflow-editor-capture-option-host';
  const destination = document.createElement('div');
  destination.className = 'workflow-editor-capture-destination';
  const destinationLabel = document.createElement('span');
  destinationLabel.textContent = 'Available to later steps as';
  const destinationValue = document.createElement('code');
  const updateDestination = () => {
    destinationValue.textContent = `{{${String(nameInput.value || 'capture').trim() || 'capture'}}}`;
  };
  nameInput.addEventListener('input', updateDestination);
  nameInput.addEventListener('input', refreshCollectionOptions);
  updateDestination();
  destination.append(destinationLabel, destinationValue);

  const required = createRequiredControl(capture.required);
  required.classList.add('workflow-editor-capture-required');
  required.querySelector('input').className = 'workflow-editor-capture-required-input';
  row.append(
    header,
    field('Name', nameInput, `steps.${stepIndex}.captures.${captureIndex}.name`),
    field('Selector', sourceSelect, `steps.${stepIndex}.captures.${captureIndex}.source`),
    field('Value', kindSelect, `steps.${stepIndex}.captures.${captureIndex}.kind`),
    limitField,
    optionHost,
    required,
    destination,
  );
  sourceSelect.addEventListener('change', () => updateCaptureOption(row, stepIndex, captureIndex));
  kindSelect.addEventListener('change', () => updateCaptureKind(row));
  updateCaptureOption(row, stepIndex, captureIndex);
  updateCaptureKind(row);
  return row;
}

function createCaptureSection(step, stepIndex) {
  const section = document.createElement('section');
  section.className = 'workflow-editor-captures';
  section.dataset.workflowField = `steps.${stepIndex}.captures`;
  const header = document.createElement('div');
  header.className = 'workflow-editor-section-header';
  const title = document.createElement('span');
  title.className = 'workflow-editor-subsection-title';
  title.textContent = 'Capture output';
  const addButton = document.createElement('button');
  addButton.type = 'button';
  addButton.className = 'btn btn-ghost btn-compact workflow-editor-add-capture';
  addButton.textContent = '+ Capture';
  header.append(title, addButton);
  const list = document.createElement('div');
  list.className = 'workflow-editor-capture-list';
  const sectionError = document.createElement('span');
  sectionError.className = 'form-error u-hidden';
  sectionError.setAttribute('aria-live', 'polite');
  section.append(header, list, sectionError);

  const refreshCaptures = () => {
    const currentStepIndex = stepRows().indexOf(section.closest('[data-workflow-editor-step]'));
    captureRows(section).forEach((row, index) => {
      row.querySelector('.workflow-editor-capture-title').textContent = `Capture ${index + 1}`;
      row.querySelectorAll('[data-workflow-field]').forEach((node) => {
        node.dataset.workflowField = node.dataset.workflowField
          .replace(/^steps\.\d+/, `steps.${currentStepIndex >= 0 ? currentStepIndex : stepIndex}`)
          .replace(/captures\.\d+/, `captures.${index}`);
      });
    });
  };
  const addCapture = (capture = {}) => {
    const row = createCaptureRow(capture, stepIndex, captureRows(section).length, (target) => {
      target.remove();
      refreshCaptures();
      refreshCollectionOptions();
    });
    list.appendChild(row);
    refreshCaptures();
    refreshCollectionOptions();
  };
  bindPressable(addButton, { onActivate: () => addCapture(), refocusComposer: false });
  (Array.isArray(step.captures) ? step.captures : []).forEach(addCapture);
  return section;
}

function addTransitionOption(select, value, label) {
  const option = document.createElement('option');
  option.value = value;
  option.textContent = label;
  select.appendChild(option);
}

function createExitCodeRow(route = {}, stepIndex = 0, routeIndex = 0, onRemove = null) {
  const row = document.createElement('div');
  row.className = 'workflow-editor-exit-code-route';
  row.dataset.workflowEditorExitCode = '1';

  const header = document.createElement('div');
  header.className = 'workflow-editor-item-header';
  const title = document.createElement('span');
  title.className = 'workflow-editor-exit-code-title';
  title.textContent = `Route ${routeIndex + 1}`;
  header.append(
    title,
    iconButton('×', 'Remove exact exit-code route', 'workflow-editor-remove-exit-code', () => onRemove?.(row)),
  );

  const codeInput = textInput('workflow-editor-exit-code', route.code, '1', 12);
  codeInput.inputMode = 'numeric';
  codeInput.setAttribute('aria-label', 'Exit code');
  const destination = transitionSelect(
    'workflow-editor-exit-code-destination',
    'Exact exit-code destination',
  );
  destination.dataset.initialValue = String(route.destination || '__next__');
  destination.addEventListener('change', () => {
    destination.classList.remove('has-missing-destination');
  });
  row.append(
    header,
    field('Exit code', codeInput, `steps.${stepIndex}.next.codes.${routeIndex}.code`),
    field('Go to', destination, `steps.${stepIndex}.next.codes.${routeIndex}.destination`),
  );
  return row;
}

function createExitCodeSection(step, stepIndex) {
  const section = document.createElement('section');
  section.className = 'workflow-editor-code-routes';
  section.dataset.workflowField = `steps.${stepIndex}.next.codes`;
  const header = document.createElement('div');
  header.className = 'workflow-editor-section-header';
  const title = document.createElement('span');
  title.className = 'workflow-editor-subsection-title';
  title.textContent = 'Exact exit codes';
  const addButton = document.createElement('button');
  addButton.type = 'button';
  addButton.className = 'btn btn-ghost btn-compact workflow-editor-add-exit-code';
  addButton.textContent = '+ Route';
  header.append(title, addButton);
  const hint = document.createElement('span');
  hint.className = 'workflow-editor-route-hint';
  hint.textContent = 'Checked before the success or failure route.';
  const sectionError = document.createElement('span');
  sectionError.className = 'form-error u-hidden';
  sectionError.setAttribute('aria-live', 'polite');
  const list = document.createElement('div');
  list.className = 'workflow-editor-exit-code-list';
  section.append(header, hint, sectionError, list);

  const refreshRoutes = () => {
    const stepRow = section.closest('[data-workflow-editor-step]');
    const currentStepIndex = stepRows().indexOf(stepRow);
    exitCodeRows(section).forEach((row, index) => {
      row.querySelector('.workflow-editor-exit-code-title').textContent = `Route ${index + 1}`;
      row.querySelectorAll('[data-workflow-field]').forEach((node) => {
        node.dataset.workflowField = node.dataset.workflowField
          .replace(/^steps\.\d+/, `steps.${currentStepIndex >= 0 ? currentStepIndex : stepIndex}`)
          .replace(/codes\.\d+/, `codes.${index}`);
      });
    });
  };
  const addRoute = (route = {}) => {
    const row = createExitCodeRow(route, stepIndex, exitCodeRows(section).length, (target) => {
      target.remove();
      refreshRoutes();
      clearErrors();
    });
    list.appendChild(row);
    refreshRoutes();
    refreshTransitionOptions();
  };
  bindPressable(addButton, { onActivate: () => addRoute(), refocusComposer: false });
  const rawCodes = step.next?.codes;
  if (rawCodes && typeof rawCodes === 'object' && !Array.isArray(rawCodes)) {
    Object.entries(rawCodes).forEach(([code, destination]) => addRoute({ code, destination }));
  }
  return section;
}

function priorCollectionNames(stepRow) {
  const names = [];
  for (const row of stepRows()) {
    if (row === stepRow) break;
    captureRows(row).forEach((captureRow) => {
      if (captureRow.querySelector('.workflow-editor-capture-kind')?.value !== 'collection') return;
      const name = String(
        captureRow.querySelector('.workflow-editor-capture-name')?.value || '',
      ).trim();
      if (name && !names.includes(name)) names.push(name);
    });
  }
  return names;
}

function refreshFanoutCollectionSelect(stepRow) {
  const select = stepRow.querySelector('.workflow-editor-fanout-collection');
  if (!select) return;
  const previous = select.dataset.initialValue || select.value || '';
  const names = priorCollectionNames(stepRow);
  select.innerHTML = '';
  addTransitionOption(
    select,
    '',
    names.length ? 'Choose a prior collection' : 'Add a collection capture to an earlier step',
  );
  names.forEach(name => addTransitionOption(select, name, name));
  if (previous && !names.includes(previous)) {
    addTransitionOption(select, previous, `Missing collection (${previous})`);
    select.options[select.options.length - 1].dataset.workflowMissingCollection = '1';
  }
  select.value = previous || '';
  select.classList.toggle('has-missing-collection', !!previous && !names.includes(previous));
  delete select.dataset.initialValue;
  if (typeof importedSyncAppSelect === 'function') importedSyncAppSelect(select);
}

function refreshCollectionOptions() {
  stepRows().forEach(refreshFanoutCollectionSelect);
}

function updateFanoutSection(section) {
  const enabled = !!section.querySelector('.workflow-editor-fanout-enabled')?.checked;
  const controls = section.querySelector('.workflow-editor-fanout-controls');
  if (controls) controls.hidden = !enabled;
  section.classList.toggle('is-enabled', enabled);
  if (!enabled) return;
  const failureMode = section.querySelector('.workflow-editor-fanout-failure-mode');
  const maxFailures = section.querySelector('.workflow-editor-fanout-max-failures');
  if (failureMode && maxFailures) {
    const failFast = failureMode.value === 'fail_fast';
    if (failFast) maxFailures.value = '1';
    else if (maxFailures.value === '1' && maxFailures.dataset.continueDefault !== '0') {
      maxFailures.value = String(WORKFLOW_FANOUT_LIMITS.maxFailures[1]);
    }
    maxFailures.disabled = failFast;
  }
  const collection = String(
    section.querySelector('.workflow-editor-fanout-collection')?.value || '',
  ).trim();
  const hint = section.querySelector('.workflow-editor-fanout-hint');
  if (hint) {
    hint.textContent = collection
      ? `Command placeholder: {{${collection}}}. One normal scoped run starts for each item.`
      : 'Choose a prior collection, then use its placeholder in this step\'s command.';
  }
  refreshCollectionOptions();
}

function createFanoutSection(step, stepIndex) {
  const raw = step.for_each && typeof step.for_each === 'object' ? step.for_each : null;
  const section = document.createElement('section');
  section.className = 'workflow-editor-fanout';
  section.dataset.workflowField = `steps.${stepIndex}.for_each`;

  const header = document.createElement('div');
  header.className = 'workflow-editor-section-header';
  const title = document.createElement('span');
  title.className = 'workflow-editor-subsection-title';
  title.textContent = 'Collection fan-out';
  const toggleLabel = document.createElement('label');
  toggleLabel.className = 'form-check workflow-editor-fanout-toggle';
  const toggle = document.createElement('input');
  toggle.className = 'workflow-editor-fanout-enabled';
  toggle.type = 'checkbox';
  toggle.checked = !!raw;
  const toggleText = document.createElement('span');
  toggleText.textContent = 'Run once per item';
  toggleLabel.append(toggle, toggleText);
  header.append(title, toggleLabel);

  const collection = optionSelect(
    'workflow-editor-fanout-collection',
    'Fan-out collection',
    [['', 'Choose a prior collection']],
    '',
  );
  collection.dataset.initialValue = String(raw?.collection || '');
  const failureMode = optionSelect(
    'workflow-editor-fanout-failure-mode',
    'Fan-out failure policy',
    WORKFLOW_FANOUT_FAILURE_MODES,
    raw?.failure_mode || raw?.mode || 'fail_fast',
  );
  const retries = numberInput(
    'workflow-editor-fanout-retries',
    raw?.retries ?? 0,
    ...WORKFLOW_FANOUT_LIMITS.retries,
  );
  const maxParallel = numberInput(
    'workflow-editor-fanout-max-parallel',
    raw?.max_parallel ?? 1,
    ...WORKFLOW_FANOUT_LIMITS.maxParallel,
  );
  const maxFailures = numberInput(
    'workflow-editor-fanout-max-failures',
    raw?.max_failures ?? (failureMode.value === 'fail_fast' ? 1 : 32),
    ...WORKFLOW_FANOUT_LIMITS.maxFailures,
  );
  maxFailures.dataset.continueDefault = raw?.failure_mode === 'continue' ? '0' : '1';

  const controls = document.createElement('div');
  controls.className = 'workflow-editor-fanout-controls';
  controls.append(
    field('Collection', collection, `steps.${stepIndex}.for_each.collection`, { wide: true }),
    field('Failure policy', failureMode, `steps.${stepIndex}.for_each.failure_mode`, { wide: true }),
    field('Retries (0–3)', retries, `steps.${stepIndex}.for_each.retries`),
    field('Parallel runs (1–8)', maxParallel, `steps.${stepIndex}.for_each.max_parallel`),
    field('Failure limit (0–32)', maxFailures, `steps.${stepIndex}.for_each.max_failures`),
  );
  const hint = document.createElement('span');
  hint.className = 'workflow-editor-route-hint workflow-editor-fanout-hint';
  controls.appendChild(hint);

  const sectionError = document.createElement('span');
  sectionError.className = 'form-error u-hidden';
  sectionError.setAttribute('aria-live', 'polite');
  section.append(header, controls, sectionError);
  toggle.addEventListener('change', () => updateFanoutSection(section));
  collection.addEventListener('change', () => updateFanoutSection(section));
  failureMode.addEventListener('change', () => updateFanoutSection(section));
  updateFanoutSection(section);
  return section;
}

function createStepRow(step = {}, index = 0, callbacks = {}) {
  const row = document.createElement('div');
  row.className = 'workflow-editor-step panel-row';
  row.dataset.workflowEditorStep = '1';
  row._workflowOriginal = step;

  const header = document.createElement('div');
  header.className = 'workflow-editor-item-header';
  const title = document.createElement('span');
  title.className = 'workflow-editor-item-title workflow-editor-step-title';
  title.textContent = `Step ${index + 1}`;
  const actions = document.createElement('div');
  actions.className = 'workflow-editor-item-actions';
  actions.append(
    iconButton('↑', 'Move workflow step up', 'workflow-editor-move-up', () => callbacks.move?.(row, -1)),
    iconButton('↓', 'Move workflow step down', 'workflow-editor-move-down', () => callbacks.move?.(row, 1)),
    iconButton('×', 'Remove workflow step', 'workflow-editor-remove-step', () => callbacks.remove?.(row)),
  );
  header.append(title, actions);

  const idInput = textInput('workflow-editor-step-id', step.id || `step_${index + 1}`, 'resolve', 64);
  row.dataset.workflowStepIdCurrent = idInput.value;
  idInput.addEventListener('input', () => callbacks.rename?.(row, row.dataset.workflowStepIdCurrent || '', idInput.value));
  const cmdInput = textInput('workflow-editor-step-command', step.cmd, 'nmap -F {{host}}', 1200);
  const noteInput = textInput('workflow-editor-step-note', step.note, 'Optional context for this step', 1000);
  const success = transitionSelect('workflow-editor-step-success', 'After success');
  const failure = transitionSelect('workflow-editor-step-failure', 'After failure');
  success.dataset.initialValue = String(step.next?.success || '__next__');
  failure.dataset.initialValue = String(step.next?.failure || 'stop');

  const transitions = document.createElement('div');
  transitions.className = 'workflow-editor-transition-fields';
  transitions.append(
    field('After success', success, `steps.${index}.next.success`),
    field('After failure', failure, `steps.${index}.next.failure`),
  );
  row.append(
    header,
    field('Step ID', idInput, `steps.${index}.id`),
    field('Command', cmdInput, `steps.${index}.cmd`),
    field('Note', noteInput, `steps.${index}.note`),
    createFanoutSection(step, index),
    transitions,
    createExitCodeSection(step, index),
    createCaptureSection(step, index),
  );
  return row;
}

function refreshFieldPaths() {
  parameterRows().forEach((row, index) => {
    row.querySelector('.workflow-editor-item-title').textContent = `Parameter ${index + 1}`;
    row.querySelectorAll('[data-workflow-field]').forEach((node) => {
      node.dataset.workflowField = node.dataset.workflowField.replace(/^inputs\.\d+/, `inputs.${index}`);
    });
    row.querySelector('.workflow-editor-move-up').disabled = index === 0;
    row.querySelector('.workflow-editor-move-down').disabled = index === parameterRows().length - 1;
  });
  const rows = stepRows();
  rows.forEach((row, index) => {
    row.querySelector('.workflow-editor-step-title').textContent = `Step ${index + 1}`;
    row.querySelectorAll('[data-workflow-field]').forEach((node) => {
      node.dataset.workflowField = node.dataset.workflowField.replace(/^steps\.\d+/, `steps.${index}`);
    });
    captureRows(row).forEach((captureRow, captureIndex) => {
      captureRow.querySelector('.workflow-editor-capture-title').textContent = `Capture ${captureIndex + 1}`;
      captureRow.querySelectorAll('[data-workflow-field]').forEach((node) => {
        node.dataset.workflowField = node.dataset.workflowField
          .replace(/^steps\.\d+/, `steps.${index}`)
          .replace(/captures\.\d+/, `captures.${captureIndex}`);
      });
    });
    exitCodeRows(row).forEach((routeRow, routeIndex) => {
      routeRow.querySelector('.workflow-editor-exit-code-title').textContent = `Route ${routeIndex + 1}`;
      routeRow.querySelectorAll('[data-workflow-field]').forEach((node) => {
        node.dataset.workflowField = node.dataset.workflowField.replace(/codes\.\d+/, `codes.${routeIndex}`);
      });
    });
    row.querySelector('.workflow-editor-move-up').disabled = index === 0;
    row.querySelector('.workflow-editor-move-down').disabled = index === rows.length - 1;
    row.querySelector('.workflow-editor-remove-step').disabled = rows.length <= 1;
  });
  refreshCollectionOptions();
}

function refreshTransitionSelect(select, {
  ids,
  currentId,
  nextId,
  fallback,
  allowNext = false,
  keepMissing = false,
} = {}) {
  const previous = select.dataset.initialValue || select.value || fallback;
  select.innerHTML = '';
  if (allowNext) {
    addTransitionOption(select, '__next__', nextId ? `Next step (${nextId})` : 'Complete');
  }
  addTransitionOption(select, 'complete', 'Complete');
  addTransitionOption(select, 'stop', 'Stop');
  ids.forEach((id) => {
    if (!id || id === currentId) return;
    addTransitionOption(select, id, id);
  });
  const available = [...select.options].some(option => option.value === previous);
  if (!available && previous && keepMissing) {
    addTransitionOption(select, previous, `Missing step (${previous})`);
    select.options[select.options.length - 1].dataset.workflowMissingDestination = '1';
  }
  select.value = (available || (keepMissing && previous)) ? previous : fallback;
  select.classList.toggle('has-missing-destination', !available && keepMissing && !!previous);
  delete select.dataset.initialValue;
  if (typeof importedSyncAppSelect === 'function') importedSyncAppSelect(select);
}

function refreshTransitionOptions() {
  const rows = stepRows();
  const ids = rows.map(row => String(row.querySelector('.workflow-editor-step-id')?.value || '').trim());
  rows.forEach((row, index) => {
    const nextId = ids[index + 1] || '';
    const currentId = ids[index];
    const success = row.querySelector('.workflow-editor-step-success');
    const failure = row.querySelector('.workflow-editor-step-failure');
    refreshTransitionSelect(success, {
      ids, currentId, nextId, fallback: '__next__', allowNext: true,
    });
    refreshTransitionSelect(failure, {
      ids, currentId, nextId, fallback: 'stop',
    });
    exitCodeRows(row).forEach((routeRow) => {
      refreshTransitionSelect(routeRow.querySelector('.workflow-editor-exit-code-destination'), {
        ids, currentId, nextId, fallback: '__next__', allowNext: true, keepMissing: true,
      });
    });
  });
}

function clearErrors() {
  editorRefs().form?.querySelectorAll('[data-workflow-field]').forEach((container) => {
    container.querySelector('.form-error')?.classList.add('u-hidden');
    const control = container.querySelector('input, select, textarea');
    control?.setAttribute('aria-invalid', 'false');
  });
}

function errorContainer(fieldPath) {
  const form = editorRefs().form;
  let path = String(fieldPath || '');
  while (path) {
    const exact = [...(form?.querySelectorAll('[data-workflow-field]') || [])]
      .find(node => node.dataset.workflowField === path);
    if (exact) return exact;
    const separator = path.lastIndexOf('.');
    path = separator >= 0 ? path.slice(0, separator) : '';
  }
  return null;
}

function showErrors(errors) {
  clearErrors();
  const unresolved = [];
  (Array.isArray(errors) ? errors : []).forEach((item) => {
    const message = String(item?.message || '').trim();
    const container = errorContainer(item?.field);
    if (!container || !message) {
      if (message) unresolved.push(message);
      return;
    }
    const error = container.querySelector(':scope > .form-error')
      || container.querySelector('.form-error');
    const control = container.querySelector('input, select, textarea');
    if (error) {
      error.textContent = message;
      error.classList.remove('u-hidden');
    }
    control?.setAttribute('aria-invalid', 'true');
  });
  return unresolved;
}

function resolveTransition(value, index, ids) {
  if (value !== '__next__') return value;
  return ids[index + 1] || 'complete';
}

function canonicalExitCode(value) {
  const text = String(value || '').trim();
  if (!/^[+-]?\d+$/.test(text)) return null;
  try {
    return BigInt(text).toString();
  } catch (_) {
    return null;
  }
}

function validateExitCodeRoutes() {
  const errors = [];
  stepRows().forEach((row, stepIndex) => {
    const seen = new Set();
    exitCodeRows(row).forEach((routeRow, routeIndex) => {
      const codeInput = routeRow.querySelector('.workflow-editor-exit-code');
      const destination = routeRow.querySelector('.workflow-editor-exit-code-destination');
      const rawCode = String(codeInput?.value || '').trim();
      const code = canonicalExitCode(rawCode);
      const codeField = `steps.${stepIndex}.next.codes.${routeIndex}.code`;
      if (!rawCode) {
        errors.push({ field: codeField, message: 'Exit code is required.' });
      } else if (code === null) {
        errors.push({ field: codeField, message: 'Enter a whole-number exit code.' });
      } else if (seen.has(code)) {
        errors.push({ field: codeField, message: 'Exit codes must be unique within a step.' });
      } else {
        seen.add(code);
      }
      if (destination?.selectedOptions?.[0]?.dataset.workflowMissingDestination === '1') {
        errors.push({
          field: `steps.${stepIndex}.next.codes.${routeIndex}.destination`,
          message: 'Choose an available destination or remove this route.',
        });
      }
    });
  });
  return errors;
}

function boundedIntegerError(input, minimum, maximum, label) {
  const raw = String(input?.value || '').trim();
  if (!/^[+-]?\d+$/.test(raw)) return `${label} must be a whole number.`;
  const value = Number(raw);
  if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
    return `${label} must be between ${minimum} and ${maximum}.`;
  }
  return '';
}

function validateCollectionFeatures() {
  const errors = [];
  stepRows().forEach((row, stepIndex) => {
    captureRows(row).forEach((captureRow, captureIndex) => {
      if (captureRow.querySelector('.workflow-editor-capture-kind')?.value !== 'collection') return;
      const itemLimit = captureRow.querySelector('.workflow-editor-capture-item-limit');
      const message = boundedIntegerError(
        itemLimit,
        1,
        WORKFLOW_COLLECTION_ITEM_LIMIT,
        'Item limit',
      );
      if (message) {
        errors.push({
          field: `steps.${stepIndex}.captures.${captureIndex}.item_limit`,
          message,
        });
      }
    });

    if (!row.querySelector('.workflow-editor-fanout-enabled')?.checked) return;
    const collectionSelect = row.querySelector('.workflow-editor-fanout-collection');
    const collection = String(collectionSelect?.value || '').trim();
    if (!collection || collectionSelect?.selectedOptions?.[0]?.dataset.workflowMissingCollection === '1') {
      errors.push({
        field: `steps.${stepIndex}.for_each.collection`,
        message: 'Choose a collection captured by an earlier step.',
      });
    } else {
      const command = String(row.querySelector('.workflow-editor-step-command')?.value || '');
      const token = new RegExp(`\\{\\{\\s*${collection.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*\\}\\}`);
      if (!token.test(command)) {
        errors.push({
          field: `steps.${stepIndex}.cmd`,
          message: `Use {{${collection}}} in this fan-out command.`,
        });
      }
    }
    [
      ['retries', '.workflow-editor-fanout-retries', ...WORKFLOW_FANOUT_LIMITS.retries, 'Retries'],
      ['max_parallel', '.workflow-editor-fanout-max-parallel', ...WORKFLOW_FANOUT_LIMITS.maxParallel, 'Parallel runs'],
      ['max_failures', '.workflow-editor-fanout-max-failures', ...WORKFLOW_FANOUT_LIMITS.maxFailures, 'Failure limit'],
    ].forEach(([fieldName, selector, minimum, maximum, label]) => {
      const message = boundedIntegerError(row.querySelector(selector), minimum, maximum, label);
      if (message) errors.push({ field: `steps.${stepIndex}.for_each.${fieldName}`, message });
    });
  });
  return errors;
}

function serializeParameter(row) {
  const input = {
    id: String(row.querySelector('.workflow-editor-parameter-id')?.value || '').trim(),
    label: String(row.querySelector('.workflow-editor-parameter-label')?.value || '').trim(),
    type: String(row.querySelector('.workflow-editor-parameter-type')?.value || 'text'),
    required: !!row.querySelector('.workflow-editor-parameter-required')?.checked,
    default: String(row.querySelector('.workflow-editor-parameter-default')?.value || '').trim(),
    placeholder: String(row.querySelector('.workflow-editor-parameter-placeholder')?.value || '').trim(),
    help: String(row.querySelector('.workflow-editor-parameter-help')?.value || '').trim(),
  };
  if (row.querySelector('.workflow-editor-parameter-sensitive')?.checked) input.sensitive = true;
  return input;
}

function payloadFromEditor(workflow = null) {
  const refs = editorRefs();
  const inputs = parameterRows().map(serializeParameter);
  const rows = stepRows();
  const ids = rows.map(row => String(row.querySelector('.workflow-editor-step-id')?.value || '').trim());
  const steps = rows.map((row, index) => {
    const original = row._workflowOriginal || {};
    const next = {
      success: resolveTransition(row.querySelector('.workflow-editor-step-success')?.value, index, ids),
      failure: resolveTransition(row.querySelector('.workflow-editor-step-failure')?.value, index, ids),
    };
    const codes = {};
    exitCodeRows(row).forEach((routeRow) => {
      const code = canonicalExitCode(routeRow.querySelector('.workflow-editor-exit-code')?.value);
      const destination = resolveTransition(
        routeRow.querySelector('.workflow-editor-exit-code-destination')?.value,
        index,
        ids,
      );
      if (code !== null && destination) codes[code] = destination;
    });
    if (Object.keys(codes).length) next.codes = codes;
    const captures = captureRows(row).map((captureRow) => {
      const source = String(captureRow.querySelector('.workflow-editor-capture-source')?.value || '');
      const optionInput = captureRow.querySelector('.workflow-editor-capture-option');
      const capture = {
        name: String(captureRow.querySelector('.workflow-editor-capture-name')?.value || '').trim(),
        source,
        required: !!captureRow.querySelector('.workflow-editor-capture-required-input')?.checked,
      };
      if (optionInput?.dataset.captureOptionField) {
        capture[optionInput.dataset.captureOptionField] = String(optionInput.value || '').trim();
      }
      if (captureRow.querySelector('.workflow-editor-capture-kind')?.value === 'collection') {
        capture.kind = 'collection';
        capture.item_limit = Number.parseInt(
          captureRow.querySelector('.workflow-editor-capture-item-limit')?.value || '',
          10,
        );
      }
      return capture;
    });
    const serialized = {
      ...original,
      id: ids[index],
      cmd: String(row.querySelector('.workflow-editor-step-command')?.value || '').trim(),
      note: String(row.querySelector('.workflow-editor-step-note')?.value || '').trim(),
      next,
    };
    if (captures.length) serialized.captures = captures;
    else delete serialized.captures;
    if (row.querySelector('.workflow-editor-fanout-enabled')?.checked) {
      serialized.for_each = {
        collection: String(row.querySelector('.workflow-editor-fanout-collection')?.value || '').trim(),
        failure_mode: String(
          row.querySelector('.workflow-editor-fanout-failure-mode')?.value || 'fail_fast',
        ),
        retries: Number.parseInt(row.querySelector('.workflow-editor-fanout-retries')?.value || '', 10),
        max_parallel: Number.parseInt(
          row.querySelector('.workflow-editor-fanout-max-parallel')?.value || '',
          10,
        ),
        max_failures: Number.parseInt(
          row.querySelector('.workflow-editor-fanout-max-failures')?.value || '',
          10,
        ),
      };
    } else {
      delete serialized.for_each;
    }
    return serialized;
  });
  const requiresVersionThree = Number(workflow?.version) === 3 || steps.some(step => (
    !!step.for_each || step.captures?.some(capture => capture.kind === 'collection')
  ));
  return {
    version: requiresVersionThree ? 3 : 2,
    title: String(refs.titleInput?.value || '').trim(),
    description: String(refs.descriptionInput?.value || '').trim(),
    inputs,
    steps,
    ...(workflow?.id ? { id: workflow.id } : {}),
  };
}

function createWorkflowEditorController({ apiFetch, onSaved, reloadCatalog, showToast } = {}) {
  let workflow = null;

  const setMessage = (message = '', isError = false) => {
    const { msg } = editorRefs();
    if (!msg) return;
    msg.textContent = message;
    msg.classList.toggle('is-error', !!isError);
  };

  const refresh = () => {
    refreshFieldPaths();
    refreshTransitionOptions();
    clearErrors();
  };

  const addParameter = (input = {}) => {
    const refs = editorRefs();
    if (!refs.parameters) return;
    const row = createParameterRow(input, parameterRows().length, {
      move: (target, delta) => {
        const rows = parameterRows();
        const index = rows.indexOf(target);
        const destination = rows[index + delta];
        if (!destination) return;
        if (delta < 0) refs.parameters.insertBefore(target, destination);
        else refs.parameters.insertBefore(destination, target);
        refresh();
      },
      remove: (target) => {
        target.remove();
        refresh();
      },
    });
    refs.parameters.appendChild(row);
    refresh();
  };

  const addStep = (step = {}) => {
    const refs = editorRefs();
    if (!refs.steps) return;
    const row = createStepRow(step, stepRows().length, {
      move: (target, delta) => {
        const rows = stepRows();
        const index = rows.indexOf(target);
        const destination = rows[index + delta];
        if (!destination) return;
        if (delta < 0) refs.steps.insertBefore(target, destination);
        else refs.steps.insertBefore(destination, target);
        refresh();
      },
      remove: (target) => {
        target.remove();
        refresh();
      },
      rename: (target, oldId, newId) => {
        stepRows().forEach((candidate) => {
          candidate.querySelectorAll(
            '.workflow-editor-step-success, .workflow-editor-step-failure, .workflow-editor-exit-code-destination',
          ).forEach((select) => {
            if (select.value === oldId) select.dataset.initialValue = newId;
          });
        });
        target.dataset.workflowStepIdCurrent = newId;
        refreshTransitionOptions();
      },
    });
    refs.steps.appendChild(row);
    refresh();
  };

  const open = (item = null) => {
    const refs = editorRefs();
    if (!refs.overlay || !refs.form || !refs.parameters || !refs.steps) return;
    workflow = item && item.source === 'user' ? item : null;
    refs.title.textContent = workflow ? 'EDIT WORKFLOW' : 'NEW WORKFLOW';
    refs.saveBtn.textContent = workflow ? 'Save changes' : 'Save workflow';
    refs.titleInput.value = workflow?.title || '';
    refs.descriptionInput.value = workflow?.description || '';
    refs.parameters.innerHTML = '';
    refs.steps.innerHTML = '';
    (Array.isArray(workflow?.inputs) ? workflow.inputs : []).forEach(addParameter);
    const sourceSteps = Array.isArray(workflow?.steps) && workflow.steps.length
      ? workflow.steps
      : [{ id: 'step_1', cmd: '', note: '' }];
    sourceSteps.forEach(addStep);
    setMessage('');
    clearErrors();
    refs.overlay.classList.remove('u-hidden');
    refs.overlay.classList.add('open');
    refs.overlay.setAttribute('aria-hidden', 'false');
    setTimeout(() => refs.titleInput?.focus(), 0);
  };

  const close = () => {
    const refs = editorRefs();
    if (!refs.overlay) return;
    refs.overlay.classList.remove('open');
    refs.overlay.classList.add('u-hidden');
    refs.overlay.setAttribute('aria-hidden', 'true');
    refs.form?.reset();
    workflow = null;
  };

  const save = async () => {
    const refs = editorRefs();
    if (!refs.saveBtn) return;
    clearErrors();
    const payload = payloadFromEditor(workflow);
    const clientErrors = [];
    if (!payload.title) clientErrors.push({ field: 'title', message: 'Workflow name is required.' });
    if (!payload.steps.length) clientErrors.push({ field: 'steps', message: 'Add at least one command step.' });
    clientErrors.push(...validateExitCodeRoutes());
    clientErrors.push(...validateCollectionFeatures());
    if (clientErrors.length) {
      showErrors(clientErrors);
      setMessage(clientErrors[0].message, true);
      return;
    }
    refs.saveBtn.disabled = true;
    setMessage('Saving workflow...');
    try {
      const editing = workflow && workflow.id;
      const url = editing ? `/session/workflows/${encodeURIComponent(workflow.id)}` : '/session/workflows';
      const response = await apiFetch(url, {
        method: editing ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const unresolved = showErrors(data.errors);
        throw new Error(unresolved[0] || data.error || `HTTP ${response.status}`);
      }
      onSaved?.(data.workflow || null, { editing: !!editing });
      close();
      await reloadCatalog();
      showToast?.(editing ? 'Workflow updated' : 'Workflow saved');
    } catch (error) {
      setMessage(error.message || 'Failed to save workflow.', true);
    } finally {
      refs.saveBtn.disabled = false;
    }
  };

  const bind = () => {
    document.querySelectorAll('#workflow-new-btn, #rail-workflow-new-btn').forEach((button) => {
      if (button.dataset.workflowEditorOpenBound === '1') return;
      button.dataset.workflowEditorOpenBound = '1';
      bindPressable(button, { onActivate: () => open(), refocusComposer: false });
    });
    const addParameterButton = document.getElementById('workflow-editor-add-parameter');
    if (addParameterButton && addParameterButton.dataset.workflowEditorBound !== '1') {
      addParameterButton.dataset.workflowEditorBound = '1';
      bindPressable(addParameterButton, { onActivate: () => addParameter(), refocusComposer: false });
    }
    const addStepButton = document.getElementById('workflow-editor-add-step');
    if (addStepButton && addStepButton.dataset.workflowEditorBound !== '1') {
      addStepButton.dataset.workflowEditorBound = '1';
      bindPressable(addStepButton, { onActivate: () => addStep(), refocusComposer: false });
    }
    const form = editorRefs().form;
    if (form && form.dataset.workflowEditorBound !== '1') {
      form.dataset.workflowEditorBound = '1';
      form.addEventListener('submit', (event) => {
        event.preventDefault();
        save();
      });
    }
    document.querySelectorAll('.workflow-editor-close').forEach((button) => {
      if (button.dataset.workflowEditorBound === '1') return;
      button.dataset.workflowEditorBound = '1';
      bindPressable(button, { onActivate: close, refocusComposer: false });
    });
    const overlay = editorRefs().overlay;
    if (overlay && overlay.dataset.workflowEditorBound !== '1') {
      overlay.dataset.workflowEditorBound = '1';
      overlay.addEventListener('click', (event) => {
        if (event.target === event.currentTarget) close();
      });
    }
  };

  bind();
  return { addParameter, addStep, close, open, payload: () => payloadFromEditor(workflow), save };
}

export { createWorkflowEditorController, payloadFromEditor };
