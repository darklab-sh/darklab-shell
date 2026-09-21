// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { bindDisclosure } from '../../ui/ui_disclosure.js';

export function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

export function displayValue(value) {
  if (value?.mode === 'unobserved') return 'Not observed by this worker';
  if (value?.mode === 'summary') {
    if (value.summary === 'count') return `${value.value} entries configured`;
    if (value.summary === 'presence') return value.value ? 'Configured' : 'Not configured';
  }
  if (value?.mode !== 'full') return 'Value withheld';
  if (value.value === null) return 'Not set';
  if (value.value === '') return '(empty)';
  return typeof value.value === 'string' ? value.value : JSON.stringify(value.value, null, 2);
}

export function disclosure(label, key, content, state, { initialOpen = false, onToggle } = {}) {
  const wrapper = element('div', undefined, 'admin-disclosure');
  const trigger = element('button', undefined, 'btn btn-ghost admin-disclosure-trigger');
  trigger.type = 'button';
  trigger.dataset.browseKey = key;
  const indicator = element('span', undefined, 'admin-disclosure-indicator');
  indicator.setAttribute('aria-hidden', 'true');
  trigger.append(indicator, element('span', label));
  const panel = element('div', undefined, 'admin-disclosure-panel');
  panel.id = `admin-panel-${encodeURIComponent(key)}`;
  trigger.setAttribute('aria-controls', panel.id);
  panel.append(...content);
  const open = state.has(key) ? state.get(key) : initialOpen;
  indicator.textContent = open ? '▾' : '▸';
  const handle = bindDisclosure(trigger, { panel, initialOpen: open, hiddenClass: 'u-hidden', refocusComposer: false,
    onToggle: expanded => {
      state.set(key, expanded);
      indicator.textContent = expanded ? '▾' : '▸';
      onToggle?.(expanded);
    },
  });
  // Shared pressables clear focus after activation. Keep keyboard readers on
  // this standalone page's trigger so a second Enter/Space can collapse it.
  trigger.addEventListener('click', event => { if (event.detail === 0) trigger.focus({ preventScroll: true }); });
  wrapper.append(trigger, panel);
  return { wrapper, trigger, panel, handle };
}

export function acceptedValues(rules = {}) {
  const types = { boolean: 'Boolean: true or false', integer: 'Whole number', number: 'Number', string: 'Text', array: 'List', object: 'Structured settings' };
  const parts = [];
  if (rules.type) parts.push(types[rules.type] || rules.type);
  if (rules.enum) parts.push(`Choices: ${rules.enum.join(', ')}`);
  if (rules.minimum !== undefined && rules.maximum !== undefined) parts.push(`From ${rules.minimum} to ${rules.maximum}, inclusive`);
  else if (rules.minimum !== undefined) parts.push(`Minimum: ${rules.minimum}`);
  else if (rules.maximum !== undefined) parts.push(`Maximum: ${rules.maximum}`);
  if (rules.input) parts.push(rules.input.charAt(0).toUpperCase() + rules.input.slice(1));
  if (rules.fallback !== undefined) parts.push(`Invalid input uses ${rules.fallback}`);
  if (rules.pattern) parts.push(`Must match pattern: ${rules.pattern}`);
  return parts;
}

function valueNode(value, { preview = false, key } = {}) {
  const text = displayValue(value);
  const structured = value?.mode === 'full' && typeof value.value === 'object' && value.value !== null;
  const node = element(structured ? 'pre' : 'span', preview && text.length > 240 ? `${text.slice(0, 240)}…` : text,
    `admin-value ${structured ? 'admin-code nice-scroll' : 'admin-scalar'} admin-${value?.mode || 'withheld'}`);
  if (!preview && value?.truncated) node.append(document.createTextNode(' (truncated)'));
  if (structured) {
    node.dataset.scrollKey = key;
    node.dataset.browseKey = key;
    node.tabIndex = 0;
  }
  return node;
}

function definition(list, label, value) {
  const item = element('div');
  const description = element('dd');
  description.append(typeof value === 'string' ? document.createTextNode(value) : value);
  item.append(element('dt', label), description);
  list.append(item);
}

export function loadedSource(row) {
  const names = { default: 'Built-in default', shipped: 'Shipped config.yaml', local: 'Local config.local.yaml', host: 'Not observed by this worker' };
  return names[row.source.layer] || row.source.name;
}

export function settingCard(row, state) {
  const card = element('article', undefined, 'admin-setting');
  card.dataset.key = row.key;
  card.append(element('h3', row.label || row.key), element('code', row.key, 'admin-setting-key'), element('p', row.description));
  const values = element('dl', undefined, 'admin-metadata');
  definition(values, row.source.layer === 'host' ? 'Host value' : 'Loaded value', valueNode(row.effective, { preview: true, key: `${row.key}:loaded` }));
  definition(values, 'Loaded from', loadedSource(row));
  card.append(values);
  if (row.effective?.mode === 'full' && displayValue(row.effective).length > 240) {
    const full = element('pre', displayValue(row.effective), 'admin-code nice-scroll');
    full.dataset.scrollKey = `${row.key}:value`;
    full.tabIndex = 0;
    full.dataset.browseKey = `${row.key}:value-text`;
    card.append(disclosure('Expand permitted value', `${row.key}:value`, [full], state).wrapper);
  }
  if (row.effective?.truncated) card.append(element('p', 'Truncated by the display limit; this is not the complete value.', 'admin-warning'));
  for (const warning of row.warnings) card.append(element('p', `${warning.event}: ${warning.reason}`, 'admin-warning'));
  const metadata = element('dl', undefined, 'admin-metadata');
  definition(metadata, 'Default', valueNode(row.default, { key: `${row.key}:default` }));
  if (row.yaml) {
    definition(metadata, 'Where to configure', `config.local.yaml → ${row.yaml}. Overrides built-in defaults and any shipped config.yaml value.`);
    definition(metadata, 'Usual locations', 'Source checkout: app/conf/config.local.yaml. Packaged deployment: conf/config.local.yaml beside the Compose files. Custom configuration directories may differ; this worker cannot identify the host path.');
  } else {
    definition(metadata, 'Where to configure', `${row.input || 'Host deployment configuration'} → ${row.key}. Use the deployment’s Compose configuration or its supported host inputs.`);
  }
  definition(metadata, 'Environment override', row.environment?.join(', ') || 'No supported override');
  if (row.environment?.length) definition(metadata, 'Deployment input', 'A host .env file is an input only where Compose passes the variable to the application or uses it for deployment. The worker cannot tell whether an environment value came from .env.');
  definition(metadata, 'Affected processes', row.processes?.join(', ') || 'Deployment');
  const guidance = [metadata];
  const rules = row.rules || {};
  const accepted = acceptedValues(rules);
  if (accepted.length) {
    const section = element('div', undefined, 'admin-accepted');
    section.append(element('h4', 'Accepted values'));
    const list = element('ul');
    list.append(...accepted.map(text => element('li', text)));
    section.append(list);
    const raw = element('pre', JSON.stringify(rules, null, 2), 'admin-code nice-scroll');
    raw.dataset.scrollKey = `${row.key}:schema`;
    raw.dataset.browseKey = `${row.key}:schema-text`;
    raw.tabIndex = 0;
    section.append(disclosure('Raw schema', `${row.key}:schema`, [raw], state).wrapper);
    guidance.push(section);
  }
  guidance.push(element('p', row.apply));
  card.append(disclosure('Defaults and host configuration', `${row.key}:guidance`, guidance, state).wrapper);
  return card;
}
