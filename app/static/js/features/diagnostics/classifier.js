// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

export function initialize(access) {
  var CLASSIFIER_KEYS = [
    'classifier_command',
    'classifier_cls',
    'classifier_cmd_type',
    'classifier_line',
  ];

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

  function appendTableRow(table, label, valueNode) {
    var row = document.createElement('tr');
    appendText(row, 'td', '', label);
    var valueCell = document.createElement('td');
    valueCell.appendChild(valueNode);
    row.appendChild(valueCell);
    table.appendChild(row);
  }

  function renderClassifierResult(region, payload) {
    if (!region) return;
    region.replaceChildren();
    if (!payload || !payload.submitted) return;
    if (!payload.result) {
      appendText(region, 'div', 'diag-empty', 'Paste one output line to inspect.');
      return;
    }

    var result = payload.result;
    var wrap = document.createElement('div');
    wrap.className = 'diag-classifier-result';

    var summary = document.createElement('div');
    summary.className = 'diag-classifier-summary';
    appendCountItem(summary, 'kind', result.kind);
    appendCountItem(summary, 'role', result.role);
    appendCountItem(summary, 'root', result.command_root);
    appendCountItem(summary, 'target', result.target);
    wrap.appendChild(summary);

    var table = document.createElement('table');
    table.className = 'diag-table';

    var signalCell = document.createElement('span');
    if (Array.isArray(result.signals) && result.signals.length) {
      signalCell.className = 'diag-chips';
      result.signals.forEach(function (signal) {
        appendText(signalCell, 'span', 'diag-chip present', signal);
      });
    } else {
      appendText(signalCell, 'span', 'diag-muted', 'none');
    }
    appendTableRow(table, 'signals', signalCell);

    var entityCell;
    if (Array.isArray(result.entities) && result.entities.length) {
      entityCell = document.createElement('div');
      entityCell.className = 'diag-count-list';
      result.entities.forEach(function (entity) {
        var item = document.createElement('span');
        item.className = 'diag-count-item';
        appendText(item, 'span', 'diag-count-name', entity && entity.type);
        appendText(item, 'span', 'diag-count-value', entity && entity.canonical_value);
        entityCell.appendChild(item);
      });
    } else {
      entityCell = document.createElement('span');
      entityCell.className = 'diag-muted';
      entityCell.textContent = 'none';
    }
    appendTableRow(table, 'entities', entityCell);

    var code = document.createElement('code');
    code.textContent = result.normalized_text || '—';
    appendTableRow(table, 'normalized', code);

    wrap.appendChild(table);
    region.appendChild(wrap);
  }

  function syncClassifierUrl(form, clear) {
    if (!window.history || typeof window.history.replaceState !== 'function') return;
    var params = new URLSearchParams(window.location.search);
    params.delete('format');
    CLASSIFIER_KEYS.forEach(function (key) { params.delete(key); });
    if (!clear) {
      var data = new FormData(form);
      CLASSIFIER_KEYS.forEach(function (key) {
        var value = data.get(key);
        if (value != null && String(value).trim()) params.set(key, value);
      });
      if (!params.has('classifier_cmd_type')) {
        params.set('classifier_cmd_type', data.get('classifier_cmd_type') || 'real');
      }
    }
    var query = params.toString();
    window.history.replaceState(null, '', window.location.pathname + (query ? '?' + query : ''));
  }

  document.addEventListener('submit', async function (event) {
    var form = event.target && event.target.matches && event.target.matches('[data-diag-classifier-form]')
      ? event.target
      : null;
    if (!form) return;
    event.preventDefault();
    var card = form.closest('.diag-classifier-inspector');
    var region = card ? card.querySelector('.diag-classifier-result-region') : null;
    var submit = form.querySelector('[type="submit"]');
    form.classList.add('is-loading');
    form.setAttribute('aria-busy', 'true');
    if (submit) submit.disabled = true;
    try {
      var params = new URLSearchParams(new FormData(form));
      var resp = await access.fetch('/diag/classifier-inspector?' + params.toString(), {
        cache: 'no-store',
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      });
      if (!resp.ok) throw new Error(String(resp.status));
      renderClassifierResult(region, await resp.json());
      form.classList.remove('is-dirty');
      syncClassifierUrl(form, false);
    } catch (_) {
      if (region) appendText(region, 'div', 'diag-empty diag-fail', 'Classifier inspection failed.');
    } finally {
      form.classList.remove('is-loading');
      form.removeAttribute('aria-busy');
      if (submit) submit.disabled = false;
    }
  });

  document.addEventListener('click', function (event) {
    var clear = event.target && event.target.closest
      ? event.target.closest('[data-diag-classifier-clear]')
      : null;
    if (!clear) return;
    var card = clear.closest('.diag-classifier-inspector');
    var form = card ? card.querySelector('[data-diag-classifier-form]') : null;
    if (!form) return;
    event.preventDefault();
    CLASSIFIER_KEYS.forEach(function (key) {
      var field = form.elements[key];
      if (!field) return;
      field.value = key === 'classifier_cmd_type' ? 'real' : '';
    });
    var region = card.querySelector('.diag-classifier-result-region');
    if (region) region.replaceChildren();
    form.classList.remove('is-dirty');
    var advanced = form.querySelector('.diag-classifier-advanced');
    if (advanced) advanced.open = false;
    syncClassifierUrl(form, true);
  });
}
