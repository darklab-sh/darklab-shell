# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Theme data embedded in browser pages, separate from the registry API."""


def browser_theme_registry(current: dict, themes: list[dict]) -> dict:
    """Keep runtime variables and metadata without duplicating the raw theme map."""
    def entry_payload(entry: dict) -> dict:
        return {key: value for key, value in entry.items() if key != "theme_vars"}

    return {"current": entry_payload(current), "themes": [entry_payload(entry) for entry in themes]}
