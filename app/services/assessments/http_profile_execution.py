# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Protected execution contracts for Project HTTP assessment profiles."""

from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlsplit

from core.database_access import get_db_connect
from services.assessments.http_profile_contracts import HttpProfileError
from services.assessments.command_plans import command_plan
from services.assessments.http_profile_material import (
    HttpProfileMaterialError,
    materialize_tool_profile,
)
from services.assessments.http_profiles import (
    _internal_profile,
    _profile_row,
    _validate_project_scope,
    _validate_references,
)
from services.secrets.storage import get_secret_value_by_name
from services.secrets.vault import MasterKeyError, SecretDecryptError


_SUPPORTED_TOOLS = frozenset({"curl", "httpx", "katana", "nuclei"})
_UNSUPPORTED_SECRET_SLOTS = frozenset({
    "client_key_passphrase",
    "proxy_authorization",
})


class HttpProfileExecutionError(ValueError):
    """A stable protected-profile preview or launch failure."""

    def __init__(self, code: str, message: str, *, status_code: int = 409):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass(frozen=True)
class ProtectedHttpLaunch:
    execution_command: str
    trusted_execution_args: tuple[str, ...]
    private_values: tuple[str, ...]
    cleanup: Any | None
    audit_summary: dict[str, Any]


def _credential_use(profile: Mapping[str, Any]) -> list[str]:
    uses = {str(key) for key, value in profile.get("secret_refs", {}).items() if value}
    if profile.get("headers"):
        uses.add("headers")
    if profile.get("file_refs"):
        uses.add("client_certificate")
    return sorted(uses)


def _path_in_scope(path: str, prefixes: list[str]) -> bool:
    return any(path == prefix or path.startswith(prefix.rstrip("/") + "/") for prefix in prefixes)


def _execution_target(profile: Mapping[str, Any], target: Mapping[str, str]) -> str:
    target_type = str(target.get("type") or "")
    target_value = str(target.get("value") or "")
    base_url = str(profile.get("base_url") or "")
    if target_type in {"domain", "ip"}:
        if str(urlsplit(base_url).hostname or "").casefold() != target_value.strip("[]").casefold():
            raise HttpProfileExecutionError(
                "http_profile_scope_mismatch",
                "The HTTP profile base URL no longer matches this exact Project target.",
            )
        return base_url
    if target_type != "url":
        raise HttpProfileExecutionError(
            "http_profile_target_unsupported",
            "HTTP profiles can only run against saved domain, IP, or URL targets.",
        )
    parsed = urlsplit(target_value)
    host = str(parsed.hostname or "").casefold()
    if host not in {str(value).casefold() for value in profile.get("allowed_hosts", [])}:
        raise HttpProfileExecutionError(
            "http_profile_scope_mismatch",
            "The HTTP profile does not allow this Project URL host.",
        )
    matching_roots = [
        str(root)
        for root in profile.get("scope_roots", [])
        if target_value == str(root) or target_value.startswith(str(root).rstrip("/") + "/")
    ]
    if not matching_roots:
        raise HttpProfileExecutionError(
            "http_profile_scope_mismatch",
            "The Project URL is outside this HTTP profile's saved scope roots.",
        )
    path = parsed.path or "/"
    includes = [str(value) for value in profile.get("include_paths", [])]
    excludes = [str(value) for value in profile.get("exclude_paths", [])]
    if includes and not _path_in_scope(path, includes):
        raise HttpProfileExecutionError(
            "http_profile_scope_mismatch",
            "The Project URL is outside this HTTP profile's included paths.",
        )
    if excludes and _path_in_scope(path, excludes):
        raise HttpProfileExecutionError(
            "http_profile_scope_mismatch",
            "The Project URL is excluded by this HTTP profile.",
        )
    return target_value


