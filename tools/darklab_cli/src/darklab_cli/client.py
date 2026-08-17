# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Small urllib-based API client for the darklab CLI."""

from __future__ import annotations

import json
import os
import re
import sys
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


class DarklabCliError(Exception):
    pass


@dataclass(frozen=True)
class DarklabConfig:
    api_url: str
    token: str
    timeout: float = 30.0
    team: str = ""


def load_config(args: Any) -> DarklabConfig:
    file_config = _load_config_file()
    api_url = (
        getattr(args, "api_url", None)
        or os.environ.get("DARKLAB_API_URL")
        or file_config.get("api_url")
        or "http://localhost:8888"
    )
    token = (
        getattr(args, "token", None)
        or os.environ.get("DARKLAB_TOKEN")
        or file_config.get("token")
        or ""
    )
    team = (
        getattr(args, "team", None)
        or os.environ.get("DARKLAB_TEAM")
        or file_config.get("team")
        or ""
    )
    timeout_value = getattr(args, "timeout", None) or os.environ.get("DARKLAB_TIMEOUT") or file_config.get("timeout") or 30
    try:
        timeout = float(timeout_value)
    except (TypeError, ValueError):
        timeout = 30.0
    return DarklabConfig(api_url=_normalize_api_url(api_url), token=str(token), timeout=max(1.0, timeout), team=str(team))


def _normalize_api_url(value: object) -> str:
    url = str(value or "").strip().rstrip("/")
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise DarklabCliError("api_url must include http:// or https:// and a host.")
    return url


def _load_config_file() -> dict[str, Any]:
    path = Path.home() / ".config" / "darklab" / "config.toml"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        payload = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise DarklabCliError(f"invalid CLI config TOML: {exc}") from exc
    if not isinstance(payload, dict):
        return {}
    supported = {"api_url", "token", "timeout", "team"}
    return {key: value for key, value in payload.items() if key in supported}


def config_file_path() -> Path:
    return Path.home() / ".config" / "darklab" / "config.toml"


def _secure_config_file(path: Path) -> None:
    try:
        path.chmod(0o600)
    except OSError as exc:
        raise DarklabCliError(f"failed to secure CLI config permissions: {exc}") from exc


_TOP_LEVEL_ASSIGNMENT_RE = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_-]*)\s*=")


def _line_ending(line: str) -> str:
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    return "\n"


def _inline_comment_suffix(line: str) -> str:
    in_single = False
    in_double = False
    escaped = False
    for index, char in enumerate(line.rstrip("\r\n")):
        if escaped:
            escaped = False
            continue
        if in_double and char == "\\":
            escaped = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            continue
        if char == "#" and not in_single and not in_double:
            prefix = " " if index > 0 and not line[index - 1].isspace() else ""
            return prefix + line[index:].rstrip("\r\n")
    return ""


def _render_config_assignment(key: str, value: str, *, comment: str = "", newline: str = "\n") -> str:
    if key == "timeout":
        rendered = f"{float(value)!r}"
    else:
        rendered = json.dumps(str(value))
    return f"{key} = {rendered}{comment}{newline}"


def _update_config_text(text: str, key: str, value: str) -> str:
    lines = text.splitlines(keepends=True)
    output: list[str] = []
    in_table = False
    updated = False
    first_table_index: int | None = None

    for line in lines:
        stripped = line.lstrip()
        if stripped.startswith("["):
            in_table = True
            if first_table_index is None:
                first_table_index = len(output)
        match = _TOP_LEVEL_ASSIGNMENT_RE.match(line) if not in_table else None
        if match and match.group(2) == key:
            updated = True
            if value:
                output.append(
                    _render_config_assignment(
                        key,
                        value,
                        comment=_inline_comment_suffix(line),
                        newline=_line_ending(line),
                    )
                )
            continue
        output.append(line)

    if not updated and value:
        insertion = _render_config_assignment(key, value)
        if first_table_index is None:
            if output and not output[-1].endswith(("\n", "\r\n")):
                output[-1] += "\n"
            output.append(insertion)
        else:
            output.insert(first_table_index, insertion)
    return "".join(output)


