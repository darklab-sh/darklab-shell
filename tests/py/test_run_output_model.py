import json
from pathlib import Path

from services.runs.output_model import (
    LINE_EVENT_SCHEMA_VERSION,
    LineEntity,
    LineEvent,
    LineKind,
    LineNoiseKind,
    LineRole,
    LineSignal,
    event_search_text,
    from_wire,
    is_noise_event,
    legacy_cls_for_event,
    noise_kind_for_event,
    to_legacy_wire,
    to_wire,
)


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "run_output_legacy_cls.json"


def test_v1_payload_round_trips_losslessly():
    payload = {
        "text": "443/tcp open https",
        "cls": "notice",
        "tsC": "12:00:00",
        "tsE": "+0.1s",
        "signals": ["findings"],
        "line_index": 7,
        "command_root": "nmap",
        "target": "darklab.sh",
        "entities": [{
            "type": "domain",
            "value": "darklab.sh",
            "canonical_value": "darklab.sh",
            "confidence": "high",
            "source_line": 7,
            "start": 14,
            "end": 24,
        }],
        "v": LINE_EVENT_SCHEMA_VERSION,
        "kind": "notice",
        "role": "body",
    }

    assert to_wire(from_wire(payload)) == payload


def test_legacy_payload_decodes_and_upgrades_predictably():
    payload = {
        "text": "$ nmap darklab.sh",
        "cls": "prompt-echo",
        "tsC": "12:00:00",
        "tsE": "+0.0s",
        "line_index": 0,
    }

    event = from_wire(payload)
    assert event.kind is LineKind.info
    assert event.role is LineRole.prompt_echo

    upgraded = to_wire(event)
    assert upgraded == {
        **payload,
        "v": LINE_EVENT_SCHEMA_VERSION,
        "kind": "info",
        "role": "prompt-echo",
    }


def test_unknown_legacy_cls_survives_compatibility_round_trip():
    payload = {
        "text": "sample row",
        "cls": "builtin-help-row builtin-tour-sample",
        "tsC": "",
        "tsE": "",
    }

    event = from_wire(payload)

    assert event.kind is LineKind.info
    assert event.role is LineRole.help_row
    assert to_wire(event) == {
        **payload,
        "v": LINE_EVENT_SCHEMA_VERSION,
        "kind": "info",
        "role": "help-row",
    }


def test_legacy_writer_preserves_current_key_order():
    event = LineEvent(
        text="line",
        kind=LineKind.notice,
        role=LineRole.body,
        ts_clock="12:00:00",
        ts_elapsed="+0.1s",
        signals=(LineSignal.findings,),
        line_index=2,
        command_root="nmap",
        target="darklab.sh",
        entities=(LineEntity("domain", "darklab.sh", "darklab.sh", "high", 2, 0, 10),),
    )

    legacy = to_legacy_wire(event)
    assert list(legacy) == ["text", "cls", "tsC", "tsE", "signals", "line_index", "command_root", "target", "entities"]
    assert legacy["cls"] == "notice"


def test_legacy_cls_fixture_maps_to_one_kind_role_pair():
    rows = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    for row in rows:
        event = from_wire({"text": "x", "cls": row["cls"], "tsC": "", "tsE": ""})
        assert event.kind.value == row["kind"], row
        assert event.role.value == row["role"], row


def test_kind_and_role_legacy_shims_are_independent():
    assert LineKind.from_legacy_cls("error") is LineKind.error
    assert LineRole.from_legacy_cls("error") is LineRole.body
    assert LineKind.from_legacy_cls("prompt-echo") is LineKind.info
    assert LineRole.from_legacy_cls("prompt-echo") is LineRole.prompt_echo


def test_unknown_values_fall_back_and_report_to_collector():
    unknowns = []
    payload = {
        "text": "line",
        "cls": "notice",
        "tsC": "",
        "tsE": "",
        "kind": "fatal",
        "role": "sparkle",
        "noise_kind": "future-noise",
        "signals": ["findings", "future-signal"],
    }

    event = from_wire(payload, lambda family, value: unknowns.append((family, value)))

    assert event.kind is LineKind.notice
    assert event.role is LineRole.body
    assert event.noise_kind is None
    assert event.signals == (LineSignal.findings,)
    assert unknowns == [
        ("kind", "fatal"),
        ("role", "sparkle"),
        ("noise_kind", "future-noise"),
        ("signal", "future-signal"),
    ]


def test_entity_normalisation_matches_capture_shape():
    payload = {
        "text": "entity line",
        "cls": "",
        "tsC": "",
        "tsE": "",
        "entities": [
            {
                "type": "domain",
                "value": "",
                "canonical_value": "darklab.sh",
                "confidence": "",
                "source_line": "3",
                "start": "5",
                "end": "15",
            },
            {"type": "ip", "canonical_value": "192.0.2.10", "start": 1},
            {"type": "", "canonical_value": "ignored"},
        ],
    }

    event = from_wire(payload)

    assert to_legacy_wire(event)["entities"] == [{
        "type": "domain",
        "value": "darklab.sh",
        "canonical_value": "darklab.sh",
        "confidence": "medium",
        "source_line": 3,
        "start": 5,
        "end": 15,
    }, {
        "type": "ip",
        "value": "192.0.2.10",
        "canonical_value": "192.0.2.10",
        "confidence": "medium",
    }]


def test_compatibility_cls_prefers_role_when_both_axes_are_non_default():
    event = LineEvent(text="prompt failed", kind=LineKind.error, role=LineRole.prompt_echo)

    assert legacy_cls_for_event(event) == "prompt-echo"
    assert to_wire(event)["kind"] == "error"


def test_event_search_text_is_event_text_for_phase_zero():
    assert event_search_text(LineEvent(text="search me")) == "search me"

    progress = LineEvent(text="progress", role=LineRole.progress)
    assert event_search_text(progress) == ""
    assert noise_kind_for_event(progress) is LineNoiseKind.progress
    assert is_noise_event(progress)
    assert to_wire(progress)["noise_kind"] == "progress"

    finding_progress = LineEvent(text="finding", role=LineRole.progress, signals=(LineSignal.findings,))
    assert event_search_text(finding_progress) == "finding"
    assert noise_kind_for_event(finding_progress) is None
    assert not is_noise_event(finding_progress)
