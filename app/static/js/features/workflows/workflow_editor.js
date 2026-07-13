// Workflows v2 definition editor.
import { bindPressable } from '../../ui/ui_pressable.js';

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

function createCaptureSourceSelect(value) {
  const select = document.createElement('select');
  select.className = 'form-select workflow-editor-capture-source';
  select.setAttribute('aria-label', 'Capture selector');
  WORKFLOW_CAPTURE_SOURCES.forEach(([source, label]) => addTransitionOption(select, source, label));
  select.value = String(value || 'first_nonempty_line');
  return select;
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
  updateDestination();
  destination.append(destinationLabel, destinationValue);

  const required = createRequiredControl(capture.required);
  required.classList.add('workflow-editor-capture-required');
  required.querySelector('input').className = 'workflow-editor-capture-required-input';
  row.append(
    header,
    field('Name', nameInput, `steps.${stepIndex}.captures.${captureIndex}.name`),
    field('Selector', sourceSelect, `steps.${stepIndex}.captures.${captureIndex}.source`),
    optionHost,
    required,
    destination,
  );
  sourceSelect.addEventListener('change', () => updateCaptureOption(row, stepIndex, captureIndex));
  updateCaptureOption(row, stepIndex, captureIndex);
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
    });
    list.appendChild(row);
    refreshCaptures();
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
  header.append(
    title,
    iconButton('×', 'Remove workflow step', 'workflow-editor-remove-step', () => callbacks.remove?.(row)),
  );

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
    transitions,
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
    row.querySelector('.workflow-editor-remove-step').disabled = rows.length <= 1;
  });
}

function refreshTransitionOptions() {
  const rows = stepRows();
  const ids = rows.map(row => String(row.querySelector('.workflow-editor-step-id')?.value || '').trim());
  rows.forEach((row, index) => {
    const nextId = ids[index + 1] || '';
    const currentId = ids[index];
    const success = row.querySelector('.workflow-editor-step-success');
    const failure = row.querySelector('.workflow-editor-step-failure');
    [success, failure].forEach((select) => {
      const previous = select.dataset.initialValue || select.value || (select === success ? '__next__' : 'stop');
      select.innerHTML = '';
      if (select === success) {
        addTransitionOption(select, '__next__', nextId ? `Next step (${nextId})` : 'Complete');
      }
      addTransitionOption(select, 'complete', 'Complete');
      addTransitionOption(select, 'stop', 'Stop');
      ids.forEach((id) => {
        if (!id || id === currentId) return;
        addTransitionOption(select, id, id);
      });
      const available = [...select.options].some(option => option.value === previous);
      select.value = available ? previous : (select === success ? '__next__' : 'stop');
      delete select.dataset.initialValue;
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
    const error = container.querySelector('.form-error');
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
    const originalNext = original.next && typeof original.next === 'object' ? original.next : {};
    const next = {
      success: resolveTransition(row.querySelector('.workflow-editor-step-success')?.value, index, ids),
      failure: resolveTransition(row.querySelector('.workflow-editor-step-failure')?.value, index, ids),
    };
    if (originalNext.codes && typeof originalNext.codes === 'object') next.codes = originalNext.codes;
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
    return serialized;
  });
  return {
    version: 2,
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
      remove: (target) => {
        target.remove();
        refresh();
      },
      rename: (target, oldId, newId) => {
        stepRows().forEach((candidate) => {
          candidate.querySelectorAll('.workflow-editor-step-success, .workflow-editor-step-failure').forEach((select) => {
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
