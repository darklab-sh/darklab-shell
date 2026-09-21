// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

export function initialize() {
  var cmdCellSelector = '.diag-cmd-cell';
  function toggleCmdCell(cell) {
    var expanded = cell.classList.toggle('expanded');
    cell.setAttribute('aria-expanded', expanded ? 'true' : 'false');
  }
  document.addEventListener('click', function (event) {
    var cell = event.target && event.target.closest
      ? event.target.closest(cmdCellSelector)
      : null;
    if (cell) toggleCmdCell(cell);
  });
  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    var cell = event.target && event.target.closest
      ? event.target.closest(cmdCellSelector)
      : null;
    if (!cell) return;
    event.preventDefault();
    toggleCmdCell(cell);
  });
}