def _unsupported_reason(profile: Mapping[str, Any], tool: str) -> str:
    if tool not in _SUPPORTED_TOOLS:
        return "This assessment tool does not yet have a protected HTTP-profile adapter."
    if profile.get("proxy_url"):
        return "Protected runs reject proxy use until an explicit proxy allowlist is configured."
    if profile.get("login_workflow_id") or profile.get("token_capture_rules"):
        return "This tool cannot safely run the profile's login or token-capture workflow yet."
    secret_slots = set(profile.get("secret_refs", {}))
    if secret_slots & _UNSUPPORTED_SECRET_SLOTS:
        return "This tool cannot safely use one or more selected HTTP-profile secret fields."
    if tool in {"httpx", "katana"} and profile.get("file_refs"):
        return "This tool does not support the profile's client certificate contract."
    return ""


def load_http_profile_plan_context(
    conn: Any,
    session_id: str,
    project_id: str,
    profile_id: str,
    *,
    target: Mapping[str, str],
    tool: str,
    team_id: str = "",
    actor_member_id: str = "",
) -> tuple[dict[str, Any], str, str]:
    """Return a safe profile summary, execution target, and recoverable error."""
    row = _profile_row(conn, session_id, project_id, profile_id, team_id=team_id)
    if not row:
        raise HttpProfileExecutionError(
            "http_profile_not_found",
            "HTTP profile was not found in this Project scope.",
            status_code=404,
        )
    profile = _internal_profile(row)
    summary = {
        "id": profile["id"],
        "name": profile["name"],
        "role": profile["role"],
        "credential_use": _credential_use(profile),
        "enabled": bool(profile["enabled"]),
        "revision": int(profile["revision"]),
        "rate_limit_per_second": int(profile["rate_limit_per_second"]),
        "concurrency": int(profile["concurrency"]),
    }
    if not profile["enabled"]:
        return summary, "", "The selected HTTP profile is disabled."
    unsupported = _unsupported_reason(profile, tool)
    if unsupported:
        return summary, "", unsupported
    try:
        _validate_project_scope(conn, session_id, project_id, profile, team_id=team_id)
        _validate_references(
            conn,
            session_id,
            team_id,
            actor_member_id,
            profile,
        )
        target_value = _execution_target(profile, target)
    except HttpProfileExecutionError as exc:
        return summary, "", str(exc)
    except HttpProfileError:
        return summary, "", "The selected HTTP profile has missing or unavailable references."
    return summary, target_value, ""


def _resolved_headers(
    profile: Mapping[str, Any],
    *,
    owner_id: str,
    session_id: str,
    team_id: str,
) -> tuple[list[tuple[str, str]], list[str]]:
    resolved: dict[str, tuple[str, str]] = {}
    private_values: list[str] = []

    def _secret(name: str) -> str:
        try:
            value = get_secret_value_by_name(
                owner_id,
                name,
                audit_session_id=session_id,
                team_id=team_id,
            )
        except (MasterKeyError, SecretDecryptError) as exc:
            raise HttpProfileExecutionError(
                "http_profile_vault_unavailable",
                "The Secrets vault is unavailable for this HTTP profile.",
                status_code=503,
            ) from exc
        if value is None:
            raise HttpProfileExecutionError(
                "http_profile_secret_missing",
                "The selected HTTP profile references a missing Secret.",
            )
        if any(character in value for character in ("\x00", "\r", "\n")):
            raise HttpProfileExecutionError(
                "http_profile_secret_invalid",
                "An HTTP profile Secret is not safe for use as a request header.",
            )
        private_values.append(value)
        return value

    def _add(name: str, value: str) -> None:
        key = name.casefold()
        if key in resolved:
            raise HttpProfileExecutionError(
                "http_profile_header_conflict",
                f"The HTTP profile defines {name} more than once.",
            )
        resolved[key] = (name, value)

    for header in profile.get("headers", []):
        _add(str(header["name"]), _secret(str(header["secret_name"])))
    refs = profile.get("secret_refs", {})
    if refs.get("bearer_token"):
        token = _secret(str(refs["bearer_token"]))
        _add("Authorization", f"Bearer {token}")
    if refs.get("cookie"):
        _add("Cookie", _secret(str(refs["cookie"])))
    if refs.get("basic_username"):
        username = _secret(str(refs["basic_username"]))
        password = _secret(str(refs["basic_password"]))
        encoded = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        private_values.append(encoded)
        _add("Authorization", f"Basic {encoded}")
    return list(resolved.values()), private_values