def save_config_value(key: str, value: str) -> None:
    if key not in {"api_url", "token", "timeout", "team"}:
        raise DarklabCliError(f"unsupported config key: {key}")
    _load_config_file()
    path = config_file_path()
    try:
        current_text = path.read_text(encoding="utf-8")
    except OSError:
        current_text = ""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_update_config_text(current_text, key, value), encoding="utf-8")
    _secure_config_file(path)


class DarklabClient:
    def __init__(self, config: DarklabConfig) -> None:
        self.config = config

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
        stream: bool = False,
    ) -> Any:
        url = self._url(path, params)
        data = None
        headers = {"Accept": "application/json"}
        if self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"
        if self.config.team:
            headers["X-Team-ID"] = self.config.team
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            resp = urllib.request.urlopen(req, timeout=self.config.timeout)  # nosec
        except urllib.error.HTTPError as exc:
            message = _error_message(exc)
            raise DarklabCliError(message) from exc
        except urllib.error.URLError as exc:
            raise DarklabCliError(str(exc.reason)) from exc
        if stream:
            return resp
        raw = resp.read()
        if not raw:
            return {}
        content_type = resp.headers.get("Content-Type", "")
        if "json" not in content_type:
            return raw.decode("utf-8", errors="replace")
        return json.loads(raw.decode("utf-8"))

    def download(self, path: str, out_dir: str | Path, *, params: dict[str, Any] | None = None) -> Path:
        resp = self.request("GET", path, params=params, stream=True)
        disposition = resp.headers.get("Content-Disposition", "")
        filename = _safe_download_filename(_download_filename(disposition) or Path(path).name or "artifact")
        target_dir = Path(out_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / filename
        if target.exists():
            raise DarklabCliError(f"refusing to overwrite existing file: {target}")
        with target.open("wb") as handle:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
        return target

    def _url(self, path: str, params: dict[str, Any] | None = None) -> str:
        route = "/" + str(path or "").lstrip("/")
        if not route.startswith("/api/v1/"):
            route = "/api/v1" + route
        query = ""
        if params:
            clean = {key: value for key, value in params.items() if value not in (None, "", [])}
            if clean:
                query = "?" + urllib.parse.urlencode(clean, doseq=True)
        return self.config.api_url + route + query


def iter_sse_events(response) -> Iterator[dict[str, Any]]:
    event_id = ""
    data_lines: list[str] = []
    for raw_line in response:
        line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
        if not line:
            if data_lines:
                payload = json.loads("\n".join(data_lines))
                if event_id and isinstance(payload, dict):
                    payload.setdefault("event_id", event_id)
                yield payload
            event_id = ""
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("id:"):
            event_id = line[3:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].strip())


def _error_message(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace")
        payload = json.loads(body) if body else {}
    except Exception:
        payload = {}
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        code = str(error.get("code") or exc.code)
        message = str(error.get("message") or exc.reason)
        return f"{code}: {message}"
    if isinstance(error, str):
        return error
    return f"HTTP {exc.code}: {exc.reason}"


def _download_filename(disposition: str) -> str:
    extended = ""
    fallback = ""
    for part in str(disposition or "").split(";"):
        part = part.strip()
        lower = part.lower()
        if lower.startswith("filename*="):
            extended = part.split("=", 1)[1].strip().strip('"')
        elif lower.startswith("filename="):
            fallback = part.split("=", 1)[1].strip().strip('"')
    if extended:
        value = extended
        encoding = "utf-8"
        if "''" in value:
            raw_encoding, value = value.split("''", 1)
            encoding = raw_encoding or encoding
        try:
            return urllib.parse.unquote(value, encoding=encoding, errors="replace")
        except LookupError:
            return urllib.parse.unquote(value, encoding="utf-8", errors="replace")
    return fallback


def _safe_download_filename(value: str) -> str:
    filename = str(value or "").replace("\\", "/")
    path = Path(filename)
    if path.is_absolute() or ".." in path.parts:
        raise DarklabCliError("download filename contains an unsafe path")
    basename = path.name
    if basename in {"", ".", ".."}:
        raise DarklabCliError("download filename is empty or unsafe")
    return basename


def print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def die(message: str) -> int:
    print(message, file=sys.stderr)
    return 1
