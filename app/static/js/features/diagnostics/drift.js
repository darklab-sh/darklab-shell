// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

export function initialize(access) {
  function appendText(parent, tag, className, text) {
    var el = document.createElement(tag);
    if (className) el.className = className;
    el.textContent = text == null || text === '' ? '—' : String(text);
    parent.appendChild(el);
    return el;
  }

  function appendCountItem(parent, name, value) {
    var item = document.createElement('span');
    item.className = 'diag-count-item';
    appendText(item, 'span', 'diag-count-name', name);
    appendText(item, 'span', 'diag-count-value', value);
    parent.appendChild(item);
  }

  function eventSummaryText(summary) {
    if (!summary) return '—';
    var entities = Array.isArray(summary.entities) ? summary.entities : [];
    var signals = Array.isArray(summary.signals) ? summary.signals : [];
    var parts = [
      'kind=' + (summary.kind || '—'),
      'role=' + (summary.role || '—'),
      'signals=' + (signals.length ? signals.join(',') : 'none'),
    ];
    if (entities.length) {
      parts.push('entities=' + entities.map(function (entity) {
        return [entity.type, entity.canonical_value].filter(Boolean).join(':');
      }).join(','));
    }
    if (summary.target) parts.push('target=' + summary.target);
    return parts.join(' · ');
  }

  function renderDriftReport(region, payload) {
    if (!region) return;
    region.replaceChildren();
    if (!payload || !payload.ok) {
      appendText(region, 'div', 'diag-empty diag-fail', payload && payload.error ? payload.error : 'Classifier drift report failed.');
      return;
    }
    var wrap = document.createElement('div');
    wrap.className = 'diag-drift-result';

    var summary = document.createElement('div');
    summary.className = 'diag-classifier-summary';
    appendCountItem(summary, 'runs', payload.runs_scanned || 0);
    appendCountItem(summary, 'lines', payload.lines_sampled || 0);
    appendCountItem(summary, 'issues', payload.issue_count || 0);
    appendCountItem(summary, 'truncated', payload.truncated_runs || 0);
    wrap.appendChild(summary);

    if (!payload.issue_count) {
      appendText(wrap, 'div', 'diag-empty diag-ok', 'No classifier drift found in the sampled output.');
      region.appendChild(wrap);
      return;
    }

    var bucketsWrap = document.createElement('div');
    bucketsWrap.className = 'diag-drift-buckets';
    (Array.isArray(payload.buckets) ? payload.buckets : []).forEach(function (bucket) {
      var details = document.createElement('details');
      details.className = 'diag-drift-bucket';
      details.open = true;
      var summaryRow = document.createElement('summary');
      appendText(summaryRow, 'span', '', bucket.label || bucket.key);
      appendText(summaryRow, 'span', 'diag-count-value', bucket.count || 0);
      details.appendChild(summaryRow);

      var table = document.createElement('table');
      table.className = 'diag-table';
      (Array.isArray(bucket.samples) ? bucket.samples : []).forEach(function (sample) {
        var row = document.createElement('tr');
        var textCell = document.createElement('td');
        textCell.className = 'diag-drift-sample-text';
        appendText(textCell, 'div', '', sample.text || '—');
        appendText(textCell, 'div', 'diag-muted', sample.command || '—');
        row.appendChild(textCell);

        var storedCell = document.createElement('td');
        appendText(storedCell, 'div', 'diag-muted', 'stored');
        appendText(storedCell, 'div', '', eventSummaryText(sample.stored));
        row.appendChild(storedCell);

        var currentCell = document.createElement('td');
        appendText(currentCell, 'div', 'diag-muted', 'current');
        appendText(currentCell, 'div', '', eventSummaryText(sample.current));
        row.appendChild(currentCell);

        var actionCell = document.createElement('td');
        var inspect = document.createElement('button');
        inspect.className = 'btn btn-secondary btn-compact';
        inspect.type = 'button';
        inspect.textContent = 'Inspect';
        inspect.dataset.diagDriftInspect = 'true';
        inspect.dataset.command = sample.command || '';
        inspect.dataset.line = sample.text || '';
        actionCell.appendChild(inspect);
        row.appendChild(actionCell);
        table.appendChild(row);
      });
      details.appendChild(table);
      bucketsWrap.appendChild(details);
    });
    wrap.appendChild(bucketsWrap);
    region.appendChild(wrap);
  }

  document.addEventListener('submit', async function (event) {
    var form = event.target && event.target.matches && event.target.matches('[data-diag-drift-form]')
      ? event.target
      : null;
    if (!form) return;
    event.preventDefault();
    var card = form.closest('[data-diag-drift-report]');
    var region = card ? card.querySelector('.diag-drift-result-region') : null;
    var submit = form.querySelector('[type="submit"]');
    if (card) card.classList.add('is-loading');
    if (submit) submit.disabled = true;
    try {
      var params = new URLSearchParams(new FormData(form));
      var resp = await access.fetch('/diag/classifier-drift?' + params.toString(), {
        cache: 'no-store',
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      });
      if (!resp.ok) throw new Error(String(resp.status));
      renderDriftReport(region, await resp.json());
      if (card) card.classList.add('has-results');
      form.classList.remove('is-dirty');
    } catch (_) {
      if (region) appendText(region, 'div', 'diag-empty diag-fail', 'Classifier drift report failed.');
    } finally {
      if (card) card.classList.remove('is-loading');
      if (submit) submit.disabled = false;
    }
  });

  document.addEventListener('click', function (event) {
    var button = event.target && event.target.closest
      ? event.target.closest('[data-diag-drift-inspect]')
      : null;
    if (!button) return;
    var form = document.querySelector('[data-diag-classifier-form]');
    if (!form) return;
    event.preventDefault();
    if (form.elements.classifier_command) form.elements.classifier_command.value = button.dataset.command || '';
    if (form.elements.classifier_line) form.elements.classifier_line.value = button.dataset.line || '';
    if (form.elements.classifier_cls) form.elements.classifier_cls.value = '';
    if (form.elements.classifier_cmd_type) form.elements.classifier_cmd_type.value = 'real';
    form.classList.add('is-dirty');
    form.scrollIntoView({ block: 'start', behavior: 'smooth' });
    form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
  });
}
