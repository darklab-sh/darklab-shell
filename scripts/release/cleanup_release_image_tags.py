#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Delete expired release-image attempt and rehearsal tags through GitLab's API."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterator
from typing import Any


TEMPORARY_TAG_RE = re.compile(
    r"^(?:"
    r"[0-9]+\.[0-9]+\.[0-9]+(?:-rc\.[0-9]+)?-(?:staging-[0-9]+-[0-9a-f]{12}-(?:amd64|arm64)|index-staging-[0-9]+-[0-9a-f]{12})"
    r"|multiarch-rehearsal-[0-9a-f]+-[0-9]+(?:-staging-[0-9]+-[0-9a-f]{12}-(?:amd64|arm64)|-index-staging-[0-9]+-[0-9a-f]{12}|-(?:amd64|arm64))?"
    r")$"
)


class GitLabApi:
    def __init__(self, *, api_url: str, token: str) -> None:
        self.api_url = api_url.rstrip("/")
        self.token = token

    def request(self, path: str, *, method: str = "GET") -> tuple[Any, str]:
        request = urllib.request.Request(
            f"{self.api_url}{path}",
            method=method,
            headers={"PRIVATE-TOKEN": self.token, "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
                value = json.loads(body) if body else None
                return value, response.headers.get("X-Next-Page", "")
        except (urllib.error.URLError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"GitLab API request failed: {method} {path}") from exc

    def pages(self, path: str) -> Iterator[list[dict[str, Any]]]:
        page = "1"
        while page:
            separator = "&" if "?" in path else "?"
            value, page = self.request(f"{path}{separator}per_page=100&page={page}")
            if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
                raise RuntimeError(f"GitLab API returned an unexpected list response: {path}")
            yield value


def _parse_timestamp(value: object) -> dt.datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("temporary registry tag is missing created_at")
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.UTC)


def find_repository_id(
    api: GitLabApi,
    *,
    project_id: str,
    registry_path: str,
) -> int:
    project = urllib.parse.quote(project_id, safe="")
    for page in api.pages(f"/projects/{project}/registry/repositories"):
        for repository in page:
            if repository.get("path") == registry_path:
                repository_id = repository.get("id")
                if isinstance(repository_id, int):
                    return repository_id
    raise RuntimeError(f"GitLab registry repository was not found: {registry_path}")


def cleanup_tags(
    *,
    api: GitLabApi,
    project_id: str,
    repository_id: int,
    keep_days: int,
    now: dt.datetime,
    dry_run: bool,
) -> list[str]:
    project = urllib.parse.quote(project_id, safe="")
    cutoff = now - dt.timedelta(days=keep_days)
    expired: list[str] = []
    path = f"/projects/{project}/registry/repositories/{repository_id}/tags"
    for page in api.pages(path):
        for tag in page:
            name = tag.get("name")
            if not isinstance(name, str) or TEMPORARY_TAG_RE.fullmatch(name) is None:
                continue
            encoded_name = urllib.parse.quote(name, safe="")
            detail, _ = api.request(f"{path}/{encoded_name}")
            if not isinstance(detail, dict):
                raise RuntimeError(f"GitLab API returned an unexpected tag response: {name}")
            if _parse_timestamp(detail.get("created_at")) >= cutoff:
                continue
            expired.append(name)

    deleted: list[str] = []
    for name in expired:
        encoded_name = urllib.parse.quote(name, safe="")
        print(f"{'Would delete' if dry_run else 'Deleting'} expired registry tag {name}")
        if not dry_run:
            api.request(f"{path}/{encoded_name}", method="DELETE")
        deleted.append(name)
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--registry-path", required=True)
    parser.add_argument("--keep-days", type=int, default=14)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if args.keep_days < 1:
        parser.error("--keep-days must be at least 1")
    api = GitLabApi(api_url=args.api_url, token=args.token)
    repository_id = find_repository_id(
        api,
        project_id=args.project_id,
        registry_path=args.registry_path,
    )
    deleted = cleanup_tags(
        api=api,
        project_id=args.project_id,
        repository_id=repository_id,
        keep_days=args.keep_days,
        now=dt.datetime.now(dt.UTC),
        dry_run=args.dry_run,
    )
    print(f"Matched {len(deleted)} expired temporary registry tag(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
