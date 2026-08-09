// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

// Shared desktop/mobile renderer for the Project Assessment tab.

import { bindDisclosure } from '../../ui/ui_disclosure.js';
import { openActionSheet } from '../../ui/ui_action_sheet.js';
import { renderAssessmentFindingWorklist } from './project_assessment_risk_renderer.js';

const checkStateLabels = {
  blocked: 'Blocked',
  covered: 'Covered',
  failed: 'Failed',
  needs_review: 'Needs review',
  not_applicable: 'Not applicable',
  not_started: 'Not started',
  running: 'Running',
  skipped: 'Skipped',
};

const filterStates = [
  '',
  'needs_review',
  'not_started',
  'running',
  'failed',
  'blocked',
  'skipped',
  'not_applicable',
  'covered',
];

const findingDeltaLabels = {
  new: 'New',
  persistent: 'Persistent',
  not_observed: 'Not observed',
  regressed: 'Regressed',
  incomparable: 'Incomparable',
};

function createProjectAssessmentRenderer(context, actions) {
  const ctx = context || {};
  const act = actions || {};

  function makeElement(tag, className = '', text = '') {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== '') element.textContent = String(text);
    return element;
  }

  function badge(text, tone = 'muted') {
    return makeElement('span', `badge badge-tone-${tone}`, text);
  }

  function stateTone(state) {
    const normalized = String(state || '');
    if (normalized === 'covered') return 'green';
    if (['needs_review', 'running', 'blocked'].includes(normalized)) return 'amber';
    if (normalized === 'failed') return 'red';
    return 'muted';
  }

  function statusTone(status) {
    if (status === 'active') return 'green';
    if (status === 'completed') return 'amber';
    return 'muted';
  }

  function displayDate(value) {
    const normalized = String(value || '');
    if (!normalized) return '';
    return typeof ctx.formatDate === 'function' ? ctx.formatDate(normalized) : normalized;
  }

  function profileByKey(st, key) {
    return st.profiles.find(profile => String(profile?.key || '') === String(key || '')) || null;
  }

  function checkDefinition(detail, check) {
    const definitions = detail?.assessment?.profile_snapshot?.checks;
    if (!Array.isArray(definitions)) return null;
    return definitions.find(item => String(item?.key || '') === String(check?.check_key || '')) || null;
  }

  function cycleLabel(st, assessment) {
    const profile = profileByKey(st, assessment?.profile_key);
    const title = String(assessment?.title || profile?.label || assessment?.profile_key || 'Assessment');
    const started = displayDate(assessment?.started_at || assessment?.created_at);
    return started ? `${title} · ${started}` : title;
  }

  function sectionHeading(title, copy) {
    const heading = makeElement('div', 'project-assessment-section-heading');
    const content = makeElement('div');
    content.append(makeElement('h3', '', title), makeElement('p', '', copy));
    heading.appendChild(content);
    return heading;
  }

  function renderStartCard(projectId, st) {
    const section = makeElement('section', 'project-assessment-start project-assessment-section');
    section.appendChild(sectionHeading(
      st.assessments.length ? 'Start another cycle' : 'Start an assessment',
      'Choose a saved methodology. The cycle freezes its checks and current confirmed targets so later edits do not rewrite the assessment.',
    ));
    if (!st.profiles.length) {
      section.appendChild(ctx.emptyProjectPanel('No assessment profiles are available.'));
      return section;
    }

    const form = makeElement('form', 'project-assessment-start-form');
    const label = makeElement('label', 'project-assessment-profile-field');
    label.appendChild(makeElement('span', '', 'Profile'));
    const select = makeElement('select', 'form-select');
    select.name = 'profile_key';
    select.setAttribute('aria-label', 'Assessment profile');
    st.profiles.forEach((profile) => {
      const option = document.createElement('option');
      option.value = String(profile?.key || '');
      option.textContent = `${profile?.label || profile?.key} (${Number(profile?.check_count || 0)} checks)`;
      select.appendChild(option);
    });
    label.appendChild(select);

    const submit = makeElement('button', 'btn btn-primary btn-compact', st.creating ? 'Starting…' : 'Start cycle');
    submit.type = 'submit';
    const canManage = ctx.canMutateProjects?.() !== false;
    submit.disabled = st.creating || !canManage;
    if (!canManage) submit.title = 'View-only team members cannot start assessment cycles.';
    ctx.bindProjectRuntimePressable?.(submit);
    form.append(label, submit);
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      void act.createCycle(projectId, select.value);
    });
    section.appendChild(form);

    const initialProfile = profileByKey(st, select.value) || st.profiles[0];
    const purpose = makeElement('p', 'project-assessment-profile-purpose', initialProfile?.purpose || '');
    select.addEventListener('change', () => {
      purpose.textContent = profileByKey(st, select.value)?.purpose || '';
    });
    section.appendChild(purpose);
    return section;
  }

  function lifecycleItems(projectId, st, assessment) {
    const disabled = !!st.mutating || ctx.canMutateProjects?.() === false;
    const status = String(assessment?.status || '');
    const items = [];
    if (status === 'active') {
      items.push({
        label: 'Complete cycle',
        action: returnFocus => act.transitionCycle(projectId, 'completed', returnFocus),
        disabled,
      });
    }
    if (status === 'active' || status === 'completed') {
      items.push({
        label: 'Archive cycle',
        action: returnFocus => act.transitionCycle(projectId, 'archived', returnFocus),
        disabled,
      });
    }
    if (status === 'archived') {
      items.push({
        label: 'Delete assessment',
        action: returnFocus => act.deleteCycle(projectId, returnFocus),
        disabled,
        tone: 'danger',
      });
    }
    return items;
  }

  function renderDesktopLifecycleActions(projectId, st, assessment) {
    const wrap = makeElement('div', 'project-assessment-cycle-actions');
    lifecycleItems(projectId, st, assessment).forEach((item) => {
      const button = makeElement(
        'button',
        item.tone === 'danger' ? 'btn btn-destructive btn-compact' : 'btn btn-secondary btn-compact',
        item.label,
      );
      button.type = 'button';
      button.disabled = item.disabled;
      if (ctx.canMutateProjects?.() === false) {
        button.title = 'View-only team members cannot change assessment cycles.';
      }
      ctx.bindProjectRuntimePressable?.(button, {
        onActivate: () => item.action(button),
      });
      wrap.appendChild(button);
    });
    return wrap;
  }

  function renderMobileLifecycleActions(projectId, st, assessment) {
    const sourceItems = lifecycleItems(projectId, st, assessment);
    if (!sourceItems.length) return null;
    const footer = makeElement('div', 'project-assessment-mobile-actions');
    const button = makeElement('button', 'btn btn-secondary', st.mutating ? 'Working…' : 'Cycle actions');
    button.type = 'button';
    button.disabled = !!st.mutating || ctx.canMutateProjects?.() === false;
    if (ctx.canMutateProjects?.() === false) {
      button.title = 'View-only team members cannot change assessment cycles.';
    }
    const items = sourceItems.map(item => ({
      ...item,
      action: () => item.action(button),
    }));
    ctx.bindProjectRuntimePressable?.(button, {
      onActivate: () => openActionSheet({
        title: `Assessment actions for ${assessment?.title || 'this cycle'}`,
        items,
        container: ctx.actionSheetContainer?.() || document.body,
        returnFocus: button,
      }),
    });
    footer.appendChild(button);
    return footer;
  }

  function renderCycleHeader(projectId, st, assessment, { mobile = false } = {}) {
    const section = makeElement('section', 'project-assessment-cycle project-assessment-section');
    const top = makeElement('div', 'project-assessment-cycle-top');
    const title = makeElement('div', 'project-assessment-cycle-title');
    title.append(
      makeElement('h2', '', assessment?.title || 'Assessment'),
      makeElement(
        'p',
        '',
        `${profileByKey(st, assessment?.profile_key)?.label || assessment?.profile_key || 'Profile'} · version ${assessment?.profile_version || 'unknown'}`,
      ),
    );
    top.append(title, badge(String(assessment?.status || 'unknown'), statusTone(assessment?.status)));
    section.appendChild(top);

    const controls = makeElement('div', 'project-assessment-cycle-controls');
    const field = makeElement('label', 'project-assessment-cycle-field');
    field.appendChild(makeElement('span', '', 'Cycle'));
    const select = makeElement('select', 'form-select');
    select.setAttribute('aria-label', 'Assessment cycle');
    st.assessments.forEach((item) => {
      const option = document.createElement('option');
      option.value = String(item?.id || '');
      option.textContent = cycleLabel(st, item);
      option.selected = option.value === st.selectedId;
      select.appendChild(option);
    });
    select.addEventListener('change', () => void act.selectCycle(projectId, select.value));
    field.appendChild(select);
    controls.appendChild(field);
    const dates = [
      assessment?.started_at ? `Started ${displayDate(assessment.started_at)}` : '',
      assessment?.completed_at ? `Completed ${displayDate(assessment.completed_at)}` : '',
      assessment?.archived_at ? `Archived ${displayDate(assessment.archived_at)}` : '',
    ].filter(Boolean).join(' · ');
    controls.appendChild(makeElement('div', 'project-assessment-cycle-dates', dates));
    section.appendChild(controls);
    if (!mobile) section.appendChild(renderDesktopLifecycleActions(projectId, st, assessment));
    return section;
  }

  function summaryCard(value, label, detail = '', tone = '') {
    const card = makeElement('div', `project-assessment-summary-card${tone ? ` is-${tone}` : ''}`);
    card.append(makeElement('strong', '', value), makeElement('span', '', label));
    if (detail) card.appendChild(makeElement('small', '', detail));
    return card;
  }

  function renderCoverage(rollup) {
    const data = rollup || {};
    const section = makeElement('section', 'project-assessment-section');
    section.appendChild(sectionHeading(
      'Coverage',
      'Coverage reflects compatible saved evidence and explicit assessment decisions.',
    ));
    const cards = makeElement('div', 'project-assessment-summary-grid');
    cards.append(
      summaryCard(data.covered_checks || 0, 'Covered', `of ${Number(data.applicable_checks || 0)} applicable`, 'success'),
      summaryCard(data.checks_awaiting_review || 0, 'Awaiting review', '', Number(data.checks_awaiting_review || 0) ? 'attention' : ''),
      summaryCard(data.untested_checks || 0, 'Untested', 'not started, running, or failed'),
      summaryCard(data.excluded_checks || 0, 'Excluded', 'blocked, skipped, or not applicable'),
      summaryCard(
        data.unavailable_evidence_checks || 0,
        'Evidence unavailable',
        'saved source was removed',
        Number(data.unavailable_evidence_checks || 0) ? 'danger' : '',
      ),
    );
    section.appendChild(cards);
    return section;
  }

  function deltaTone(state) {
    if (state === 'regressed') return 'red';
    if (state === 'new') return 'amber';
    if (state === 'persistent') return 'green';
    return 'muted';
  }

  function comparisonCopy(comparison) {
    const status = String(comparison?.status || 'pending');
    if (status === 'comparable') {
      return 'This cycle is compared with the latest earlier cycle that used the same saved check and evidence rule.';
    }
    if (status === 'partial') {
      return 'Some checks have a compatible earlier baseline; others remain explicitly incomparable.';
    }
    if (status === 'no_baseline') {
      return 'No earlier completed cycle has the same saved check and target yet.';
    }
    if (status === 'incomparable') {
      return "The saved checks can't be compared safely because their evidence contracts differ or evidence is unavailable.";
    }
    return 'Finding changes will appear after this cycle saves compatible evidence.';
  }

  function renderDeltaFindingButtons(projectId, side, findings) {
    const group = makeElement('div', 'project-assessment-delta-evidence');
    group.appendChild(makeElement('strong', '', side === 'current' ? 'This cycle' : 'Earlier cycle'));
    const records = Array.isArray(findings) ? findings : [];
    if (!records.length) {
      group.appendChild(makeElement(
        'span',
        'project-assessment-delta-empty',
        side === 'current' ? 'No compatible observation saved' : 'No earlier observation saved',
      ));
      return group;
    }
    records.forEach((finding) => {
      const button = makeElement('button', 'btn btn-secondary btn-compact', finding?.title || 'Open finding');
      button.type = 'button';
      button.title = `${side === 'current' ? 'Open current' : 'Open earlier'} finding details`;
      ctx.bindProjectRuntimePressable?.(button, {
        onActivate: () => void act.openDeltaFinding(projectId, finding, button),
      });
      group.appendChild(button);
    });
    return group;
  }

  function renderFindingDeltas(projectId, findingDeltas) {
    const data = findingDeltas || {};
    const comparison = data.comparison || {};
    const rollup = data.rollup || {};
    const section = makeElement('section', 'project-assessment-section project-assessment-deltas');
    section.appendChild(sectionHeading('Finding changes', comparisonCopy(comparison)));
    const cards = makeElement('div', 'project-assessment-summary-grid');
    cards.append(
      summaryCard(rollup.new || 0, 'New', 'first seen in this cycle', Number(rollup.new || 0) ? 'attention' : ''),
      summaryCard(rollup.persistent || 0, 'Persistent', 'seen in both compatible cycles'),
      summaryCard(rollup.not_observed || 0, 'Not observed', 'absent from a compatible clean check', 'success'),
      summaryCard(rollup.regressed || 0, 'Regressed', 'returned after verified remediation', Number(rollup.regressed || 0) ? 'danger' : ''),
      summaryCard(rollup.incomparable || 0, 'Incomparable', 'evidence cannot support a delta'),
    );
    section.appendChild(cards);

    const items = Array.isArray(data.items) ? data.items : [];
    if (!items.length) return section;
    const list = makeElement('div', 'project-assessment-delta-list');
    items.forEach((item) => {
      const row = makeElement('article', 'panel-row project-assessment-delta-row');
      const heading = makeElement('div', 'project-assessment-delta-heading');
      const identity = item?.vulnerability_id || item?.rule_identity || item?.remediation_id || 'Saved finding';
      heading.append(
        makeElement('strong', '', identity),
        badge(findingDeltaLabels[item?.state] || item?.state || 'Incomparable', deltaTone(item?.state)),
      );
      const targets = [...new Set(
        (Array.isArray(item?.checks) ? item.checks : [])
          .map(check => check?.target_value)
          .filter(Boolean),
      )];
      const meta = [
        targets.join(', '),
        `${Number(item?.current_observations?.length || 0)} current observation${Number(item?.current_observations?.length || 0) === 1 ? '' : 's'}`,
        `${Number(item?.previous_observations?.length || 0)} earlier observation${Number(item?.previous_observations?.length || 0) === 1 ? '' : 's'}`,
      ].filter(Boolean).join(' · ');
      row.append(heading, makeElement('div', 'project-assessment-delta-meta', meta));
      const reason = Array.isArray(item?.reasons) ? item.reasons[0] : '';
      if (reason) row.appendChild(makeElement('p', 'project-assessment-delta-reason', reason));
      const evidence = makeElement('div', 'project-assessment-delta-evidence-grid');
      evidence.append(
        renderDeltaFindingButtons(projectId, 'current', item?.current_findings),
        renderDeltaFindingButtons(projectId, 'previous', item?.previous_findings),
      );
      row.appendChild(evidence);
      list.appendChild(row);
    });
    section.appendChild(list);
    if (data.truncated) {
      section.appendChild(makeElement(
        'p',
        'project-assessment-delta-limit',
        `Showing the first ${Number(data.item_limit || items.length)} remediation groups.`,
      ));
    }
    return section;
  }

  function filterChip(label, active, onActivate) {
    const chip = makeElement('button', `chip${active ? ' is-active' : ''}`, label);
    chip.type = 'button';
    chip.setAttribute('aria-pressed', active ? 'true' : 'false');
    ctx.bindProjectRuntimePressable?.(chip, { onActivate, clearPressStyle: true });
    return chip;
  }

  function renderCategoryProgress(projectId, st, rollups) {
    const section = makeElement('section', 'project-assessment-section');
    section.appendChild(sectionHeading(
      'Category progress',
      'Narrow the check worklist without changing the cycle.',
    ));
    const list = makeElement('div', 'project-assessment-category-list');
    list.appendChild(filterChip('All categories', !st.category, () => {
      void act.setFilter(projectId, 'category', '');
    }));
    (Array.isArray(rollups) ? rollups : []).forEach((item) => {
      const category = String(item?.category || 'uncategorized');
      const label = `${category} · ${Number(item?.covered_checks || 0)}/${Number(item?.applicable_checks || 0)} covered`;
      list.appendChild(filterChip(label, st.category === category, () => {
        void act.setFilter(projectId, 'category', category);
      }));
    });
    section.appendChild(list);
    return section;
  }

  function targetKey(check) {
    return [check?.target_type || 'target', check?.target_entity_id || check?.target_value || 'unknown'].join(':');
  }

  function checkMeta(check) {
    const parts = [String(check?.policy_level || ''), `${Number(check?.evidence_count || 0)} evidence`];
    if (Number(check?.unavailable_evidence_count || 0) > 0) {
      parts.push(`${Number(check.unavailable_evidence_count)} unavailable`);
    }
    if (check?.last_evidence_at) parts.push(`last ${displayDate(check.last_evidence_at)}`);
    return parts.filter(Boolean).join(' · ');
  }

  function actionLabel(check) {
    const [kind, actionId] = String(check?.recommended_action_key || '').split(':', 2);
    if (!actionId) return 'Run recommended action';
    if (kind === 'workflow') return `Open ${actionId} workflow`;
    const labels = {
      curl: 'Curl',
      dalfox: 'Dalfox',
      dnsrecon: 'DNSRecon',
      httpx: 'HTTPx',
      katana: 'Katana',
      nmap: 'Nmap',
      nuclei: 'Nuclei',
      ping: 'Ping',
      schemathesis: 'Schemathesis',
    };
    return `Run ${labels[actionId] || actionId}`;
  }

  function checkActionItems(projectId, detail, check, returnFocus) {
    const definition = checkDefinition(detail, check);
    const items = [];
    if (check?.recommended_action_key) {
      items.push({
        label: actionLabel(check),
        disabled: ctx.canRunCommands?.() === false,
        action: () => act.launchRecommendedAction(projectId, check, returnFocus),
      });
    }
    if (check?.target_entity_id) {
      items.push({
        label: 'Create finding',
        disabled: ctx.canTriageFindings?.() === false,
        action: () => act.createFinding(projectId, check, definition, returnFocus),
      });
    }
    return items;
  }

  function renderCheck(projectId, detail, check, { mobile = false } = {}) {
    const definition = checkDefinition(detail, check);
    const row = makeElement('article', 'panel-row project-assessment-check-row');
    const main = makeElement('div', 'project-assessment-check-main');
    main.append(
      makeElement('div', 'project-assessment-check-title', definition?.label || check?.check_key || 'Assessment check'),
      makeElement('div', 'project-assessment-check-meta', checkMeta(check)),
    );
    const purpose = String(definition?.purpose || check?.state_reason || '');
    if (purpose) main.appendChild(makeElement('p', 'project-assessment-check-purpose', purpose));
    const nucleiRecommendation = check?.nuclei_recommendation;
    if (nucleiRecommendation?.recommended) {
      const recommendation = makeElement('div', 'project-assessment-check-recommendation');
      recommendation.append(
        badge('Recommended from saved evidence', 'blue'),
        makeElement('p', '', String(nucleiRecommendation.summary || '')),
      );
      if (nucleiRecommendation.source_truncated) {
        recommendation.appendChild(makeElement(
          'small',
          '',
          'The saved-evidence review reached its safety limit, so this recommendation may be incomplete.',
        ));
      }
      main.appendChild(recommendation);
    }
    const states = makeElement('div', 'project-assessment-check-states');
    states.appendChild(badge(checkStateLabels[check?.state] || check?.state || 'Unknown', stateTone(check?.state)));
    if (check?.state_source === 'manual') states.appendChild(badge('Manual decision'));
    if (Number(check?.unavailable_evidence_count || 0) > 0) {
      states.appendChild(badge('Evidence unavailable', 'red'));
    }
    if (mobile) {
      const button = makeElement('button', 'btn btn-secondary btn-compact', 'Check actions');
      button.type = 'button';
      const items = checkActionItems(projectId, detail, check, button);
      button.disabled = !items.length;
      ctx.bindProjectRuntimePressable?.(button, {
        onActivate: () => openActionSheet({
          title: `${definition?.label || check?.check_key || 'Assessment check'} actions`,
          items,
          container: ctx.actionSheetContainer?.() || document.body,
          returnFocus: button,
        }),
      });
      states.appendChild(button);
    } else {
      checkActionItems(projectId, detail, check, null).forEach((item) => {
        const button = makeElement('button', 'btn btn-secondary btn-compact', item.label);
        button.type = 'button';
        button.disabled = item.disabled;
        if (item.disabled) {
          button.title = item.label === 'Create finding'
            ? "View-only team members can't create findings. Switch to Personal or ask for operator access."
            : "View-only team members can't start runs. Switch to Personal or ask for operator access.";
        }
        ctx.bindProjectRuntimePressable?.(button, {
          onActivate: () => {
            const contextualItems = checkActionItems(projectId, detail, check, button);
            const current = contextualItems.find(candidate => candidate.label === item.label);
            return current?.action?.();
          },
        });
        states.appendChild(button);
      });
    }
    row.append(main, states);
    return row;
  }

  function renderTargetGroup(projectId, st, detail, checks, { mobile = false } = {}) {
    const representative = checks[0] || {};
    const key = targetKey(representative);
    const open = st.expandedTargets.has(key);
    const group = makeElement('section', 'project-assessment-target-group');
    const toggle = makeElement('button', 'control-row project-assessment-target-toggle');
    toggle.type = 'button';
    const glyph = makeElement('span', 'project-assessment-disclosure', open ? '▾' : '▸');
    const label = makeElement('span', 'project-assessment-target-label');
    label.append(
      makeElement('strong', '', representative?.target_value || representative?.target_entity_id || 'Project-wide checks'),
      makeElement('small', '', `${representative?.target_type || 'project'} · ${checks.length} check${checks.length === 1 ? '' : 's'}`),
    );
    const covered = checks.filter(check => check?.state === 'covered').length;
    const review = checks.filter(check => check?.state === 'needs_review').length;
    const counts = makeElement(
      'span',
      'project-assessment-target-counts',
      `${covered} covered${review ? ` · ${review} review` : ''}`,
    );
    toggle.append(glyph, label, counts);
    const body = makeElement('div', 'project-assessment-target-body');
    checks.forEach(check => body.appendChild(renderCheck(projectId, detail, check, { mobile })));
    bindDisclosure(toggle, {
      panel: body,
      initialOpen: open,
      hiddenClass: 'u-hidden',
      openClass: 'is-open',
      clearPressStyle: true,
      onToggle: (isOpen) => {
        glyph.textContent = isOpen ? '▾' : '▸';
        if (isOpen) st.expandedTargets.add(key);
        else st.expandedTargets.delete(key);
      },
    });
    group.append(toggle, body);
    return group;
  }

  function renderPager(projectId, st, page) {
    const total = Math.max(0, Number(page?.total || 0));
    const limit = Math.max(1, Number(page?.limit || st.limit));
    const offset = Math.max(0, Number(page?.offset || st.offset));
    if (total <= limit && offset === 0) return null;
    const pager = makeElement('div', 'project-assessment-pager');
    const previous = makeElement('button', 'btn btn-secondary btn-compact', 'Previous');
    previous.type = 'button';
    previous.disabled = offset <= 0;
    ctx.bindProjectRuntimePressable?.(previous, {
      onActivate: () => void act.setPage(projectId, Math.max(0, offset - limit)),
    });
    const status = total ? `${offset + 1}–${Math.min(offset + limit, total)} of ${total}` : '0 checks';
    const next = makeElement('button', 'btn btn-secondary btn-compact', 'Next');
    next.type = 'button';
    next.disabled = offset + limit >= total;
    ctx.bindProjectRuntimePressable?.(next, {
      onActivate: () => void act.setPage(projectId, offset + limit),
    });
    pager.append(previous, makeElement('span', '', status), next);
    return pager;
  }

  function renderChecks(projectId, st, detail, { mobile = false } = {}) {
    const section = makeElement('section', 'project-assessment-section');
    section.appendChild(sectionHeading(
      'Check worklist',
      'Expand a target to review what is covered, outstanding, excluded, or missing evidence.',
    ));
    const stateFilters = makeElement('div', 'project-assessment-state-filters');
    filterStates.forEach((value) => {
      const label = value ? checkStateLabels[value] : 'All states';
      stateFilters.appendChild(filterChip(label, st.checkState === value, () => {
        void act.setFilter(projectId, 'state', value);
      }));
    });
    section.appendChild(stateFilters);

    const page = detail?.checks || {};
    const checks = Array.isArray(page?.checks) ? page.checks : [];
    if (!checks.length) {
      section.appendChild(ctx.emptyProjectPanel(
        st.category || st.checkState
          ? 'No checks match these assessment filters.'
          : 'This assessment cycle has no checks for its saved targets.',
      ));
      return section;
    }

    const groups = new Map();
    checks.forEach((check) => {
      const key = targetKey(check);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(check);
    });
    const list = makeElement('div', 'project-assessment-target-list nice-scroll');
    list.scrollTop = st.checksScrollTop;
    list.addEventListener('scroll', () => {
      st.checksScrollTop = list.scrollTop;
    }, { passive: true });
    groups.forEach(group => list.appendChild(renderTargetGroup(
      projectId,
      st,
      detail,
      group,
      { mobile },
    )));
    section.appendChild(list);
    const pager = renderPager(projectId, st, page);
    if (pager) section.appendChild(pager);
    return section;
  }

  function errorPanel(message, retry) {
    const panel = ctx.emptyProjectPanel(message);
    const button = makeElement('button', 'btn btn-secondary btn-compact', 'Retry');
    button.type = 'button';
    ctx.bindProjectRuntimePressable?.(button, { onActivate: retry });
    panel.appendChild(button);
    return panel;
  }

  function renderContent(projectId, st, selected, { mobile = false } = {}) {
    const root = makeElement('div', `project-assessment-root${mobile ? ' is-mobile' : ''}`);
    root.dataset.projectAssessmentRoot = String(projectId || '');
    if (st.loading && !st.loaded) {
      root.appendChild(ctx.emptyProjectPanel('Loading project assessments...'));
      return root;
    }
    if (st.error && !st.loaded) {
      root.appendChild(errorPanel(st.error, () => void act.load(projectId, { force: true })));
      return root;
    }
    if (!st.assessments.length) {
      root.appendChild(renderStartCard(projectId, st));
      root.appendChild(act.renderHttpProfiles(projectId, { mobile }));
      return root;
    }

    root.appendChild(renderCycleHeader(projectId, st, selected, { mobile }));
    if (!st.assessments.some(item => item?.status === 'active')) {
      root.appendChild(renderStartCard(projectId, st));
    }
    root.appendChild(act.renderHttpProfiles(projectId, { mobile }));
    if (st.detailLoading && !st.detail) {
      root.appendChild(ctx.emptyProjectPanel('Loading assessment coverage...'));
      return root;
    }
    if (st.detailError && !st.detail) {
      root.appendChild(errorPanel(st.detailError, () => void act.loadDetail(projectId)));
      return root;
    }
    if (!st.detail) return root;
    root.append(
      renderCoverage(st.detail.rollup),
      renderAssessmentFindingWorklist(ctx, act, projectId, st, st.detail.finding_worklist),
      renderFindingDeltas(projectId, st.detail.finding_deltas),
      renderCategoryProgress(projectId, st, st.detail.category_rollups),
      renderChecks(projectId, st, st.detail, { mobile }),
    );
    if (mobile) {
      const actions = renderMobileLifecycleActions(projectId, st, selected);
      if (actions) root.appendChild(actions);
    }
    return root;
  }

  return { renderContent };
}

export { createProjectAssessmentRenderer };
