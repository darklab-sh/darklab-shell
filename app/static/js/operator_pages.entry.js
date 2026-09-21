// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { createOperatorAccess } from './features/admin/operator_access.js';
import { initialize as refresh } from './features/diagnostics/refresh.js';
import { initialize as aiTest } from './features/diagnostics/ai_test.js';
import { initialize as classifier } from './features/diagnostics/classifier.js';
import { initialize as drift } from './features/diagnostics/drift.js';
import { initialize as commandCells } from './features/diagnostics/command_cells.js';
import { initialize as auditExports } from './features/diagnostics/audit_exports.js';

const access = createOperatorAccess();
access.start();
if (document.querySelector('.diag-audit-main')) {
  auditExports(access);
} else {
  refresh(access);
  aiTest(access);
  classifier(access);
  drift(access);
  commandCells();
}
