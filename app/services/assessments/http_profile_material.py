# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Tool-specific private files for protected HTTP assessment runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import yaml

from services.assessments.http_profile_runtime import (
    PrivateHttpMaterialError,
    PrivateHttpRunMaterial,
)
from services.teams.scope import owner_context_for_scope
from services.workspace.files import (
    WorkspaceError,
    open_owner_workspace_file_for_download,
)


class HttpProfileMaterialError(RuntimeError):
    """Raised when protected tool material cannot be prepared safely."""


@dataclass(frozen=True)
class ProtectedToolMaterial:
    trusted_args: tuple[str, ...]
    private_values: tuple[str, ...]
    cleanup: Any | None


def private_file_values(slot: str, content: bytes) -> list[str]:
    """Return maskable private-key lines without storing PEM markers."""
    if slot != "client_key":
        return []
    return [
        line
        for line in content.decode("utf-8", errors="ignore").splitlines()
        if len(line) >= 16 and not line.startswith("-----")
    ]


def _curl_config_value(value: str) -> str:
    if any(ord(character) < 32 and character not in {"\t"} for character in value):
        raise HttpProfileMaterialError("Curl profile material contains an unsafe value")
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\t", "\\t")
    )


def _curl_config(
    headers: list[tuple[str, str]],
    copied: Mapping[str, str],
) -> bytes:
    lines = [
        f'header = "{_curl_config_value(f"{name}: {value}")}"'
        for name, value in headers
    ]
    if copied:
        lines.extend([
            f'cert = "{_curl_config_value(copied["client_certificate"])}"',
            f'key = "{_curl_config_value(copied["client_key"])}"',
        ])
    return ("\n".join(lines) + "\n").encode("utf-8")


def _copy_profile_files(
    material: PrivateHttpRunMaterial,
    profile: Mapping[str, Any],
    *,
    session_id: str,
    team_id: str,
    actor_member_id: str,
    private_values: list[str],
) -> dict[str, str]:
    owner = owner_context_for_scope(
        session_id,
        team_id=team_id,
        actor_member_id=actor_member_id,
    )
    copied: dict[str, str] = {}
    for slot, relative_path in profile.get("file_refs", {}).items():
        with open_owner_workspace_file_for_download(owner, str(relative_path)) as stream:
            content = stream.read()
        destination = material.write_bytes(f"{slot}.pem", content)
        copied[str(slot)] = str(destination)
        private_values.append(str(destination))
        private_values.extend(private_file_values(str(slot), content))
    return copied


def materialize_tool_profile(
    tool: str,
    profile: Mapping[str, Any],
    headers: list[tuple[str, str]],
    *,
    session_id: str,
    team_id: str,
    actor_member_id: str,
) -> ProtectedToolMaterial:
    """Build one scanner-readable context without exposing values in argv."""
    if not headers and not profile.get("file_refs"):
        return ProtectedToolMaterial((), (), None)
    material: PrivateHttpRunMaterial | None = None
    private_values: list[str] = []
    trusted_args: list[str] = []
    try:
        material = PrivateHttpRunMaterial()
        copied = _copy_profile_files(
            material,
            profile,
            session_id=session_id,
            team_id=team_id,
            actor_member_id=actor_member_id,
            private_values=private_values,
        ) if profile.get("file_refs") else {}
        if tool == "curl":
            config_path = material.write_bytes(
                "curl.conf",
                _curl_config(headers, copied),
            )
            trusted_args.extend(["--config", str(config_path)])
            private_values.append(str(config_path))
        elif headers:
            if tool in {"httpx", "nuclei"}:
                secret_payload = {
                    "id": "darklab-http-profile",
                    "info": {"name": "Protected DarkLab HTTP profile"},
                    "static": [{
                        "type": "Header",
                        "domains": list(profile.get("allowed_hosts", [])),
                        "headers": [
                            {"key": name, "value": value}
                            for name, value in headers
                        ],
                    }],
                }
                secret_path = material.write_bytes(
                    "secrets.yaml",
                    yaml.safe_dump(secret_payload, sort_keys=False).encode("utf-8"),
                )
                trusted_args.extend(["-sf", str(secret_path)])
            else:
                secret_path = material.write_bytes(
                    "headers.txt",
                    "".join(f"{name}: {value}\n" for name, value in headers).encode("utf-8"),
                )
                trusted_args.extend(["-H", str(secret_path)])
            private_values.append(str(secret_path))
        if copied and tool == "nuclei":
            trusted_args.extend([
                "-cc",
                copied["client_certificate"],
                "-ck",
                copied["client_key"],
            ])
    except (OSError, PrivateHttpMaterialError, WorkspaceError, HttpProfileMaterialError) as exc:
        if material:
            material.cleanup()
        raise HttpProfileMaterialError(
            "Protected HTTP run material could not be prepared"
        ) from exc
    return ProtectedToolMaterial(
        tuple(trusted_args),
        tuple(private_values),
        material.cleanup,
    )
