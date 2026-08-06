# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Safe process-start metadata and protected argument helpers."""

import shlex
from dataclasses import replace
from typing import Any, Callable

from services.runs.contracts import RunPreparationError


def append_trusted_execution_args(prepared: Any, values: tuple[str, ...]) -> Any:
    """Append adapter-built argv only after the operator command was validated."""
    if not values:
        return prepared
    normalized: list[str] = []
    for value in values:
        argument = str(value)
        if not argument or any(character in argument for character in ("\x00", "\r", "\n")):
            raise RunPreparationError("Protected execution arguments are invalid.")
        normalized.append(argument)
    suffix = shlex.join(normalized)
    return replace(
        prepared,
        execution_command=f"{prepared.execution_command} {suffix}",
        command=f"{prepared.command} {suffix}",
    )


def display_missing_runtime(prepared_real: Any) -> str:
    return str(
        getattr(prepared_real, "display_missing_runtime", "")
        or prepared_real.missing_runtime
    )


def real_start_kwargs(
    *,
    owner_client_id: str,
    owner_tab_id: str,
    team_id: str,
    owner_context: object,
    private_values: tuple[str, ...],
) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    if owner_client_id:
        kwargs["owner_client_id"] = owner_client_id
    if owner_tab_id:
        kwargs["owner_tab_id"] = owner_tab_id
    if team_id:
        kwargs.update({"team_id": team_id, "owner_context": owner_context})
    if private_values:
        kwargs["private_values"] = private_values
    return kwargs


def cleanup_started_run_material(hook: Callable[[], None] | None) -> None:
    if not hook:
        return
    try:
        hook()
    except Exception:
        # Cleanup implementations log their own bounded context. The normal
        # missing-runtime response must remain available if cleanup also fails.
        pass