def _scope_arguments(profile: Mapping[str, Any], tool: str, target_value: str) -> list[str]:
    if tool in {"curl", "httpx"}:
        return []
    if tool == "nuclei":
        return ["-dr", "-ni"]
    raw_host = str(urlsplit(target_value).hostname or "")
    host = re.escape(f"[{raw_host}]" if ":" in raw_host else raw_host)
    arguments = ["-fs", "fqdn"]
    for prefix in profile.get("include_paths", []):
        arguments.extend(["-cs", rf"^https?://{host}(?::\d+)?{re.escape(str(prefix))}"])
    for prefix in profile.get("exclude_paths", []):
        arguments.extend(["-cos", rf"^https?://{host}(?::\d+)?{re.escape(str(prefix))}"])
    return arguments


def materialize_http_profile_launch(
    session_id: str,
    project_id: str,
    plan: Mapping[str, Any],
    *,
    team_id: str = "",
    actor_member_id: str = "",
) -> ProtectedHttpLaunch:
    """Revalidate and materialize one selected profile immediately before launch."""
    selected = plan.get("http_profile")
    if not isinstance(selected, Mapping) or not str(selected.get("id") or ""):
        return ProtectedHttpLaunch(
            str(plan.get("display_command") or ""),
            (),
            (),
            None,
            {},
        )
    tool = str((plan.get("action") or {}).get("id") or "")
    raw_target = plan.get("target")
    target = {
        "type": str(raw_target.get("type") or ""),
        "value": str(raw_target.get("value") or ""),
    } if isinstance(raw_target, Mapping) else {"type": "", "value": ""}
    profile_id = str(selected.get("id") or "")
    with get_db_connect()() as conn:
        summary, target_value, unavailable = load_http_profile_plan_context(
            conn,
            session_id,
            project_id,
            profile_id,
            target=target,
            tool=tool,
            team_id=team_id,
            actor_member_id=actor_member_id,
        )
        row = _profile_row(conn, session_id, project_id, profile_id, team_id=team_id)
        profile = _internal_profile(row)
    if unavailable or summary["revision"] != int(selected.get("revision") or 0):
        raise HttpProfileExecutionError(
            "http_profile_changed",
            unavailable or "The HTTP profile changed. Review the current launch plan again.",
        )
    protected_command = command_plan(
        tool,
        str(target.get("type") or ""),
        str(target.get("value") or ""),
        web_target=target_value,
        http_profile=summary,
        protected_display=False,
    )
    if protected_command is None:
        raise HttpProfileExecutionError(
            "http_profile_tool_unsupported",
            "This saved action has no protected HTTP-profile command contract.",
        )
    owner_id = team_id or session_id
    headers, private_values = _resolved_headers(
        profile,
        owner_id=owner_id,
        session_id=session_id,
        team_id=team_id,
    )
    trusted_args = _scope_arguments(profile, tool, target_value)
    try:
        tool_material = materialize_tool_profile(
            tool,
            profile,
            headers,
            session_id=session_id,
            team_id=team_id,
            actor_member_id=actor_member_id,
        )
    except HttpProfileMaterialError as exc:
        raise HttpProfileExecutionError(
            "http_profile_materialization_failed",
            "Protected HTTP run material could not be prepared.",
            status_code=503,
        ) from exc
    return ProtectedHttpLaunch(
        execution_command=protected_command.command,
        trusted_execution_args=tuple(trusted_args) + tool_material.trusted_args,
        private_values=tuple(private_values) + tool_material.private_values,
        cleanup=tool_material.cleanup,
        audit_summary={
            "profile_id": summary["id"],
            "profile_role": summary["role"],
            "credential_use": summary["credential_use"],
        },
    )
