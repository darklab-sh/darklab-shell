// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Remediation-level fix-first worklist shared by desktop and mobile Assessment views.

import { findingRiskSummary } from '../findings/finding_risk.js';
import { bindDisclosure } from '../../ui/ui_disclosure.js';

const priorityFilters = [
  ['', 'All priorities', 'total'],
  ['kev', 'CISA KEV', 'kev_listed'],
  ['epss', 'EPSS scored', 'epss_scored'],
  ['cvss', 'CVSS scored', 'cvss_scored'],
  ['unscored', 'Unscored', 'unscored'],
];

const validationLabels = {
  active_confirmation: 'Actively confirmed',
  captured_observation: 'Captured observation',
  imported_assertion: 'Imported assertion',
  manual_assessment: 'Manual assessment',
  version_inference: 'Version inference',
};

function makeElement(tag, className = '', text = '') {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== '') element.textContent = String(text);
  return element;
}

function badge(text, tone = 'muted') {
  return makeElement('span', `badge badge-tone-${tone}`, text);
}

function severityTone(severity) {
  if (severity === 'critical' || severity === 'high') return 'red';
  if (severity === 'medium') return 'amber';
  return 'muted';
}

function filterChip(context, label, count, active, onActivate) {
  const chip = makeElement('button', `chip${active ? ' is-active' : ''}`, `${label} · ${count}`);
  chip.type = 'button';
  chip.setAttribute('aria-pressed', active ? 'true' : 'false');
  context.bindProjectRuntimePressable?.(chip, { onActivate, clearPressStyle: true });
  return chip;
}

function priorityContext(item) {
  const context = item?.priority_context || {};
  const confidence = Array.isArray(context.confidence) ? context.confidence[0] : '';
  const exposure = Array.isArray(context.exposure) ? context.exposure[0] : '';
  return [
    confidence ? `${confidence} confidence` : '',
    exposure ? `${exposure} exposure` : '',
  ].filter(Boolean).join(' · ');
}

function lastSeenContext(context, item) {
  const value = String(item?.last_seen_at || '');
  if (!value) return '';
  const displayed = typeof context.formatDate === 'function' ? context.formatDate(value) : value;
  return `last seen ${displayed}`;
}

function observationButton(context, actions, projectId, observation) {
  const label = observation?.title || 'Open finding';
  const button = makeElement('button', 'btn btn-secondary btn-compact', label);
  button.type = 'button';
  button.title = 'Open this saved observation';
  context.bindProjectRuntimePressable?.(button, {
    onActivate: () => void actions.openDeltaFinding(projectId, observation),
  });
  return button;
}

function renderObservations(context, actions, projectId, item) {
  const observations = Array.isArray(item?.observation_summaries)
    ? item.observation_summaries
    : [];
  const wrap = makeElement('div', 'project-assessment-risk-observations');
  if (observations.length <= 1) {
    if (observations[0]) wrap.appendChild(observationButton(context, actions, projectId, observations[0]));
    return wrap;
  }
  const toggle = makeElement(
    'button',
    'control-row project-assessment-risk-observation-toggle',
    `View ${observations.length} observations`,
  );
  toggle.type = 'button';
  const list = makeElement('div', 'project-assessment-risk-observation-list');
  observations.forEach((observation) => {
    const row = makeElement('div', 'project-assessment-risk-observation');
    row.append(
      observationButton(context, actions, projectId, observation),
      badge(validationLabels[observation?.validation_method] || observation?.validation_method || 'Observed'),
    );
    list.appendChild(row);
  });
  bindDisclosure(toggle, {
    panel: list,
    initialOpen: false,
    hiddenClass: 'u-hidden',
    openClass: 'is-open',
    clearPressStyle: true,
  });
  wrap.append(toggle, list);
  return wrap;
}

