"""Small urllib-based API client for darklab CLI."""

from __future__ import annotations

import json
import os
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
    timeout_value = getattr(args, "timeout", None) or os.environ.get("DARKLAB_TIMEOUT") or file_config.get("timeout") or 30
    try:
        timeout = float(timeout_value)
    except (TypeError, ValueError):
        timeout = 30.0
    return DarklabConfig(api_url=_normalize_api_url(api_url), token=str(token), timeout=max(1.0, timeout))


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
    supported = {"api_url", "token", "timeout"}
    return {key: value for key, value in payload.items() if key in supported}


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
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
        try:
            resp = urllib.request.urlopen(req, timeout=self.config.timeout)  # nosec B310 - user-configured API URL
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
