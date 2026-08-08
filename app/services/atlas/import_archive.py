# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Read Atlas import uploads and expand supported archives within fixed bounds."""

from __future__ import annotations

from dataclasses import dataclass
import gzip
import hashlib
from io import BytesIO
from pathlib import PurePosixPath
import re
import stat
from typing import BinaryIO, IO
import zipfile

GZIP_MAGIC = b"\x1f\x8b"
ZIP_MAGICS = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
ZIP_MAX_ENTRIES = 16


class ImportSourceError(ValueError):
    """Safe source or archive error that can be shown in an import preview."""


@dataclass(frozen=True)
class PreparedImportSource:
    payload: bytes
    upload_bytes: int
    compression: str
    upload_sha256: str

    @property
    def expanded_bytes(self) -> int:
        return len(self.payload)


def _compression_kind(payload: bytes) -> str:
    if payload.startswith(GZIP_MAGIC):
        return "gzip"
    if payload.startswith(ZIP_MAGICS):
        return "zip"
    return "none"


def _read_upload(
    source: bytes | str | BinaryIO | IO[bytes],
    *,
    max_upload_bytes: int,
) -> bytes:
    if isinstance(source, bytes):
        payload = source
    elif isinstance(source, str):
        payload = source.encode("utf-8")
    else:
        payload = source.read(max_upload_bytes + 1)
    if len(payload) > max_upload_bytes:
        raise ImportSourceError(f"Import file exceeds the configured {max_upload_bytes} byte limit.")
    return payload


def _read_bounded(stream, *, max_expanded_bytes: int) -> bytes:
    payload = stream.read(max_expanded_bytes + 1)
    if len(payload) > max_expanded_bytes:
        raise ImportSourceError(
            f"Expanded import exceeds the configured {max_expanded_bytes} byte limit."
        )
    return payload


def _safe_zip_member(info: zipfile.ZipInfo) -> None:
    name = str(info.filename or "")
    path = PurePosixPath(name)
    if (
        not name
        or "\\" in name
        or name.startswith("/")
        or re.match(r"^[A-Za-z]:", name)
        or any(part in {"", ".", ".."} for part in path.parts)
        or any(ord(char) < 32 or ord(char) == 127 for char in name)
    ):
        raise ImportSourceError("ZIP import contains an unsafe report path.")
    if info.flag_bits & 0x1:
        raise ImportSourceError("Encrypted ZIP imports are not supported.")
    mode = info.external_attr >> 16
    if info.create_system == 3 and stat.S_IFMT(mode) not in {0, stat.S_IFREG}:
        raise ImportSourceError("ZIP import report must be a regular file.")


def _expand_gzip(payload: bytes, *, max_expanded_bytes: int) -> bytes:
    try:
        with gzip.GzipFile(fileobj=BytesIO(payload), mode="rb") as stream:
            return _read_bounded(stream, max_expanded_bytes=max_expanded_bytes)
    except ImportSourceError:
        raise
    except (EOFError, OSError) as exc:
        raise ImportSourceError("Gzip import is malformed or incomplete.") from exc


def _expand_zip(payload: bytes, *, max_expanded_bytes: int) -> bytes:
    try:
        with zipfile.ZipFile(BytesIO(payload), mode="r") as archive:
            entries = archive.infolist()
            if len(entries) > ZIP_MAX_ENTRIES:
                raise ImportSourceError(f"ZIP import exceeds the {ZIP_MAX_ENTRIES} entry limit.")
            members = [info for info in entries if not info.is_dir()]
            if len(members) != 1:
                raise ImportSourceError("ZIP import must contain exactly one report file.")
            member = members[0]
            _safe_zip_member(member)
            if member.file_size > max_expanded_bytes:
                raise ImportSourceError(
                    f"Expanded import exceeds the configured {max_expanded_bytes} byte limit."
                )
            with archive.open(member, mode="r") as stream:
                return _read_bounded(stream, max_expanded_bytes=max_expanded_bytes)
    except ImportSourceError:
        raise
    except (NotImplementedError, OSError, RuntimeError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise ImportSourceError("ZIP import is malformed or uses unsupported compression.") from exc


def prepare_import_source(
    source: bytes | str | BinaryIO | IO[bytes],
    *,
    max_upload_bytes: int,
    max_expanded_bytes: int,
) -> PreparedImportSource:
    uploaded = _read_upload(source, max_upload_bytes=max_upload_bytes)
    compression = _compression_kind(uploaded)
    if compression == "gzip":
        expanded = _expand_gzip(uploaded, max_expanded_bytes=max_expanded_bytes)
    elif compression == "zip":
        expanded = _expand_zip(uploaded, max_expanded_bytes=max_expanded_bytes)
    else:
        expanded = uploaded
        if len(expanded) > max_expanded_bytes:
            raise ImportSourceError(
                f"Expanded import exceeds the configured {max_expanded_bytes} byte limit."
            )
    if compression != "none" and _compression_kind(expanded) != "none":
        raise ImportSourceError("Nested compressed imports are not supported.")
    return PreparedImportSource(
        payload=expanded,
        upload_bytes=len(uploaded),
        compression=compression,
        upload_sha256=hashlib.sha256(uploaded).hexdigest(),
    )
