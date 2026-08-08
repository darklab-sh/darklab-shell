# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from pathlib import Path
import sqlite3
from unittest import mock

from services.commands.registry import CommandValidationResult
from services.runs.finalization_web_surface import append_httpx_screenshot_artifacts
from services.runs.finalization_web_surface_query import load_protected_workspace_paths
from services.runs.finalization_artifacts import save_run_file_artifacts_for_finalize
from services.runs.httpx_workspace_artifact_metadata import (
    HTTPX_SCREENSHOT_DIRECTORY,
)
from services.runs.workspace_artifact_metadata import workspace_artifact_metadata
from services.teams.scope import personal_owner_context
from services.workspace.files import ensure_owner_workspace


def _cfg(tmp_path: Path) -> dict[str, object]:
    return {
        "workspace_enabled": True,
        "workspace_root": str(tmp_path / "workspaces"),
        "workspace_quota_mb": 1,
        "workspace_max_file_mb": 1,
        "workspace_max_files": 100,
    }


def _artifact_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE runs (id TEXT PRIMARY KEY, team_id TEXT NOT NULL DEFAULT '')")
    conn.execute(
        "CREATE TABLE run_file_artifacts ("
        "id TEXT PRIMARY KEY, session_id TEXT NOT NULL, run_id TEXT NOT NULL, workspace_path TEXT NOT NULL)"
    )
    return conn


def test_httpx_screenshot_directory_metadata_requires_one_validated_output():
    validation = CommandValidationResult(
        allowed=True,
        display_command="httpx -json -screenshot -srd shots",
        exec_command="httpx -json -screenshot -srd /workspace/owner/shots",
        workspace_writes=["shots"],
    )

    assert workspace_artifact_metadata(validation) == {
        "shots": {
            "structured_output": HTTPX_SCREENSHOT_DIRECTORY,
            "source_flag": "-srd",
        },
    }
    assert workspace_artifact_metadata(CommandValidationResult(
        allowed=True,
        display_command="httpx -json -srd shots",
        exec_command="httpx -json -srd /workspace/owner/shots",
        workspace_writes=["shots"],
    )) == {}


