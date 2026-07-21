# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Command-registry driven smoke-test command corpus helpers."""

from __future__ import annotations

from collections.abc import Callable

from services.commands.registry_secret_specs import scoped_required_secrets
from services.commands.registry_validation import split_command_argv


def spread_sensitive_smoke_commands(commands: list[str]) -> list[str]:
    """De-clump bursty network lookups without changing source ownership/order."""
    sensitive_roots = {"dig", "whois"}
    scheduled: list[str] = []
    deferred: list[str] = []

    def _root(command: str) -> str:
        return split_command_argv(command)[0].lower() if command.strip() else ""

    def _last_sensitive_root() -> str:
        for command in reversed(scheduled):
            root = _root(command)
            if root in sensitive_roots:
                return root
        return ""

    def _flush_deferred(*, allow_sensitive_after_sensitive: bool = False) -> None:
        if not deferred:
            return
        last_root = _root(scheduled[-1]) if scheduled else ""
        last_sensitive_root = _last_sensitive_root()
        fallback_index = None
        for index, command in enumerate(deferred):
            root = _root(command)
            if root == last_root:
                continue
            if (
                not allow_sensitive_after_sensitive
                and last_root in sensitive_roots
                and root in sensitive_roots
            ):
                continue
            if root != last_sensitive_root:
                scheduled.append(deferred.pop(index))
                return
            if fallback_index is None:
                fallback_index = index
        if fallback_index is not None:
            scheduled.append(deferred.pop(fallback_index))

    for command in commands:
        root = _root(command)
        last_root = _root(scheduled[-1]) if scheduled else ""
        if root in sensitive_roots and last_root in sensitive_roots:
            deferred.append(command)
            continue
        scheduled.append(command)
        if root not in sensitive_roots:
            _flush_deferred()

    while deferred:
        before = len(deferred)
        _flush_deferred(allow_sensitive_after_sensitive=True)
        if len(deferred) == before:
            scheduled.append(deferred.pop(0))

    return scheduled


def _example_sources(spec: dict):
    yield from spec.get("examples") or []
    for sub_spec in (spec.get("subcommands") or {}).values():
        if isinstance(sub_spec, dict):
            yield from _example_sources(sub_spec)


def _example_smoke_profile(example: dict) -> str:
    smoke = example.get("smoke")
    if isinstance(smoke, str):
        return smoke.strip().lower()
    if isinstance(smoke, dict):
        return str(smoke.get("profile") or "").strip().lower()
    return ""


def load_container_smoke_test_commands(
    *,
    load_autocomplete_context: Callable[[dict], dict],
    load_workflows: Callable[[dict], list],
    workflow_tokens: Callable[[str], set[str]],
    render_workflow_text: Callable[[str, dict[str, str]], str],
    is_help_invocation_for_spec: Callable[[str, object, str | None], bool],
    suggestion_enabled_for_features: Callable[[dict, dict], bool],
) -> list[str]:
    """Return the user-facing smoke-test corpus from registry examples and workflows."""
    commands = []
    seen = set()

    def _is_unauthenticated_help_smoke(root: str, spec: dict, example: dict) -> bool:
        if _example_smoke_profile(example) != "unauthenticated":
            return False
        command = str(example.get("value") or "").strip()
        return bool(command and is_help_invocation_for_spec(command, spec.get("help"), root))

    for root, spec in load_autocomplete_context({"workspace_enabled": False}).items():
        if not isinstance(spec, dict):
            continue
        root = str(root or "").strip().lower()
        for example in _example_sources(spec):
            if not isinstance(example, dict):
                continue
            smoke_profile = _example_smoke_profile(example)
            if smoke_profile in {"disabled", "manual", "skip"}:
                continue
            if not suggestion_enabled_for_features(example, {"workspace_enabled": False}):
                continue
            command = str(example.get("value") or "").strip()
            required_secrets = [
                item
                for item in scoped_required_secrets(command, spec.get("requires_secrets"))
                if not bool(item.get("optional"))
            ]
            if required_secrets and not _is_unauthenticated_help_smoke(root, spec, example):
                continue
            if not command or command in seen:
                continue
            seen.add(command)
            commands.append(command)

    for workflow in load_workflows({"workspace_enabled": False}):
        if not isinstance(workflow, dict):
            continue
        workflow_inputs = {
            item["id"]: str(item.get("default") or "").strip()
            for item in workflow.get("inputs") or []
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        }
        for step in workflow.get("steps") or []:
            if not isinstance(step, dict):
                continue
            command = str(step.get("cmd") or "").strip()
            tokens = workflow_tokens(command)
            if tokens:
                if not tokens.issubset({key for key, value in workflow_inputs.items() if value}):
                    continue
                command = render_workflow_text(command, workflow_inputs).strip()
            if not command or command in seen:
                continue
            seen.add(command)
            commands.append(command)

    return spread_sensitive_smoke_commands(commands)


def feature_required_includes(
    item: dict,
    feature: str,
    *,
    suggestion_required_features: Callable[[dict], list[str]],
) -> bool:
    required_features = suggestion_required_features(item)
    return feature.strip().lower() in required_features


def load_container_smoke_test_interactive_commands(
    *,
    load_autocomplete_context: Callable[[dict], dict],
    suggestion_enabled_for_features: Callable[[dict, dict], bool],
    suggestion_required_features: Callable[[dict], list[str]],
) -> list[str]:
    """Return interactive PTY examples for the dedicated smoke-test corpus."""
    commands = []
    seen = set()
    cfg = {"workspace_enabled": False, "interactive_pty_enabled": True}

    for spec in load_autocomplete_context(cfg).values():
        if not isinstance(spec, dict):
            continue
        for example in _example_sources(spec):
            if not isinstance(example, dict):
                continue
            if not feature_required_includes(
                example,
                "interactive_pty",
                suggestion_required_features=suggestion_required_features,
            ):
                continue
            if not suggestion_enabled_for_features(example, cfg):
                continue
            command = str(example.get("value") or "").strip()
            if not command or command in seen:
                continue
            seen.add(command)
            commands.append(command)

    return commands
