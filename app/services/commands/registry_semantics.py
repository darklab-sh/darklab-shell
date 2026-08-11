# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Cross-entry semantic checks for normalized command registries."""


def validate_commands_registry_semantics(
    registry: dict,
    *,
    require_pipe_contracts: bool,
) -> None:
    """Reject ambiguous command roots and incomplete pipe-helper contracts."""
    roots_by_section: dict[str, set[str]] = {}
    for section in ("commands", "pipe_helpers"):
        roots: set[str] = set()
        for entry in registry.get(section, []) or []:
            root = str(entry.get("root") or "").strip().lower()
            if not root:
                continue
            if root in roots:
                raise ValueError(f"duplicate command registry root in {section}: {root}")
            roots.add(root)
            if (
                require_pipe_contracts
                and section == "pipe_helpers"
                and not bool((entry.get("autocomplete") or {}).get("pipe_command"))
            ):
                raise ValueError(f"pipe helper must declare autocomplete.pipe.enabled: {root}")
        roots_by_section[section] = roots

    overlaps = roots_by_section["commands"] & roots_by_section["pipe_helpers"]
    if overlaps:
        raise ValueError(
            "command registry roots cannot appear in commands and pipe_helpers: "
            + ", ".join(sorted(overlaps))
        )
