# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

from core.output_signals import SIGNAL_SCOPES
from services.runs.output_model import LineSignal


def test_output_signal_scopes_are_covered_by_line_signal_enum():
    assert set(SIGNAL_SCOPES) == {signal.value for signal in LineSignal}
