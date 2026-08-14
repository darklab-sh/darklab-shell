# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Catalog contract for the browser-owned Project probe command."""

from services.assessments.base_action_catalog import base_action_ids
from services.assessments.nmap_profiles import nmap_profile_keys
from services.assessments.nuclei_profiles import nuclei_profile_keys
from services.assessments import service_actions as service_action_registry
from services.commands.builtin_registry import (
    BuiltinCommandSpec,
    BuiltinExecutionOwner,
    build_builtin_command_spec,
)
from services.commands.builtins_discovery import run_builtin_client_side_command


def _probe_services() -> tuple[str, ...]:
    canonical = [key for key in service_action_registry.ACTIONS if key != "version-cve"]
    aliases = [
        key for key, value in service_action_registry.ALIASES.items()
        if value in canonical
    ]
    return tuple(dict.fromkeys((*canonical, *aliases)))


def _value_suggestions(values, description):
    return [{"value": value, "description": description} for value in values]


def _nuclei_profile_suggestions():
    return [
        {
            "value": value,
            "description": "Nuclei profile",
            **(
                {"feature_required": "assessment_intrusive_actions_enabled"}
                if value == "intrusive"
                else {}
            ),
        }
        for value in nuclei_profile_keys()
    ]


_PROBE_AUTOCOMPLETE = {
    "root": "probe",
    "description": "built-in: inspect bounded one-off checks for confirmed Project targets",
    "autocomplete": {
        "subcommands": {
            "list": {
                "description": "List reviewed probe actions and profiles",
                "flags": [
                    {
                        "value": "--project",
                        "takes_value": True,
                        "description": "Project slug or id; defaults to the active Project",
                    },
                    {
                        "value": "--service",
                        "takes_value": True,
                        "description": "Show recommendations for one detected service",
                        "suggest": _value_suggestions(_probe_services(), "Detected service name"),
                    },
                    {
                        "value": "--target-type",
                        "takes_value": True,
                        "description": "Show actions compatible with one target type",
                        "suggest": _value_suggestions(
                            ("domain", "ip", "url"),
                            "Confirmed Project target type",
                        ),
                    },
                ],
            },
            "plan": {
                "description": "Preview one bounded command for a confirmed Project target",
                "arguments": _value_suggestions(base_action_ids(), "Reviewed probe action") + [{
                    "value": "<target>", "hint_only": True,
                    "description": "Exact confirmed Project target",
                }],
                "flags": [
                    {"value": "--project", "takes_value": True, "description": "Project slug or id"},
                    {"value": "--entity-id", "takes_value": True, "description": "Confirmed target entity id"},
                    {
                        "value": "--http-profile", "takes_value": True,
                        "description": "Project HTTP profile id",
                    },
                    {
                        "value": "--nmap-profile", "takes_value": True,
                        "description": "Reviewed Nmap profile",
                        "suggest": _value_suggestions(nmap_profile_keys(), "Nmap profile"),
                    },
                    {
                        "value": "--nuclei-profile", "takes_value": True,
                        "description": "Managed Nuclei profile",
                        "suggest": _nuclei_profile_suggestions(),
                    },
                ],
            },
            "run": {
                "description": "Preview, confirm, and run one bounded Project probe",
                "arguments": _value_suggestions(base_action_ids(), "Reviewed probe action") + [{
                    "value": "<target>", "hint_only": True,
                    "description": "Exact confirmed Project target",
                }],
                "flags": [
                    {"value": "--project", "takes_value": True, "description": "Project slug or id"},
                    {"value": "--entity-id", "takes_value": True, "description": "Confirmed target entity id"},
                    {
                        "value": "--http-profile", "takes_value": True,
                        "description": "Project HTTP profile id",
                    },
                    {
                        "value": "--nmap-profile", "takes_value": True,
                        "description": "Reviewed Nmap profile",
                        "suggest": _value_suggestions(nmap_profile_keys(), "Nmap profile"),
                    },
                    {
                        "value": "--nuclei-profile", "takes_value": True,
                        "description": "Managed Nuclei profile",
                        "suggest": _nuclei_profile_suggestions(),
                    },
                ],
            },
        },
    },
}


def probe_builtin_spec() -> BuiltinCommandSpec:
    return build_builtin_command_spec(
        _PROBE_AUTOCOMPLETE,
        handler_key="probe",
        handler=lambda _command, _context: run_builtin_client_side_command("probe"),
        name="probe list | probe plan|run <action> <target> --project <project-slug-or-id>",
        description="List, preview, and run bounded checks for confirmed Project targets.",
        execution_owner=BuiltinExecutionOwner.BROWSER,
        browser_fallback_stub=True,
    )


__all__ = ["probe_builtin_spec"]
