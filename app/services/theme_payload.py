# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Theme data embedded in browser pages, separate from the registry API."""


def browser_theme_registry(current: dict, themes: list[dict]) -> dict:
    """Keep the current palette ready while other previews load on demand."""
    def entry_payload(entry: dict, *, metadata: bool = False) -> dict:
        omitted = {"theme_vars", "vars"} if metadata else {"theme_vars"}
        return {key: value for key, value in entry.items() if key not in omitted}

    return {"current": entry_payload(current), "themes": [entry_payload(entry, metadata=True) for entry in themes],
            "details_loaded": False}
