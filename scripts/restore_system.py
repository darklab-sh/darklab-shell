#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Compatibility entrypoint for the operator restore helper."""

import os
from pathlib import Path
import sys


implementation = Path(__file__).resolve().parent / "operations/restore_system.py"
os.execv(sys.executable, [sys.executable, str(implementation), *sys.argv[1:]])
