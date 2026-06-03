"""Short-lived signed URLs for browser-native downloads."""

from __future__ import annotations

from typing import Any, Mapping, cast

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from services.secrets.vault import get_wrapping_key
from services.teams.scope import OwnerContext, OwnerScope


DOWNLOAD_TICKET_MAX_AGE_SECONDS = 120
_DOWNLOAD_TICKET_SALT = "darklab-shell-download-ticket-v1"


class DownloadTicketError(ValueError):
    """Raised when a download ticket is missing, expired, or invalid."""


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(
        secret_key=get_wrapping_key(),
        salt=_DOWNLOAD_TICKET_SALT,
    )


def create_download_ticket(payload: Mapping[str, Any]) -> str:
    normalized = {str(key): value for key, value in dict(payload).items()}
    return _serializer().dumps(normalized)


def owner_context_ticket_payload(context: OwnerContext) -> dict[str, str]:
    return {
        "owner_scope": context.scope,
        "owner_id": context.owner_id,
        "actor_session_id": context.actor_session_id,
        "actor_member_id": context.actor_member_id,
    }


def owner_context_from_ticket(payload: Mapping[str, Any]) -> OwnerContext:
    scope = str(payload.get("owner_scope") or "")
    if scope not in {"personal", "team"}:
        raise DownloadTicketError("download ticket owner scope is invalid")
    owner_id = str(payload.get("owner_id") or "").strip()
    if not owner_id:
        raise DownloadTicketError("download ticket owner is invalid")
    return OwnerContext(
        scope=cast(OwnerScope, scope),
        owner_id=owner_id,
        actor_session_id=str(payload.get("actor_session_id") or "").strip(),
        actor_member_id=str(payload.get("actor_member_id") or "").strip(),
    )


def read_download_ticket(
    token: str,
    *,
    expected_kind: str,
    max_age_seconds: int = DOWNLOAD_TICKET_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    raw = str(token or "").strip()
    if not raw:
        raise DownloadTicketError("download ticket is required")
    try:
        payload = _serializer().loads(raw, max_age=max_age_seconds)
    except SignatureExpired as exc:
        raise DownloadTicketError("download ticket expired") from exc
    except BadSignature as exc:
        raise DownloadTicketError("download ticket is invalid") from exc
    if not isinstance(payload, dict):
        raise DownloadTicketError("download ticket payload is invalid")
    if str(payload.get("kind") or "") != expected_kind:
        raise DownloadTicketError("download ticket kind is invalid")
    return payload
