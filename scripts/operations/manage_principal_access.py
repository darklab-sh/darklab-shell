# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Manage principal access through the local container operator boundary."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = ROOT / "app"
sys.path.insert(0, str(APP_ROOT))

from config import CFG  # noqa: E402
from runtime_bootstrap import init_database  # noqa: E402
from services.auth import lifecycle  # noqa: E402
from services.auth.browser_sessions import (  # noqa: E402
    revoke_principal_browser_sessions,
    rotate_signing_key,
)


def _inside_container() -> bool:
    return Path("/.dockerenv").exists() or Path("/run/.containerenv").exists()


def _require_container() -> None:
    if not _inside_container():
        raise RuntimeError(
            "principal access management must run inside the darklab_shell container"
        )


def _open_secret_file(path_value: str) -> tuple[int, Path]:
    path = Path(path_value).expanduser()
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags, 0o600)
    except OSError as exc:
        raise RuntimeError(f"could not create secret file securely: {exc}") from exc
    return descriptor, path


def _issue_to_file(path_value: str, operation: Callable[[], Any]) -> dict[str, Any]:
    descriptor, path = _open_secret_file(path_value)
    try:
        issued = operation()
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            descriptor = -1
            handle.write(issued.secret + "\n")
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            if path.stat().st_size == 0:
                path.unlink()
        except OSError:
            pass
        raise
    return {
        "credential": issued.metadata.to_safe_dict(),
        "secret_file": str(path),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage pseudonymous principal access.")
    commands = parser.add_subparsers(dest="command", required=True)

    bootstrap = commands.add_parser(
        "bootstrap",
        help="Create the first principal for a fresh token-required deployment.",
    )
    bootstrap.add_argument("--label", default="Initial operator access")
    bootstrap.add_argument("--secret-file", required=True)

    status = commands.add_parser("status", help="Show safe principal and credential metadata.")
    status.add_argument("principal_id")

    issue = commands.add_parser("issue", help="Issue a portable credential or PAT.")
    issue.add_argument("principal_id")
    issue.add_argument("--type", choices=("portable", "pat"), default="portable")
    issue.add_argument("--label", default="")
    issue.add_argument("--expires-at")
    issue.add_argument("--scope", action="append", default=[])
    issue.add_argument("--secret-file", required=True)

    recover = commands.add_parser("recover", help="Revoke current credentials and issue replacement access.")
    recover.add_argument("principal_id")
    recover.add_argument("--confirm-principal", required=True)
    recover.add_argument("--label", default="Recovered access")
    recover.add_argument("--secret-file", required=True)

    expiry = commands.add_parser("expiry", help="Change one credential's expiry.")
    expiry.add_argument("principal_id")
    expiry.add_argument("credential_id")
    expiry.add_argument("expires_at", help="ISO-8601 timestamp, or 'none' for a portable credential.")

    rotate = commands.add_parser("rotate", help="Issue a replacement before revoking a credential.")
    rotate.add_argument("principal_id")
    rotate.add_argument("credential_id")
    rotate.add_argument("--label")
    rotate.add_argument("--expires-at")
    rotate.add_argument("--secret-file", required=True)

    revoke = commands.add_parser("revoke", help="Revoke one credential.")
    revoke.add_argument("principal_id")
    revoke.add_argument("credential_id")
    revoke.add_argument("--reason", required=True)
    revoke.add_argument("--confirm-lockout", action="store_true")
    revoke.add_argument("--pause-related-work", action="store_true")

    disable = commands.add_parser("disable", help="Disable a principal and suspend its work.")
    disable.add_argument("principal_id")
    disable.add_argument("--reason", required=True)

    enable = commands.add_parser("enable", help="Enable a disabled principal.")
    enable.add_argument("principal_id")

    revoke_sessions = commands.add_parser(
        "revoke-all-sessions",
        help="Sign every browser out for one principal.",
    )
    revoke_sessions.add_argument("principal_id")

    commands.add_parser(
        "rotate-session-signing-key",
        help="Use a new signing key for future browser sessions.",
    )
    return parser


def run(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "bootstrap":
        if str(CFG.get("access_profile") or "open") != "token_required":
            raise RuntimeError("bootstrap requires access_profile: token_required")
        init_database()
        descriptor, path = _open_secret_file(args.secret_file)

        def persist_credential(secret: str) -> None:
            nonlocal descriptor
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                descriptor = -1
                handle.write(secret + "\n")
                handle.flush()
                os.fsync(handle.fileno())

        try:
            bundle = lifecycle.operator_bootstrap(
                credential_label=args.label,
                credential_sink=persist_credential,
            )
        except BaseException:
            if descriptor >= 0:
                os.close(descriptor)
            try:
                path.unlink()
            except OSError:
                pass
            raise
        return {
            **bundle.to_safe_dict(),
            "secret_file": str(path),
        }
    if args.command == "status":
        principal, credentials = lifecycle.operator_summary(args.principal_id)
        return {
            "principal": principal.to_safe_dict(),
            "credentials": [item.to_safe_dict() for item in credentials],
        }
    if args.command == "issue":
        return _issue_to_file(
            args.secret_file,
            lambda: lifecycle.operator_issue(
                args.principal_id,
                credential_type=args.type,
                label=args.label,
                expires_at=args.expires_at,
                scopes=args.scope or None,
            ),
        )
    if args.command == "recover":
        if args.confirm_principal != args.principal_id:
            raise RuntimeError("--confirm-principal must exactly match the target principal id")
        return _issue_to_file(
            args.secret_file,
            lambda: lifecycle.operator_recover(args.principal_id, label=args.label),
        )
    if args.command == "expiry":
        value = None if args.expires_at.lower() == "none" else args.expires_at
        item = lifecycle.operator_change_expiry(args.principal_id, args.credential_id, value)
        return {"credential": item.to_safe_dict()}
    if args.command == "rotate":
        return _issue_to_file(
            args.secret_file,
            lambda: lifecycle.operator_rotate(
                args.principal_id,
                args.credential_id,
                label=args.label,
                expires_at=args.expires_at,
            ),
        )
    if args.command == "revoke":
        item, disposition = lifecycle.operator_revoke(
            args.principal_id,
            args.credential_id,
            reason=args.reason,
            confirm_lockout=args.confirm_lockout,
            pause_related_work=args.pause_related_work,
        )
        return {
            "credential": item.to_safe_dict(),
            "durable_work": disposition.to_safe_dict(),
        }
    if args.command in {"disable", "enable"}:
        principal = lifecycle.set_principal_enabled(
            args.principal_id,
            enabled=args.command == "enable",
            reason=getattr(args, "reason", ""),
        )
        return {"principal": principal.to_safe_dict()}
    if args.command == "revoke-all-sessions":
        return {"revoked_sessions": revoke_principal_browser_sessions(args.principal_id)}
    if args.command == "rotate-session-signing-key":
        return {"active_signing_key_version": rotate_signing_key()}
    raise RuntimeError("unknown access-management command")


def main(argv: list[str] | None = None) -> int:
    try:
        _require_container()
        payload = run(_parser().parse_args(argv))
    except (RuntimeError, ValueError, PermissionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
