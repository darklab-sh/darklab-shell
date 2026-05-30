"""Tests for notification application hook points."""

from __future__ import annotations

from services.notifications import hooks
from services.runs.kinds import RUN_KIND_BUILTIN, RUN_KIND_EXTERNAL


def test_run_complete_hook_enqueues_external_run_summary(monkeypatch):
    captured = {}

    def fake_enqueue(trigger, payload, session_token, *, conn=None, dispatch_sync=False, run_id=None, team_id=""):
        captured.update({
            "trigger": trigger,
            "payload": payload,
            "session_token": session_token,
            "run_id": run_id,
            "team_id": team_id,
            "dispatch_sync": dispatch_sync,
        })
        return ["nte_1"]

    monkeypatch.setattr("services.notifications.hooks.dispatcher.enqueue", fake_enqueue)

    queued = hooks.enqueue_run_complete(
        run_id="run-1",
        session_id="tok_notifications",
        command="nmap -sV darklab.sh",
        exit_code=0,
        run_kind=RUN_KIND_EXTERNAL,
        finalize_summary={"finding_count": 2, "atlas_entity_count": 5, "artifact_count": 1, "project_target_count": 3},
        cfg={"share_redaction_enabled": True},
    )

    assert queued == ["nte_1"]
    assert captured["trigger"] == "run_complete"
    assert captured["session_token"] == "tok_notifications"
    assert captured["run_id"] == "run-1"
    assert captured["team_id"] == ""
    assert captured["dispatch_sync"] is False
    assert captured["payload"]["run_id"] == "run-1"
    assert captured["payload"]["command_root"] == "nmap"
    assert captured["payload"]["exit_code"] == 0
    assert captured["payload"]["summary_fields"] == {
        "artifact_count": 1,
        "finding_count": 2,
        "atlas_entity_count": 5,
        "project_target_count": 3,
    }


def test_run_complete_hook_skips_builtin_runs(monkeypatch):
    called = False

    def fake_enqueue(*args, **kwargs):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr("services.notifications.hooks.dispatcher.enqueue", fake_enqueue)

    queued = hooks.enqueue_run_complete(
        run_id="run-1",
        session_id="tok_notifications",
        command="help",
        exit_code=0,
        run_kind=RUN_KIND_BUILTIN,
        finalize_summary={"finding_count": 1},
    )

    assert queued == []
    assert called is False


def test_run_complete_hook_redacts_string_summary_fields():
    redacted = hooks._redact_summary_fields(
        {"detail": "Authorization: Bearer secret-token", "finding_count": 1},
        cfg={"share_redaction_enabled": True},
    )

    assert redacted == {"detail": "Authorization: Bearer [redacted]", "finding_count": 1}


def test_run_complete_hook_swallow_enqueue_errors(monkeypatch):
    def fake_enqueue(*args, **kwargs):
        raise RuntimeError("queue unavailable")

    logged = {}

    def fake_log_error(message, *args, **kwargs):
        logged["message"] = message
        logged["kwargs"] = kwargs

    monkeypatch.setattr("services.notifications.hooks.dispatcher.enqueue", fake_enqueue)
    monkeypatch.setattr("services.notifications.hooks.log.error", fake_log_error)

    queued = hooks.enqueue_run_complete(
        run_id="run-1",
        session_id="tok_notifications",
        command="nmap darklab.sh",
        exit_code=1,
        run_kind=RUN_KIND_EXTERNAL,
    )

    assert queued == []
    assert logged["message"] == "NOTIFICATION_RUN_COMPLETE_ENQUEUE_ERROR"
    assert logged["kwargs"]["extra"]["run_id"] == "run-1"


def test_run_complete_summary_defaults_missing_counts_to_zero():
    assert hooks._run_complete_summary({"finding_count": 4}) == {
        "artifact_count": 0,
        "finding_count": 4,
        "atlas_entity_count": 0,
        "project_target_count": 0,
    }
