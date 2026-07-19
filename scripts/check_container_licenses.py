#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Compatibility entrypoint for the container license checker."""

import os
from pathlib import Path
import sys


implementation = Path(__file__).resolve().parent / "release/check_container_licenses.py"
os.execv(sys.executable, [sys.executable, str(implementation), *sys.argv[1:]])
