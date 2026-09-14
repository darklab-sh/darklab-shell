# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Archive authorization stops have one safe terminal outcome at every stage."""

from contextlib import nullcontext
import errno
import json
import logging
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from conftest import copy_pristine_sqlite_database, make_test_app
from core import database
from core.logging_setup import GELFFormatter, _TextFormatter, _extra_fields
from identity_helpers import principal_identity
from services.auth import export_authorization
from services.auth.background_authorization import BackgroundAuthorization, BackgroundAuthorizationState
from services.projects import export_cleanup, package_archive, package_jobs
from services.reports import jobs as report_jobs


@pytest.fixture(params=["package", "report"])
def worker(request, tmp_path, monkeypatch):
    kind = request.param
    module = package_jobs if kind == "package" else report_jobs
    job_id = ("epj_" if kind == "package" else "rpj_") + "a" * 24
    job_dir = tmp_path / kind
    monkeypatch.setattr(module, "_JOB_DIR", job_dir)
    job = {
        "id": job_id,
        "project_id": "proj_" + "b" * 16,
        "principal_id": "prn_" + "c" * 32,
        "personal_workspace_id": "wsp_" + "d" * 32,
        "originating_credential_id": "crd_" + "e" * 32,
        "package_id": "pkg_" + "f" * 16,
        "status": "queued",
        "phase": "queued",
        "draft": {"title": "private-report-title", "notes": "private-report-body"},
    }
    module._write_job(job)
    audit = Mock()
    monkeypatch.setattr(module, "_record_job_audit", audit)
    monkeypatch.setattr(export_authorization, "get_db_connect", lambda: lambda: nullcontext(None))
    if kind == "report":
        monkeypatch.setattr(
            module, "get_project", lambda *_args, **_kwargs: {"id": job["project_id"], "name": "private-project-title"}
        )
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    logger = logging.Logger("export-authorization", logging.DEBUG)
    logger.addHandler(handler)
    monkeypatch.setattr(module, "log", logger)
    monkeypatch.setattr(package_archive, "log", logger)
    monkeypatch.setattr(export_cleanup, "log", logger)
    builder_name = "build_evidence_package_archive" if kind == "package" else "build_report_export_archive"
    return SimpleNamespace(
        kind=kind,
        module=module,
        job=job,
        records=records,
        audit=audit,
        builder_name=builder_name,
        archive=job_dir / "private-archive-name.zip",
        prefix="PACKAGE_BUILD" if kind == "package" else "REPORT_EXPORT_JOB",
    )


def _assert_terminal(worker, *, stage, reason, unavailable=False, retained_archive=False):
    stored = worker.module._read_job(worker.job["id"])
    assert stored["status"] == "failed" and stored["phase"] == "authorization"
    assert stored["error_status"] == (500 if unavailable else 403)
    assert stored["authorization_reason"] == reason
    assert bool(stored.get("archive_path")) is retained_archive
    assert bool(stored.get("authorization_cleanup_pending")) is retained_archive
    assert worker.audit.call_count == 1
    suffix = "CHECK_FAILED" if unavailable else "REJECTED"
    events = [record for record in worker.records if record.msg == worker.prefix + "_AUTHORIZATION_" + suffix]
    assert len(events) == 1
    event = events[0]
    assert event.levelno == (logging.ERROR if unavailable else logging.WARNING)
    assert event.reason == reason and event.stage == stage
    assert event.job_id == worker.job["id"] and event.project_id == worker.job["project_id"]
    assert event.principal_id == worker.job["principal_id"]
    fields = {"job_id", "project_id", "principal_id", "reason", "stage"}
    if unavailable:
        fields.add("error_type")
        assert event.error_type == "OperationalError"
    assert set(_extra_fields(event)) == fields
    for record in worker.records:
        assert not record.exc_info
        assert "COMPLETE" not in record.msg
        rendered = _TextFormatter().format(record) + GELFFormatter().format(record)
        for private in (
            "private-report",
            "private-project",
            "private-archive",
            "private-denial",
            "private-database",
        ):
            assert private not in rendered
        if not unavailable:
            assert record.levelno < logging.ERROR
    assert json.loads(GELFFormatter().format(event))["_reason"] == reason