function renderRiskRow(context, actions, projectId, item) {
  const row = makeElement('article', 'panel-row project-assessment-risk-row');
  const heading = makeElement('div', 'project-assessment-risk-heading');
  const identity = item?.vulnerability_id || item?.rule_identity || item?.remediation_id || 'Saved finding';
  heading.append(
    makeElement('strong', '', identity),
    badge(item?.severity || 'info', severityTone(item?.severity)),
  );
  row.append(heading, makeElement('div', 'project-assessment-risk-title', item?.title || 'Saved finding'));
  const risk = findingRiskSummary(item);
  row.appendChild(makeElement(
    'div',
    'project-assessment-risk-signals',
    risk || 'No stored public exploit signal',
  ));
  const validation = validationLabels[item?.strongest_validation_method]
    || item?.strongest_validation_method
    || 'Observation method unavailable';
  const meta = [
    `${Number(item?.observation_count || 0)} observation${Number(item?.observation_count || 0) === 1 ? '' : 's'}`,
    `${Number(item?.evidence_count || 0)} evidence source${Number(item?.evidence_count || 0) === 1 ? '' : 's'}`,
    validation,
    priorityContext(item),
    lastSeenContext(context, item),
  ].filter(Boolean).join(' · ');
  row.appendChild(makeElement('div', 'project-assessment-risk-meta', meta));
  if (item?.remediation_preview) {
    row.appendChild(makeElement('p', 'project-assessment-risk-remediation', item.remediation_preview));
  }
  row.appendChild(renderObservations(context, actions, projectId, item));
  return row;
}

function renderPager(context, actions, projectId, page, state) {
  const total = Math.max(0, Number(page?.total || 0));
  const limit = Math.max(1, Number(page?.limit || state.findingLimit || 10));
  const offset = Math.max(0, Number(page?.offset || state.findingOffset || 0));
  if (total <= limit && offset === 0) return null;
  const pager = makeElement('div', 'project-assessment-pager');
  const previous = makeElement('button', 'btn btn-secondary btn-compact', 'Previous');
  previous.type = 'button';
  previous.disabled = offset <= 0;
  context.bindProjectRuntimePressable?.(previous, {
    onActivate: () => void actions.setFindingPage(projectId, Math.max(0, offset - limit)),
  });
  const next = makeElement('button', 'btn btn-secondary btn-compact', 'Next');
  next.type = 'button';
  next.disabled = offset + limit >= total;
  context.bindProjectRuntimePressable?.(next, {
    onActivate: () => void actions.setFindingPage(projectId, offset + limit),
  });
  pager.append(
    previous,
    makeElement('span', '', `${offset + 1}–${Math.min(offset + limit, total)} of ${total}`),
    next,
  );
  return pager;
}

function renderAssessmentFindingWorklist(context, actions, projectId, state, worklist) {
  const page = worklist || {};
  const rollup = page.rollup || {};
  const section = makeElement('section', 'project-assessment-section project-assessment-risk');
  const heading = makeElement('div', 'project-assessment-section-heading');
  const copy = makeElement('div');
  copy.append(
    makeElement('h3', '', 'Fix first'),
    makeElement(
      'p',
      '',
      'Current-cycle issues ranked by CISA KEV, EPSS, CVSS, then age. Coverage remains a separate measure.',
    ),
  );
  heading.appendChild(copy);
  section.appendChild(heading);

  const filters = makeElement('div', 'project-assessment-risk-filters');
  priorityFilters.forEach(([value, label, countKey]) => {
    filters.appendChild(filterChip(
      context,
      label,
      Number(rollup[countKey] || 0),
      state.findingPriority === value,
      () => void actions.setFindingFilter(projectId, value),
    ));
  });
  section.appendChild(filters);

  const items = Array.isArray(page.items) ? page.items : [];
  if (!items.length) {
    section.appendChild(context.emptyProjectPanel(
      state.findingPriority
        ? 'No current-cycle issues match this priority filter.'
        : 'No current-cycle findings are backed by compatible saved evidence yet.',
    ));
    return section;
  }
  const list = makeElement('div', 'project-assessment-risk-list');
  items.forEach(item => list.appendChild(renderRiskRow(context, actions, projectId, item)));
  section.appendChild(list);
  const pager = renderPager(context, actions, projectId, page, state);
  if (pager) section.appendChild(pager);
  return section;
}

export { renderAssessmentFindingWorklist };
