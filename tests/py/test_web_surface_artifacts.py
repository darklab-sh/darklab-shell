# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

from pathlib import Path
from unittest import mock

from services.commands.registry import CommandValidationResult
from services.runs.finalization_web_surface import append_httpx_screenshot_artifacts
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
        "workspace_max_file_mb": 1,
        "workspace_max_files": 100,
    }


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

    capped_cfg = {**cfg, "workspace_max_files": 1}
    assert append_httpx_screenshot_artifacts(base, entries, owner, cfg=capped_cfg) == base


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
            object(),
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
            object(),
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
