// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

export function initialize(access) {
  var INTERVAL_MS = 10000;
  var inFlight = false;
  var indicator = document.querySelector('.diag-live-indicator');

  function shouldDeferDiagRefresh() {
    if (!access.active || document.visibilityState !== 'visible') return true;
    if (document.querySelector(
      '.diag-classifier-form.is-dirty, .diag-classifier-form.is-loading, '
      + '.diag-drift-report.is-loading, .diag-drift-form.is-dirty, '
      + '.diag-ai-panel.is-loading'
    )) return true;
    return !!(
      document.activeElement
      && document.activeElement.closest
      && document.activeElement.closest('.diag-classifier-form, .diag-drift-form, .diag-ai-panel')
    );
  }

  async function refreshDiag() {
    if (inFlight || shouldDeferDiagRefresh()) return;
    inFlight = true;
    if (indicator) indicator.classList.add('refreshing');
    try {
      var resp = await access.fetch('/diag' + window.location.search, {
        cache: 'no-store',
        credentials: 'same-origin',
      });
      if (!resp.ok) return;
      var html = await resp.text();
      if (shouldDeferDiagRefresh()) return;
      var doc = new DOMParser().parseFromString(html, 'text/html');
      var newMain = doc.querySelector('.diag-main');
      var oldMain = document.querySelector('.diag-main');
      if (newMain && oldMain) {
        var oldDrift = oldMain.querySelector('[data-diag-drift-report].has-results');
        var newDrift = newMain.querySelector('[data-diag-drift-report]');
        if (oldDrift && newDrift) newDrift.replaceWith(oldDrift);
        // Keep the root bound to the shared access guard across refreshes.
        oldMain.replaceChildren(...newMain.childNodes);
      }
      var newGen = doc.querySelector('.diag-refreshed-at time');
      var oldGen = document.querySelector('.diag-refreshed-at time');
      if (newGen && oldGen) {
        oldGen.textContent = newGen.textContent;
        var dt = newGen.getAttribute('datetime');
        if (dt) oldGen.setAttribute('datetime', dt);
      }
    } catch (_) {
      // Soft-fail: the next interval will try again.
    } finally {
      inFlight = false;
      if (indicator) indicator.classList.remove('refreshing');
    }
  }

  setInterval(refreshDiag, INTERVAL_MS);
  document.addEventListener('visibilitychange', function () {
    // Refresh immediately when the tab becomes visible again so the
    // operator does not stare at a stale snapshot for up to 10s.
    if (document.visibilityState === 'visible') refreshDiag();
  });
  document.addEventListener('input', function (event) {
    var form = event.target && event.target.closest
      ? event.target.closest('.diag-classifier-form, .diag-drift-form')
      : null;
    if (form) form.classList.add('is-dirty');
  });
}
