// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

export function initialize(access) {
  let loading = false;
  document.addEventListener('click', async event => {
    const link = event.target.closest?.('a[href^="/diag/audit/export"]');
    if (!link || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    if (loading || !access.active) return;
    loading = true;
    link.setAttribute('aria-busy', 'true');
    try {
      const response = await access.fetch(link.href);
      if (!response.ok) throw new Error('Export failed');
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const download = document.createElement('a');
      download.href = url;
      download.download = new URL(link.href).searchParams.get('format') === 'json' ? 'audit-events.json' : 'audit-events.csv';
      document.body.append(download);
      download.click();
      download.remove();
      setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch {
      if (access.active) {
        let status = document.querySelector('[data-audit-export-status]');
        if (!status) {
          status = document.createElement('p');
          status.dataset.auditExportStatus = '';
          status.setAttribute('role', 'status');
          document.querySelector('.diag-audit-main')?.append(status);
        }
        status.textContent = 'The export could not be completed. Try again.';
      }
    } finally {
      loading = false;
      link.removeAttribute('aria-busy');
    }
  });
}
