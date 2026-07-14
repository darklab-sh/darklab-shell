# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

import json
import re
from pathlib import Path

from services.runs.output_model import (
    LINE_KIND_VALUES,
    LINE_NOISE_KIND_VALUES,
    LINE_ROLE_VALUES,
    LINE_SIGNAL_VALUES,
    from_wire,
)


ROOT_DIR = Path(__file__).resolve().parents[2]
JS_MODEL = ROOT_DIR / "app" / "static" / "js" / "core" / "run_output_model.js"
LEGACY_CLS_FIXTURE = ROOT_DIR / "tests" / "py" / "fixtures" / "run_output_legacy_cls.json"


def _js_array(name: str) -> set[str]:
    source = JS_MODEL.read_text(encoding="utf-8")
    match = re.search(rf"const {name} = Object\.freeze\(\[([^\]]*)\]\);", source, re.S)
    assert match, f"{name} was not found in {JS_MODEL}"
    return set(re.findall(r"'([^']+)'", match.group(1)))


def test_python_and_js_line_event_enum_values_match():
    assert _js_array("LINE_KIND_VALUES") == set(LINE_KIND_VALUES)
    assert _js_array("LINE_NOISE_KIND_VALUES") == set(LINE_NOISE_KIND_VALUES)
    assert _js_array("LINE_ROLE_VALUES") == set(LINE_ROLE_VALUES)
    assert _js_array("LINE_SIGNAL_VALUES") == set(LINE_SIGNAL_VALUES)


def test_python_legacy_class_fixture_matches_line_event_decoder():
    rows = json.loads(LEGACY_CLS_FIXTURE.read_text(encoding="utf-8"))

    for row in rows:
        event = from_wire({"text": "sample", "cls": row["cls"], "tsC": "", "tsE": ""})
        assert event.kind.value == row["kind"]
        assert event.role.value == row["role"]