@pytest.mark.parametrize("stage", ["pre_build", "progress", "post_build"])
@pytest.mark.parametrize(
    "state", [state for state in BackgroundAuthorizationState if state != BackgroundAuthorizationState.AUTHORIZED]
)
def test_each_authorization_state_has_one_terminal_warning_at_every_checkpoint(worker, monkeypatch, stage, state):
    calls = 0
    fail_at = {"pre_build": 1, "progress": 2, "post_build": 3}[stage]

    def authorize(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return BackgroundAuthorization(
            state if calls == fail_at else BackgroundAuthorizationState.AUTHORIZED,
            message="private-denial-message",
        )

    def build(*_args, progress_callback, **_kwargs):
        progress_callback("rendering", "private-report-progress")
        worker.archive.write_bytes(b"private-report-archive")
        return {"path": str(worker.archive), "byte_size": worker.archive.stat().st_size}

    monkeypatch.setattr(export_authorization, "resolve_background_authorization", authorize)
    builder = Mock(side_effect=build)
    monkeypatch.setattr(worker.module, worker.builder_name, builder)
    worker.module._run_job(worker.job["id"], {})
    _assert_terminal(worker, stage=stage, reason=state.value)
    assert calls == fail_at
    assert builder.call_count == (0 if stage == "pre_build" else 1)
    assert not worker.archive.exists()


@pytest.mark.parametrize("stage", ["pre_build", "progress", "post_build"])
def test_authorization_storage_faults_are_terminal_server_errors(worker, monkeypatch, stage):
    calls = 0
    fail_at = {"pre_build": 1, "progress": 2, "post_build": 3}[stage]

    def authorize(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == fail_at:
            raise sqlite3.OperationalError("private-database-query-and-values")
        return BackgroundAuthorization(BackgroundAuthorizationState.AUTHORIZED)

    def build(*_args, progress_callback, **_kwargs):
        progress_callback("rendering", "private-report-progress")
        worker.archive.write_bytes(b"private-report-archive")
        return {"path": str(worker.archive), "byte_size": worker.archive.stat().st_size}

    monkeypatch.setattr(export_authorization, "resolve_background_authorization", authorize)
    monkeypatch.setattr(worker.module, worker.builder_name, build)
    worker.module._run_job(worker.job["id"], {})
    _assert_terminal(worker, stage=stage, reason="authorization_check_failed", unavailable=True)
    assert not worker.archive.exists()


def test_unexpected_exporter_failure_remains_a_server_error(worker, monkeypatch):
    monkeypatch.setattr(
        export_authorization,
        "resolve_background_authorization",
        lambda *_args, **_kwargs: BackgroundAuthorization(BackgroundAuthorizationState.AUTHORIZED),
    )
    monkeypatch.setattr(worker.module, worker.builder_name, Mock(side_effect=RuntimeError("exporter failed")))
    worker.module._run_job(worker.job["id"], {})
    assert worker.module._read_job(worker.job["id"])["error_status"] == 500
    assert not any("AUTHORIZATION_" in record.msg for record in worker.records)
    assert len([record for record in worker.records if record.levelno == logging.ERROR]) == 1


def _create_real_package(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "DB_PATH", str(copy_pristine_sqlite_database(tmp_path / "archive.db")))
    app = make_test_app()
    app.config["RATELIMIT_ENABLED"] = False
    identity = principal_identity("archive authorization logging")
    client = app.test_client()
    response = client.post("/projects", headers=identity.browser_headers(), json={"name": "private-project-title"})
    assert response.status_code == 201
    project = response.get_json()["project"]
    response = client.post(
        f"/projects/{project['id']}/packages",
        headers=identity.browser_headers(),
        json={"name": "private-package-title", "include_artifacts": False},
    )
    assert response.status_code == 201
    package = response.get_json()["package"]
    return identity, project, package


@pytest.mark.parametrize("phase", ["core", "finalizing", "complete"])
@pytest.mark.parametrize("unavailable", [False, True])
def test_real_package_builder_preserves_authorization_outcome_and_removes_partial_archive(
    tmp_path, monkeypatch, phase, unavailable
):
    identity, project, package = _create_real_package(tmp_path, monkeypatch)
    archive_dir = tmp_path / "private-archives"
    archive_dir.mkdir()
    records = []
    handler = logging.Handler()
    handler.emit = records.append
    logger = logging.Logger("package-progress-authorization", logging.DEBUG)
    logger.addHandler(handler)
    monkeypatch.setattr(package_archive, "log", logger)
    error = (
        export_authorization.ExportAuthorizationUnavailable("OperationalError")
        if unavailable
        else export_authorization.ExportAuthorizationRejected(
            BackgroundAuthorization(BackgroundAuthorizationState.PRINCIPAL_DISABLED, message="private-denial-message"),
        )
    )

    def progress(current_phase, _message):
        if current_phase == phase:
            raise error

    with pytest.raises(type(error)) as caught:
        package_archive.build_evidence_package_archive(
            identity.personal_workspace_id,
            project["id"],
            package["id"],
            progress_callback=progress,
            archive_dir=str(archive_dir),
        )
    assert caught.value is error
    assert not list(archive_dir.glob("*.zip"))
    assert all(record.levelno < logging.ERROR for record in records)
    assert not any(record.msg == "PACKAGE_BUILD_COMPLETED" for record in records)


@pytest.mark.parametrize("worker", ["package"], indirect=True)
@pytest.mark.parametrize("phase", ["core", "complete"])
def test_live_principal_disablement_stops_the_real_package_worker_once(worker, tmp_path, monkeypatch, phase):
    from core.database_access import get_db_connect
    from services.auth import storage

    identity, project, package = _create_real_package(tmp_path, monkeypatch)
    monkeypatch.setattr(export_authorization, "get_db_connect", get_db_connect)
    worker.job.update(
        {
            "principal_id": identity.principal_id,
            "personal_workspace_id": identity.personal_workspace_id,
            "project_id": project["id"],
            "package_id": package["id"],
        }
    )
    worker.module._write_job(worker.job)
    worker.records.clear()

    def build(*args, progress_callback, **kwargs):
        def progress(current_phase, message):
            if current_phase == phase:
                storage.disable_principal(identity.principal_id, reason="operator stop")
            progress_callback(current_phase, message)

        return package_archive.build_evidence_package_archive(*args, progress_callback=progress, **kwargs)

    monkeypatch.setattr(worker.module, worker.builder_name, build)
    worker.module._run_job(worker.job["id"], {})
    _assert_terminal(worker, stage="progress", reason="principal_disabled")
    assert not list(worker.module._JOB_DIR.glob("*.zip"))


def _cleanup_events(worker, stage, error_type, error_number):
    events = [record for record in worker.records if record.msg == "EXPORT_REVOKED_ARCHIVE_CLEANUP_FAILED"]
    assert len(events) == 1
    record = events[0]
    assert record.levelno == logging.WARNING and not record.exc_info
    assert _extra_fields(record) == {
        "job_id": worker.job["id"], "job_kind": worker.kind, "stage": stage,
        "error_type": error_type, "errno": error_number,
    }
    rendered = _TextFormatter().format(record) + GELFFormatter().format(record)
    assert "private" not in rendered
    assert str(worker.archive) not in rendered


def _download_result(worker):
    if worker.kind == "package":
        return worker.module.evidence_package_archive_for_job(
            worker.job["personal_workspace_id"], worker.job["project_id"], worker.job["package_id"], worker.job["id"],
        )
    return worker.module.report_export_archive_for_job(
        worker.job["personal_workspace_id"], worker.job["project_id"], worker.job["id"],
    )


def _cleanup_retry(worker, *, discard=False):
    if discard:
        method = "discard_evidence_package_archive_job" if worker.kind == "package" else "discard_report_export_job"
        getattr(worker.module, method)(worker.job["id"])
    else:
        method = "cleanup_evidence_package_archive_jobs" if worker.kind == "package" else "cleanup_report_export_jobs"
        old = worker.module._now().timestamp() - worker.module._JOB_TTL.total_seconds() - 60
        os.utime(worker.module._job_path(worker.job["id"]), (old, old))
        getattr(worker.module, method)()


@pytest.mark.parametrize("failure", ["missing", "permission", "io", "success"])
@pytest.mark.parametrize("unavailable", [False, True])
def test_post_build_cleanup_reports_real_failures_and_retains_private_retry_metadata(
    worker, monkeypatch, failure, unavailable,
):
    calls = 0

    def authorize(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            if unavailable:
                raise sqlite3.OperationalError("private-database-query")
            return BackgroundAuthorization(BackgroundAuthorizationState.PRINCIPAL_DISABLED)
        return BackgroundAuthorization(BackgroundAuthorizationState.AUTHORIZED)

    def build(*_args, **_kwargs):
        if failure != "missing":
            worker.archive.write_bytes(b"private-report-body")
        return {"path": str(worker.archive), "byte_size": 19}

    original_unlink = Path.unlink
    fail_removal = failure in {"permission", "io"}
    error_type, error_number = (PermissionError, errno.EACCES) if failure == "permission" else (OSError, errno.EIO)

    def unlink(path, *args, **kwargs):
        if path == worker.archive and fail_removal:
            raise error_type(error_number, "private-cleanup-error", str(path))
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(export_authorization, "resolve_background_authorization", authorize)
    monkeypatch.setattr(worker.module, worker.builder_name, build)
    monkeypatch.setattr(Path, "unlink", unlink)
    worker.module._run_job(worker.job["id"], {})
    _assert_terminal(
        worker, stage="post_build", reason="authorization_check_failed" if unavailable else "principal_disabled",
        unavailable=unavailable, retained_archive=fail_removal,
    )
    public = worker.module._public_job(worker.module._read_job(worker.job["id"]))
    assert "archive_path" not in public and "authorization_cleanup_pending" not in public
    download = _download_result(worker)
    assert download["status"] == "failed" and "path" not in download
    if not fail_removal:
        assert not worker.archive.exists()
        assert not any(r.msg == "EXPORT_REVOKED_ARCHIVE_CLEANUP_FAILED" for r in worker.records)
        return
    _cleanup_events(worker, "post_build_authorization", error_type.__name__, error_number)
    stored = worker.module._read_job(worker.job["id"])
    assert stored["archive_path"] == str(worker.archive)
    assert worker.archive.exists()

    # Both cleanup entry points preserve the association while removal still fails.
    for discard in (False, True):
        worker.records.clear()
        _cleanup_retry(worker, discard=discard)
        _cleanup_events(
            worker, "discard_authorization" if discard else "retention_authorization", error_type.__name__, error_number,
        )
        assert worker.module._read_job(worker.job["id"])["archive_path"] == str(worker.archive)
        assert worker.archive.exists()
    fail_removal = False
    worker.records.clear()
    _cleanup_retry(worker)
    assert not worker.archive.exists()
    assert worker.module._read_job(worker.job["id"]) is None
    assert not worker.records


@pytest.mark.parametrize("worker", ["package"], indirect=True)
@pytest.mark.parametrize("phase", ["core", "complete"])
@pytest.mark.parametrize("unavailable", [False, True])
def test_real_package_progress_cleanup_failure_is_retained_for_a_later_retry(
    worker, tmp_path, monkeypatch, phase, unavailable,
):
    from core.database_access import get_db_connect
    from services.auth import storage

    identity, project, package = _create_real_package(tmp_path, monkeypatch)
    monkeypatch.setattr(export_authorization, "get_db_connect", get_db_connect)
    worker.job.update({
        "principal_id": identity.principal_id, "personal_workspace_id": identity.personal_workspace_id,
        "project_id": project["id"], "package_id": package["id"],
    })
    worker.module._write_job(worker.job)
    worker.records.clear()

    original_unlink = Path.unlink
    fail_removal = True

    def unlink(path, *args, **kwargs):
        if path.parent == worker.module._JOB_DIR and path.suffix == ".zip" and fail_removal:
            raise PermissionError(errno.EACCES, "private-cleanup-error", str(path))
        return original_unlink(path, *args, **kwargs)

    def build(*args, progress_callback, **kwargs):
        def progress(current_phase, message):
            if current_phase == phase:
                if unavailable:
                    raise export_authorization.ExportAuthorizationUnavailable("OperationalError")
                storage.disable_principal(identity.principal_id, reason="operator stop")
            progress_callback(current_phase, message)
        return package_archive.build_evidence_package_archive(*args, progress_callback=progress, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink)
    monkeypatch.setattr(worker.module, worker.builder_name, build)
    worker.module._run_job(worker.job["id"], {})
    _assert_terminal(
        worker, stage="progress", reason="authorization_check_failed" if unavailable else "principal_disabled",
        unavailable=unavailable, retained_archive=True,
    )
    _cleanup_events(worker, "progress_authorization", "PermissionError", errno.EACCES)
    archive = Path(worker.module._read_job(worker.job["id"])["archive_path"])
    assert archive.is_file()
    assert _download_result(worker)["status"] == "failed"
    fail_removal = False
    worker.records.clear()
    _cleanup_retry(worker, discard=True)
    assert not archive.exists()
    assert worker.module._read_job(worker.job["id"]) is None
    assert not worker.records
