// SPDX-FileCopyrightText: 2026 mmayhew
// SPDX-License-Identifier: AGPL-3.0-only

import { initializeConsole } from './features/admin/operator_console.js';
import { createOperatorAccess } from './features/admin/operator_access.js';

const root = document.getElementById('admin-console');
const access = createOperatorAccess({ root });
initializeConsole(root, { fetcher: access.fetch });
access.start();
