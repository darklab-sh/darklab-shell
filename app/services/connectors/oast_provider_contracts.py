# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Non-secret value contracts for the private OAST provider transport."""

from __future__ import annotations

from dataclasses import dataclass, field


class OastProviderTransportError(RuntimeError):
    """Raised when the private provider transport fails closed."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class OastProviderSession:
    callback_label: str
    correlation_id: str
    secret_key: str = field(repr=False)
    private_key_pem: bytes = field(repr=False)


@dataclass(frozen=True)
class OastProviderPollBatch:
    interactions: tuple[dict[str, object], ...]
    rejected_count: int
    ignored_shared_count: int


__all__ = [
    "OastProviderPollBatch",
    "OastProviderSession",
    "OastProviderTransportError",
]
