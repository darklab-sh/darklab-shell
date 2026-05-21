import re
from pathlib import Path

from services.runs.output_model import LINE_KIND_VALUES, LINE_ROLE_VALUES, LINE_SIGNAL_VALUES


ROOT_DIR = Path(__file__).resolve().parents[2]
JS_MODEL = ROOT_DIR / "app" / "static" / "js" / "core" / "run_output_model.js"


def _js_array(name: str) -> set[str]:
    source = JS_MODEL.read_text(encoding="utf-8")
    match = re.search(rf"const {name} = Object\.freeze\(\[([^\]]*)\]\);", source, re.S)
    assert match, f"{name} was not found in {JS_MODEL}"
    return set(re.findall(r"'([^']+)'", match.group(1)))


def test_python_and_js_line_event_enum_values_match():
    assert _js_array("LINE_KIND_VALUES") == set(LINE_KIND_VALUES)
    assert _js_array("LINE_ROLE_VALUES") == set(LINE_ROLE_VALUES)
    assert _js_array("LINE_SIGNAL_VALUES") == set(LINE_SIGNAL_VALUES)
