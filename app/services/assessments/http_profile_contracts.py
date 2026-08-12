# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Stable contracts for Project HTTP assessment profiles."""

from services.projects.contracts import ProjectWorkspaceError


HTTP_PROFILE_MAX_NAME_LEN = 120
HTTP_PROFILE_MAX_URL_LEN = 2048
HTTP_PROFILE_MAX_LIST_ITEMS = 50
HTTP_PROFILE_MAX_HEADERS = 50
HTTP_PROFILE_MAX_CAPTURE_RULES = 20
HTTP_PROFILE_MAX_PATH_LEN = 1000
HTTP_PROFILE_SECRET_SLOTS = frozenset({
    "cookie",
    "bearer_token",
    "basic_username",
    "basic_password",
    "proxy_authorization",
    "client_key_passphrase",
})
HTTP_PROFILE_FILE_SLOTS = frozenset({"client_certificate", "client_key"})
HTTP_PROFILE_CAPTURE_SOURCES = frozenset({"cookie", "header", "json_pointer", "body_regex"})
HTTP_PROFILE_CAPTURE_TARGETS = frozenset({"cookie", "header", "bearer"})


class HttpProfileError(ProjectWorkspaceError):
    """Raised when an HTTP-profile request is invalid."""


class HttpProfileNotFound(HttpProfileError):
    """Raised when a profile or Project is outside the active owner scope."""


class HttpProfileConflict(HttpProfileError):
    """Raised when a profile name or optimistic revision conflicts."""
