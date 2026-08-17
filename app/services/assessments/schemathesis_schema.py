# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Review local OpenAPI JSON before Schemathesis can consume it."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import re
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit

from services.intel.canonical import CanonicalizationError, canonical_url


SCHEMATHESIS_SCHEMA_MAX_BYTES = 1_048_576
SCHEMATHESIS_SCHEMA_MAX_NODES = 50_000
SCHEMATHESIS_SCHEMA_MAX_DEPTH = 64
SCHEMATHESIS_READ_OPERATION_LIMIT = 20
_ARTIFACT_ID_RE = re.compile(r"rfa_[0-9a-f]{16}")
_READ_METHODS = frozenset({"get", "head"})


class SchemathesisSchemaError(ValueError):
    """A stable rejection for an unsafe or unsupported API schema."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ReviewedOpenApiSchema:
    """Immutable metadata and bytes from one locally reviewed OpenAPI artifact."""

    source_artifact_id: str
    source_sha256: str
    base_url: str
    schema_version: str
    operations: tuple[str, ...]
    content: bytes = field(repr=False)

    @property
    def operation_count(self) -> int:
        return len(self.operations)


def review_local_openapi_json(
    content: bytes,
    *,
    source_artifact_id: str,
    base_url: str,
) -> ReviewedOpenApiSchema:
    """Return a bounded local-schema contract or reject it before execution."""
    if not _ARTIFACT_ID_RE.fullmatch(str(source_artifact_id or "")):
        raise SchemathesisSchemaError(
            "invalid_source_artifact",
            "Schemathesis requires one saved Project run-file artifact.",
        )
    if not isinstance(content, bytes) or not content or len(content) > SCHEMATHESIS_SCHEMA_MAX_BYTES:
        raise SchemathesisSchemaError(
            "invalid_schema_size",
            "OpenAPI JSON must be non-empty and no larger than 1 MiB.",
        )
    approved_base = _review_base_url(base_url)
    document = _decode_document(content)
    version = str(document.get("openapi") or "")
    if not (version.startswith("3.0.") or version.startswith("3.1.")):
        raise SchemathesisSchemaError(
            "unsupported_openapi_version",
            "Schemathesis supports reviewed OpenAPI 3.0 and 3.1 documents.",
        )
    _review_document_values(document)
    if "servers" in document:
        _review_servers(document["servers"], approved_base)
    operations = _read_operations(document.get("paths"), approved_base)
    if not operations:
        raise SchemathesisSchemaError(
            "no_read_operations",
            "OpenAPI JSON must define at least one GET or HEAD operation.",
        )
    if len(operations) > SCHEMATHESIS_READ_OPERATION_LIMIT:
        raise SchemathesisSchemaError(
            "operation_limit_exceeded",
            f"OpenAPI JSON exceeds the {SCHEMATHESIS_READ_OPERATION_LIMIT}-operation review limit.",
        )
    return ReviewedOpenApiSchema(
        source_artifact_id=source_artifact_id,
        source_sha256=hashlib.sha256(content).hexdigest(),
        base_url=approved_base,
        schema_version=version,
        operations=tuple(operations),
        content=content,
    )


def _review_base_url(value: str) -> str:
    raw = str(value or "").strip()
    parts = urlsplit(raw)
    if parts.username or parts.password or parts.query or parts.fragment:
        raise SchemathesisSchemaError(
            "invalid_base_url",
            "The reviewed API base URL cannot contain credentials, a query, or a fragment.",
        )
    try:
        reviewed = canonical_url(raw)
    except CanonicalizationError as exc:
        raise SchemathesisSchemaError(
            "invalid_base_url",
            "The reviewed API base URL must be an HTTP or HTTPS URL.",
        ) from exc
    reviewed = reviewed.rstrip("/")
    _safe_path(urlsplit(reviewed).path, code="invalid_base_url")
    return reviewed


def _decode_document(content: bytes) -> dict[str, Any]:
    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise SchemathesisSchemaError(
                    "duplicate_schema_key",
                    "OpenAPI JSON cannot contain duplicate object keys.",
                )
            result[key] = value
        return result

    def reject_constant(_value: str) -> None:
        raise ValueError

    try:
        document = json.loads(
            content.decode("utf-8"),
            object_pairs_hook=unique_object,
            parse_constant=reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        if isinstance(exc, SchemathesisSchemaError):
            raise
        raise SchemathesisSchemaError(
            "invalid_openapi_json",
            "The selected artifact is not strict UTF-8 OpenAPI JSON.",
        ) from exc
    if not isinstance(document, dict):
        raise SchemathesisSchemaError(
            "invalid_openapi_document",
            "OpenAPI JSON must contain one object at the document root.",
        )
    return document


def _review_document_values(document: dict[str, Any]) -> None:
    stack: list[tuple[Any, int]] = [(document, 0)]
    node_count = 0
    while stack:
        value, depth = stack.pop()
        node_count += 1
        if node_count > SCHEMATHESIS_SCHEMA_MAX_NODES or depth > SCHEMATHESIS_SCHEMA_MAX_DEPTH:
            raise SchemathesisSchemaError(
                "schema_complexity_exceeded",
                "OpenAPI JSON exceeds the bounded document complexity limit.",
            )
        if isinstance(value, dict):
            ref = value.get("$ref")
            if ref is not None and (
                not isinstance(ref, str) or not (ref == "#" or ref.startswith("#/"))
            ):
                raise SchemathesisSchemaError(
                    "external_schema_reference",
                    "OpenAPI JSON can use internal JSON Pointer references only.",
                )
            if "$id" in value:
                raise SchemathesisSchemaError(
                    "schema_base_override",
                    "OpenAPI JSON cannot override the reviewed schema base URI.",
                )
            stack.extend((child, depth + 1) for child in value.values())
        elif isinstance(value, list):
            stack.extend((child, depth + 1) for child in value)


def _review_servers(value: Any, base_url: str) -> None:
    if not isinstance(value, list):
        raise SchemathesisSchemaError(
            "invalid_schema_servers",
            "OpenAPI server declarations must be a list.",
        )
    base = urlsplit(base_url)
    base_path = _safe_path(base.path, code="invalid_base_url")
    for item in value:
        server_url = item.get("url") if isinstance(item, dict) else None
        if not isinstance(server_url, str) or "{" in server_url or "}" in server_url:
            raise SchemathesisSchemaError(
                "invalid_schema_server",
                "OpenAPI server URLs must be fixed strings inside the reviewed target scope.",
            )
        resolved = urlsplit(urljoin(base_url.rstrip("/") + "/", server_url))
        resolved_path = _safe_path(resolved.path, code="invalid_schema_server")
        in_path_scope = not base_path or resolved_path == base_path or resolved_path.startswith(base_path + "/")
        if (
            resolved.scheme != base.scheme
            or resolved.netloc != base.netloc
            or not in_path_scope
            or resolved.query
            or resolved.fragment
        ):
            raise SchemathesisSchemaError(
                "schema_server_out_of_scope",
                "OpenAPI server URLs must stay inside the reviewed API base URL.",
            )


def _read_operations(value: Any, base_url: str) -> list[str]:
    if not isinstance(value, dict):
        raise SchemathesisSchemaError(
            "invalid_openapi_paths",
            "OpenAPI JSON must define a paths object.",
        )
    operations: list[str] = []
    for path, path_item in value.items():
        if (
            not isinstance(path, str)
            or not path.startswith("/")
            or path.startswith("//")
            or not isinstance(path_item, dict)
        ):
            raise SchemathesisSchemaError(
                "invalid_openapi_path",
                "OpenAPI operation paths must be safe absolute API paths.",
            )
        _safe_path(path, code="invalid_openapi_path")
        if "servers" in path_item:
            _review_servers(path_item["servers"], base_url)
        for method in _READ_METHODS:
            if method in path_item:
                if not isinstance(path_item[method], dict):
                    raise SchemathesisSchemaError(
                        "invalid_openapi_operation",
                        "OpenAPI GET and HEAD operations must be objects.",
                    )
                if "servers" in path_item[method]:
                    _review_servers(path_item[method]["servers"], base_url)
                operations.append(f"{method.upper()} {path}")
    return sorted(operations)


def _safe_path(value: str, *, code: str) -> str:
    decoded = unquote(str(value or ""))
    if (
        "\\" in decoded
        or any(ord(char) < 32 for char in decoded)
        or any(part in {".", ".."} for part in decoded.split("/"))
    ):
        raise SchemathesisSchemaError(
            code,
            "OpenAPI URLs and operation paths cannot contain ambiguous path segments.",
        )
    return decoded.rstrip("/")


__all__ = [
    "ReviewedOpenApiSchema",
    "SCHEMATHESIS_READ_OPERATION_LIMIT",
    "SCHEMATHESIS_SCHEMA_MAX_BYTES",
    "SchemathesisSchemaError",
    "review_local_openapi_json",
]
