// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

const CHANGE_STATES = Object.freeze([
  ['regressed', 'Regressed', 'badge-tone-red'],
  ['new', 'New', 'badge-tone-amber'],
  ['persistent', 'Persistent', 'badge-tone-muted'],
  ['not_observed', 'Not observed', 'badge-tone-muted'],
  ['incomparable', 'Incomparable', 'badge-tone-muted'],
]);

function count(value) {
  const parsed = Number(value || 0);
  return Number.isFinite(parsed) ? parsed.toLocaleString() : '0';
}

function comparisonSummary(comparison = {}) {
  const status = String(comparison.status || 'pending');
  const total = Number(comparison.total_checks || 0);
  const comparable = Number(comparison.comparable_checks || 0);
  const noBaseline = Number(comparison.no_baseline_checks || 0);
  const incompatible = Number(comparison.incomparable_checks || 0);
  if (status === 'pending') return 'Comparison pending';
  if (status === 'comparable') return `${count(comparable)} comparable check${comparable === 1 ? '' : 's'}`;
  if (status === 'no_baseline') return `${count(noBaseline)} check${noBaseline === 1 ? '' : 's'} without a baseline`;
  return [
    `${count(comparable)} of ${count(total)} checks comparable`,
    noBaseline ? `${count(noBaseline)} without a baseline` : '',
    incompatible ? `${count(incompatible)} incompatible` : '',
  ].filter(Boolean).join(' · ');
}

function renderProjectFindingChangesSummary({
  changes,
  projectId = '',
  onOpenAssessment,
  bindPressable,
  mobile = false,
} = {}) {
  if (!changes || typeof changes !== 'object') return null;
  const assessment = changes.assessment && typeof changes.assessment === 'object'
    ? changes.assessment
    : {};
  const rollup = changes.rollup && typeof changes.rollup === 'object' ? changes.rollup : {};
  const section = document.createElement('section');
  section.className = `project-finding-changes-summary${mobile ? ' is-mobile' : ''}`;
  section.dataset.projectFindingChanges = String(assessment.id || '');

  const heading = document.createElement('div');
  heading.className = 'project-finding-changes-heading';
  const copy = document.createElement('div');
  copy.className = 'project-finding-changes-copy';
  const title = document.createElement('h3');
  title.textContent = 'Finding changes';
  const meta = document.createElement('p');
  meta.textContent = [
    String(assessment.title || 'Assessment cycle'),
    String(assessment.status || ''),
    comparisonSummary(changes.comparison),
  ].filter(Boolean).join(' · ');
  copy.append(title, meta);
  heading.appendChild(copy);

  const assessmentId = String(assessment.id || '');
  if (assessmentId && typeof onOpenAssessment === 'function') {
    const open = document.createElement('button');
    open.type = 'button';
    open.className = 'btn btn-secondary btn-compact';
    open.textContent = 'Open Assessment';
    open.dataset.projectFindingChangesAssessment = assessmentId;
    const activate = (event) => {
      event.preventDefault();
      onOpenAssessment(String(projectId || ''), { assessmentId });
    };
    if (typeof bindPressable === 'function') {
      bindPressable(open, { onActivate: activate });
    } else {
      open.addEventListener('click', activate);
    }
    heading.appendChild(open);
  }

  const badges = document.createElement('div');
  badges.className = 'project-finding-changes-rollup';
  CHANGE_STATES.forEach(([key, label, tone]) => {
    const badge = document.createElement('span');
    badge.className = `badge ${tone}`;
    badge.dataset.findingChangeState = key;
    badge.textContent = `${label}: ${count(rollup[key])}`;
    badges.appendChild(badge);
  });

  const note = document.createElement('p');
  note.className = 'project-finding-changes-note';
  note.textContent = Number(rollup.total || 0)
    ? 'Counts are distinct remediation groups, not evidence observations.'
    : 'No remediation groups have been compared for this cycle yet.';
  section.append(heading, badges, note);
  return section;
}

export { comparisonSummary, renderProjectFindingChangesSummary };
