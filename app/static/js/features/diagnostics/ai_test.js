// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

export function initialize(access) {
  function timingText(timings) {
    if (!timings) return '';
    var parts = [];
    if (timings.prompt_ms != null) {
      parts.push('prompt ' + Math.round(Number(timings.prompt_ms) || 0) + ' ms'
        + (timings.prompt_n != null ? ' / ' + timings.prompt_n + ' tok' : ''));
    }
    if (timings.predicted_ms != null) {
      parts.push('generation ' + Math.round(Number(timings.predicted_ms) || 0) + ' ms'
        + (timings.predicted_n != null ? ' / ' + timings.predicted_n + ' tok' : ''));
    }
    return parts.join(' · ');
  }

  function renderResult(region, payload) {
    if (!region) return;
    region.replaceChildren();
    var el = document.createElement('div');
    el.className = payload && payload.ok ? 'diag-storage-banner diag-ok' : 'diag-storage-banner diag-fail';
    if (payload && payload.ok) {
      el.textContent = 'Prompt OK'
        + (payload.latency_ms != null ? ' · ' + payload.latency_ms + ' ms' : '')
        + (timingText(payload.provider_timings) ? ' · ' + timingText(payload.provider_timings) : '')
        + (payload.payload && payload.payload.message ? ' · ' + payload.payload.message : '');
    } else {
      el.textContent = payload && payload.error ? payload.error : 'AI test prompt failed.';
    }
    region.appendChild(el);
    if (payload && payload.raw_response) {
      var pre = document.createElement('pre');
      pre.className = 'diag-ai-raw';
      pre.textContent = payload.raw_response;
      region.appendChild(pre);
    }
  }

  document.addEventListener('submit', async function (event) {
    var form = event.target && event.target.matches && event.target.matches('[data-diag-ai-test-form]')
      ? event.target
      : null;
    if (!form) return;
    event.preventDefault();
    var panel = form.closest('[data-diag-ai-panel]');
    var region = panel ? panel.querySelector('.diag-ai-test-result') : null;
    var submit = form.querySelector('[type="submit"]');
    if (panel) panel.classList.add('is-loading');
    if (submit) submit.disabled = true;
    try {
      var resp = await access.fetch(form.action, {
        method: 'POST',
        cache: 'no-store',
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      });
      var payload = await resp.json().catch(function () { return { ok: false }; });
      renderResult(region, payload);
    } catch (_) {
      renderResult(region, { ok: false, error: 'AI test prompt failed.' });
    } finally {
      if (panel) panel.classList.remove('is-loading');
      if (submit) submit.disabled = false;
    }
  });
}
