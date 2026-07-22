#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Compatibility entrypoint for the release payload builder."""

import os
from pathlib import Path
import sys


implementation = Path(__file__).resolve().parent / "release/build_release_payload.py"
os.execv(sys.executable, [sys.executable, str(implementation), *sys.argv[1:]])
