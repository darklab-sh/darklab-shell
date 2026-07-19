#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Compatibility entrypoint for the theme example generator."""

import os
from pathlib import Path
import sys


implementation = Path(__file__).resolve().parent / "generate/generate_theme_examples.py"
os.execv(sys.executable, [sys.executable, str(implementation), *sys.argv[1:]])
