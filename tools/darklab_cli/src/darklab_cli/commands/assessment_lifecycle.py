# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Assessment-cycle lifecycle command handlers."""

from __future__ import annotations

import argparse
from typing import Any

from ..client import DarklabClient, DarklabCliError, die
from .assessment_lifecycle_formatting import (
    print_assessment_delete_preview,
    print_assessment_deleted,
    print_assessment_result,
)
from .confirmations import destructive_action_confirmed


_TRANSITION_STATUS = {"complete": "completed", "archive": "archived"}


def _actionable_error(exc: DarklabCliError, action: str) -> DarklabCliError:
    if exc.code == "team_forbidden":
        message = (
            "Assessment lifecycle changes require the MUTATE_PROJECTS capability "
            "for the selected team."
        )
    elif exc.code == "assessment_batch_cancellation_pending":
        details = exc.details if isinstance(exc.details, dict) else {}
        raw_batch_ids = details.get("batch_ids")
        batch_ids = (
            [str(batch_id) for batch_id in raw_batch_ids if str(batch_id)]
            if isinstance(raw_batch_ids, list)
            else []
        )
        if not batch_ids and details.get("batch_id"):
            batch_ids = [str(details["batch_id"])]
        affected = ", ".join(batch_ids) or "the linked assessment batches"
        message = (
            f"Assessment batch cancellation is still settling for {affected}. "
            "Wait for every affected batch to reach a terminal state, then retry "
            f"assessment {action}."
        )
    else:
        return exc
    return DarklabCliError(
        message,
        status=exc.status,
        code=exc.code,
        details=exc.details,
    )


def _request(
    client: DarklabClient,
    method: str,
    path: str,
    *,
    action: str,
    body: dict[str, Any] | None = None,
) -> Any:
    try:
        return client.request(method, path, body=body)
    except DarklabCliError as exc:
        actionable = _actionable_error(exc, action)
        if actionable is exc:
            raise
        raise actionable from exc


def handle_assessment_lifecycle(
    client: DarklabClient,
    args: argparse.Namespace,
    base_path: str,
) -> int:
    command = args.assessment_command
    if command == "create":
        body = {"profile_key": args.profile_key}
        if args.title is not None:
            body["title"] = args.title
        payload = _request(client, "POST", base_path, action="create", body=body)
        return print_assessment_result(payload, args.format)
    if command in _TRANSITION_STATUS:
        path = f"{base_path}/{args.assessment_id}"
        payload = _request(
            client,
            "PATCH",
            path,
            action=command,
            body={"status": _TRANSITION_STATUS[command]},
        )
        return print_assessment_result(payload, args.format)
    if command == "delete":
        return _delete_assessment(client, args, base_path)
    raise DarklabCliError("unknown assessment lifecycle command")


def _delete_assessment(
    client: DarklabClient,
    args: argparse.Namespace,
    base_path: str,
) -> int:
    path = f"{base_path}/{args.assessment_id}"
    preview = client.request("GET", f"{path}/delete-preview")
    raw_preview = preview.get("preview") if isinstance(preview, dict) else None
    if not isinstance(raw_preview, dict):
        raise DarklabCliError("assessment deletion preview response is invalid")
    if not destructive_action_confirmed(
        preview,
        confirmed=args.confirm,
        output_format=args.format,
        action="delete this archived assessment",
        render_text=print_assessment_delete_preview,
    ):
        return 0
    if not raw_preview.get("can_delete"):
        return die("assessment must be archived before it can be deleted")
    payload = _request(client, "DELETE", path, action="delete")
    return print_assessment_deleted(payload, args.format)


__all__ = ["handle_assessment_lifecycle"]