def test_httpx_screenshot_artifacts_are_bounded_to_verified_image_children(tmp_path):
    cfg = _cfg(tmp_path)
    owner = personal_owner_context("web-surface-artifacts")
    root = ensure_owner_workspace(owner, cfg)
    shots = root / "shots"
    shots.mkdir()
    (shots / "app.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"image")
    (shots / "photo.jpg").write_bytes(b"\xff\xd8\xff" + b"photo")
    (shots / "oversized.jpg").write_bytes(b"\xff\xd8\xff" + (b"x" * 1_048_574))
    (shots / "not-image.png").write_bytes(b"not an image")
    (root / "outside.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"outside")
    (shots / "linked.png").symlink_to(root / "outside.png")
    base = [{
        "workspace_path": "shots",
        "display_name": "shots",
        "kind": "output",
        "detected_by": "workspace_flag",
        "structured_output": HTTPX_SCREENSHOT_DIRECTORY,
        "source_flag": "-srd",
    }]
    entries = [{"source_detail": {"screenshots": [
        {"artifact_path": "shots/app.png"},
        {"artifact_path": "shots/app.png"},
        {"artifact_path": "shots/photo.jpg"},
        {"artifact_path": "shots/oversized.jpg"},
        {"artifact_path": "shots/not-image.png"},
        {"artifact_path": "outside.png"},
        {"artifact_path": "shots/linked.png"},
        {"artifact_path": "shots/../outside.png"},
    ]}}]

    artifacts = append_httpx_screenshot_artifacts(base, entries, owner, cfg=cfg)

    assert artifacts == [
        base[0],
        {
            "workspace_path": "shots/app.png",
            "display_name": "app.png",
            "kind": "screenshot",
            "byte_size": 13,
            "detected_by": "httpx_screenshot",
            "content_type": "image/png",
            "preview_type": "image",
        },
        {
            "workspace_path": "shots/photo.jpg",
            "display_name": "photo.jpg",
            "kind": "screenshot",
            "byte_size": 8,
            "detected_by": "httpx_screenshot",
            "content_type": "image/jpeg",
            "preview_type": "image",
        },
    ]
    assert (shots / "app.png").is_file()
    assert (shots / "photo.jpg").is_file()
    assert not (shots / "oversized.jpg").exists()
    assert not (shots / "not-image.png").exists()
    assert not (shots / "linked.png").exists()
    assert (root / "outside.png").is_file()

    capped_cfg = {**cfg, "workspace_max_files": 1}
    assert append_httpx_screenshot_artifacts(base, entries, owner, cfg=capped_cfg) == base
    assert not (shots / "app.png").exists()
    assert not (shots / "photo.jpg").exists()


def test_httpx_screenshot_artifacts_keep_earlier_files_and_clean_new_byte_overage(tmp_path):
    cfg = _cfg(tmp_path)
    owner = personal_owner_context("web-surface-byte-quota")
    root = ensure_owner_workspace(owner, cfg)
    shots = root / "shots"
    shots.mkdir()
    (root / "earlier.txt").write_bytes(b"e" * 300_000)
    (shots / "first.png").write_bytes(b"\x89PNG\r\n\x1a\n" + (b"a" * 399_992))
    (shots / "second.png").write_bytes(b"\x89PNG\r\n\x1a\n" + (b"b" * 399_992))
    base = [{
        "workspace_path": "shots",
        "display_name": "shots",
        "kind": "output",
        "detected_by": "workspace_flag",
        "structured_output": HTTPX_SCREENSHOT_DIRECTORY,
        "source_flag": "-srd",
    }]
    entries = [{"source_detail": {"screenshots": [
        {"artifact_path": "shots/first.png"},
        {"artifact_path": "shots/second.png"},
    ]}}]

    with mock.patch(
        "services.runs.finalization_web_surface.app_metrics.record_workspace_quota_rejection"
    ) as quota_rejection:
        artifacts = append_httpx_screenshot_artifacts(
            base,
            entries,
            owner,
            cfg=cfg,
            run_id="run-quota",
            session_id="web-surface-byte-quota",
        )

    assert [item["workspace_path"] for item in artifacts] == ["shots", "shots/first.png"]
    assert (root / "earlier.txt").is_file()
    assert (shots / "first.png").is_file()
    assert not (shots / "second.png").exists()
    quota_rejection.assert_called_once_with()


def test_httpx_screenshot_cleanup_preserves_paths_registered_by_an_earlier_owner_run(tmp_path):
    cfg = {**_cfg(tmp_path), "workspace_max_files": 1}
    owner = personal_owner_context("web-surface-protected")
    root = ensure_owner_workspace(owner, cfg)
    shots = root / "shots"
    shots.mkdir()
    (shots / "prior.png").write_bytes(b"\x89PNG\r\n\x1a\nprior")
    (shots / "new.png").write_bytes(b"\x89PNG\r\n\x1a\nnew")
    base = [{
        "workspace_path": "shots",
        "kind": "output",
        "structured_output": HTTPX_SCREENSHOT_DIRECTORY,
    }]
    entries = [{"source_detail": {"screenshots": [
        {"artifact_path": "shots/prior.png"},
        {"artifact_path": "shots/new.png"},
    ]}}]
    conn = _artifact_conn()
    conn.execute("INSERT INTO runs (id, team_id) VALUES ('run-prior', '')")
    conn.execute(
        "INSERT INTO run_file_artifacts (id, session_id, run_id, workspace_path) "
        "VALUES ('artifact-prior', 'web-surface-protected', 'run-prior', 'shots/prior.png')"
    )

    artifacts = append_httpx_screenshot_artifacts(
        base,
        entries,
        owner,
        cfg=cfg,
        run_id="run-current",
        session_id="web-surface-protected",
        conn=conn,
    )
    failed_artifacts = append_httpx_screenshot_artifacts(
        base,
        entries,
        owner,
        cfg=cfg,
        retain=False,
        run_id="run-current",
        session_id="web-surface-protected",
        conn=conn,
    )

    assert [item["workspace_path"] for item in artifacts] == ["shots", "shots/prior.png"]
    assert failed_artifacts == base
    assert (shots / "prior.png").is_file()
    assert not (shots / "new.png").exists()
    conn.close()


def test_protected_screenshot_paths_follow_personal_and_team_ownership():
    conn = _artifact_conn()
    for run_id, team_id in (
        ("personal-prior", ""),
        ("personal-current", ""),
        ("other-personal", ""),
        ("team-prior", "team-one"),
        ("other-team", "team-two"),
    ):
        conn.execute("INSERT INTO runs (id, team_id) VALUES (?, ?)", (run_id, team_id))
    for artifact_id, session_id, run_id, path in (
        ("a1", "session-one", "personal-prior", "shots/personal.png"),
        ("a2", "session-one", "personal-current", "shots/current.png"),
        ("a3", "session-two", "other-personal", "shots/other.png"),
        ("a4", "member-one", "team-prior", "shots/team.png"),
        ("a5", "member-two", "other-team", "shots/other-team.png"),
    ):
        conn.execute(
            "INSERT INTO run_file_artifacts (id, session_id, run_id, workspace_path) VALUES (?, ?, ?, ?)",
            (artifact_id, session_id, run_id, path),
        )
    candidates = [
        "shots/personal.png",
        "shots/current.png",
        "shots/other.png",
        "shots/team.png",
        "shots/other-team.png",
    ]

    assert load_protected_workspace_paths(
        conn,
        candidates,
        run_id="personal-current",
        session_id="session-one",
        team_id="",
    ) == {"shots/personal.png"}
    assert load_protected_workspace_paths(
        conn,
        candidates,
        run_id="team-current",
        session_id="member-two",
        team_id="team-one",
    ) == {"shots/team.png"}
    conn.close()


def test_httpx_screenshot_cleanup_fails_safe_when_protected_path_lookup_fails(tmp_path):
    cfg = _cfg(tmp_path)
    owner = personal_owner_context("web-surface-protected-failure")
    root = ensure_owner_workspace(owner, cfg)
    (root / "shots").mkdir()
    (root / "shots" / "capture.png").write_bytes(b"\x89PNG\r\n\x1a\nimage")
    base = [{
        "workspace_path": "shots",
        "kind": "output",
        "structured_output": HTTPX_SCREENSHOT_DIRECTORY,
    }]
    entries = [{"source_detail": {"screenshots": [{"artifact_path": "shots/capture.png"}]}}]
    failing_conn = mock.Mock()
    failing_conn.execute.side_effect = RuntimeError("database unavailable")

    with mock.patch("services.runs.finalization_web_surface.log.warning") as warning_log:
        artifacts = append_httpx_screenshot_artifacts(
            base,
            entries,
            owner,
            cfg=cfg,
            run_id="run-current",
            session_id="web-surface-protected-failure",
            conn=failing_conn,
        )

    assert [item["workspace_path"] for item in artifacts] == ["shots", "shots/capture.png"]
    assert (root / "shots" / "capture.png").is_file()
    lookup_warning = next(
        call for call in warning_log.call_args_list
        if call.args == ("HTTPX_SCREENSHOT_PROTECTED_PATH_LOOKUP_FAILED",)
    )
    assert lookup_warning.kwargs["extra"]["protected_lookup_error"] == "RuntimeError"
    assert "workspace_path" not in lookup_warning.kwargs["extra"]


def test_httpx_screenshot_artifacts_reject_ambiguous_output_directories(tmp_path):
    cfg = _cfg(tmp_path)
    owner = personal_owner_context("web-surface-ambiguous")
    root = ensure_owner_workspace(owner, cfg)
    for directory in ("one", "two"):
        (root / directory).mkdir()
    base = [{
        "workspace_path": directory,
        "kind": "output",
        "structured_output": HTTPX_SCREENSHOT_DIRECTORY,
    } for directory in ("one", "two")]

    assert append_httpx_screenshot_artifacts(base, [], owner, cfg=cfg) == base


def test_run_finalization_records_verified_httpx_screenshot_children(tmp_path):
    cfg = _cfg(tmp_path)
    owner = personal_owner_context("web-surface-finalize")
    root = ensure_owner_workspace(owner, cfg)
    (root / "shots").mkdir()
    (root / "shots" / "app.webp").write_bytes(b"RIFF\x04\x00\x00\x00WEBPdata")
    base = [{
        "workspace_path": "shots",
        "kind": "output",
        "structured_output": HTTPX_SCREENSHOT_DIRECTORY,
    }]
    entries = [{"source_detail": {"screenshots": [{"artifact_path": "shots/app.webp"}]}}]

    conn = _artifact_conn()
    with (
        mock.patch(
            "services.runs.finalization_artifacts.run_finalize_savepoint",
            side_effect=lambda _conn, _name, operation: operation(),
        ),
        mock.patch(
            "services.runs.finalization_artifacts.record_run_file_artifacts",
            side_effect=lambda _conn, _session, _run, artifacts, **_kwargs: artifacts,
        ),
    ):
        recorded = save_run_file_artifacts_for_finalize(
            conn,
            "web-surface-finalize",
            "",
            "run-httpx",
            "httpx -json -screenshot -srd shots",
            base,
            owner,
            persisted_entries=entries,
            cfg=cfg,
            workspace_artifacts_with_sizes_fn=lambda _session, artifacts: artifacts,
        )
        failed_run_artifacts = save_run_file_artifacts_for_finalize(
            conn,
            "web-surface-finalize",
            "",
            "run-httpx-failed",
            "httpx -json -screenshot -srd shots",
            base,
            owner,
            persisted_entries=entries,
            exit_code=2,
            cfg=cfg,
            workspace_artifacts_with_sizes_fn=lambda _session, artifacts: artifacts,
        )

    assert [item["workspace_path"] for item in recorded] == ["shots", "shots/app.webp"]
    assert recorded[1]["content_type"] == "image/webp"
    assert failed_run_artifacts == base
    assert not (root / "shots" / "app.webp").exists()
    conn.close()


def test_run_finalization_keeps_validated_artifacts_when_screenshot_discovery_fails():
    base = [{"workspace_path": "shots", "kind": "output"}]
    with (
        mock.patch(
            "services.runs.finalization_artifacts.append_httpx_screenshot_artifacts",
            side_effect=RuntimeError("injected"),
        ),
        mock.patch(
            "services.runs.finalization_artifacts.run_finalize_savepoint",
            side_effect=lambda _conn, _name, operation: operation(),
        ),
        mock.patch(
            "services.runs.finalization_artifacts.record_run_file_artifacts",
            side_effect=lambda _conn, _session, _run, artifacts, **_kwargs: artifacts,
        ),
        mock.patch("services.runs.finalization_artifacts.app_metrics.record_run_finalize_error") as metric,
    ):
        recorded = save_run_file_artifacts_for_finalize(
            object(),
            "web-surface-failure",
            "",
            "run-httpx",
            "httpx -json -screenshot -srd shots",
            base,
            personal_owner_context("web-surface-failure"),
            workspace_artifacts_with_sizes_fn=lambda _session, artifacts: artifacts,
        )

    assert recorded == base
    metric.assert_called_once_with("httpx_screenshot_artifacts")
