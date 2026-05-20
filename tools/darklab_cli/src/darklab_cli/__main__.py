"""Command line entry point for the darklab_shell API client."""

from __future__ import annotations

import argparse
import getpass
import json
from pathlib import Path
import sys
from typing import Any

from .client import DarklabClient, DarklabCliError, die, iter_sse_events, load_config, print_json

STREAM_INCOMPLETE_EXIT_CODE = 2


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="darklab")
    parser.add_argument("--api-url", help="darklab_shell base URL")
    parser.add_argument("--token", help="tok_ session token")
    parser.add_argument("--timeout", type=float, default=None, help="HTTP timeout in seconds")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("whoami")

    run = sub.add_parser("run")
    run.add_argument("run_command")
    run.add_argument("--project", dest="project_id")
    run.add_argument("--link-project", dest="link_project", help="Project name to resolve and link after completion.")
    run.add_argument("--wait", action="store_true", help="Wait for the run to finish instead of streaming output.")
    run.add_argument("--wait-timeout", type=float, default=None, help="Server-side wait timeout in seconds.")
    run.add_argument("--format", choices=("text", "json", "ndjson"), default="text")
    run_follow = run.add_mutually_exclusive_group()
    run_follow.add_argument("--follow", dest="follow", action="store_true", default=True)
    run_follow.add_argument("--no-follow", dest="follow", action="store_false")

    tail = sub.add_parser("tail")
    tail.add_argument("run_id")
    tail.add_argument("--format", choices=("text", "ndjson"), default="text")
    tail.add_argument("--after", default="")

    cancel = sub.add_parser("cancel")
    cancel.add_argument("run_id")

    history = sub.add_parser("history")
    history.add_argument("--project", dest="project_id")
    history.add_argument("--since")
    history.add_argument("--until")
    history.add_argument("--limit", type=int, default=50)
    history.add_argument("--offset", type=int, default=0)
    history.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    grep = sub.add_parser("grep")
    grep.add_argument("pattern")
    grep.add_argument("--context", type=int, default=2)
    grep.add_argument("--project", dest="project_id")
    grep.add_argument("--since")
    grep.add_argument("--until")
    grep.add_argument("--limit", type=int, default=50)
    grep.add_argument("--offset", type=int, default=0)
    grep.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    show = sub.add_parser("show")
    show.add_argument("run_id")
    show.add_argument("--lines", type=int, default=0)
    show.add_argument("--format", choices=("text", "json"), default="text")

    output = sub.add_parser("output")
    output.add_argument("run_id")
    output.add_argument("--range", dest="line_range", help="1-based line range to fetch, such as 10-40.")
    output.add_argument("--format", choices=("text", "json"), default="text")

    artifacts = sub.add_parser("artifacts")
    artifacts.add_argument("run_id")

    projects = sub.add_parser("projects")
    projects.add_argument("--format", choices=("text", "json", "ndjson"), default="text")
    projects.add_argument("--limit", type=int, default=50)
    projects.add_argument("--offset", type=int, default=0)

    project = sub.add_parser("project")
    project.add_argument("project_id")
    project.add_argument("--format", choices=("text", "json"), default="text")

    project_findings = sub.add_parser("project-findings")
    project_findings.add_argument("project_id")
    project_findings.add_argument("--limit", type=int, default=50)
    project_findings.add_argument("--offset", type=int, default=0)
    project_findings.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    project_runs = sub.add_parser("project-runs")
    project_runs.add_argument("project_id")
    project_runs.add_argument("--limit", type=int, default=50)
    project_runs.add_argument("--offset", type=int, default=0)
    project_runs.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    project_entities = sub.add_parser("project-entities")
    project_entities.add_argument("project_id")
    project_entities.add_argument("--entity-type")
    project_entities.add_argument("--limit", type=int, default=50)
    project_entities.add_argument("--offset", type=int, default=0)
    project_entities.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    project_packages = sub.add_parser("project-packages")
    project_packages.add_argument("project_id")
    project_packages.add_argument("--limit", type=int, default=50)
    project_packages.add_argument("--offset", type=int, default=0)
    project_packages.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    atlas = sub.add_parser("atlas")
    atlas_sub = atlas.add_subparsers(dest="atlas_command", required=True)

    atlas_summary = atlas_sub.add_parser("summary")
    _add_atlas_common_filters(atlas_summary, include_entity_type=False)
    atlas_summary.add_argument("--format", choices=("text", "json"), default="text")

    atlas_runs = atlas_sub.add_parser("runs")
    atlas_runs.add_argument("--q")
    atlas_runs.add_argument("--run-id")
    atlas_runs.add_argument("--limit", type=int, default=30)
    atlas_runs.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    atlas_entities = atlas_sub.add_parser("entities")
    _add_atlas_common_filters(atlas_entities)
    atlas_entities.add_argument("--limit", type=int, default=50)
    atlas_entities.add_argument("--offset", type=int, default=0)
    atlas_entities.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    atlas_entity = atlas_sub.add_parser("entity")
    atlas_entity.add_argument("entity_id")
    atlas_entity.add_argument("--format", choices=("text", "json"), default="text")

    atlas_findings = atlas_sub.add_parser("findings")
    _add_atlas_common_filters(atlas_findings, include_entity_type=False)
    atlas_findings.add_argument("--review-state", action="append", default=[])
    atlas_findings.add_argument("--limit", type=int, default=50)
    atlas_findings.add_argument("--offset", type=int, default=0)
    atlas_findings.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    atlas_finding = atlas_sub.add_parser("finding")
    atlas_finding.add_argument("finding_id")
    atlas_finding.add_argument("--format", choices=("text", "json"), default="text")

    download = sub.add_parser(
        "download",
        description="Download one run artifact. Use `darklab artifacts <run_id>` first to list artifact ids.",
    )
    download.add_argument("run_id")
    download.add_argument(
        "--artifact",
        required=True,
        help="Artifact id from `darklab artifacts <run_id>`.",
    )
    download.add_argument("--out", default=".", help="Destination directory.")

    notify = sub.add_parser("notify")
    notify_sub = notify.add_subparsers(dest="notify_command", required=True)

    notify_list = notify_sub.add_parser("list")
    notify_list.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    notify_create = notify_sub.add_parser("create")
    notify_create.add_argument("kind", choices=("webhook", "slack", "discord", "telegram", "pushover", "email"))
    notify_create.add_argument("--label")
    notify_create.add_argument("--trigger", action="append", default=[])
    notify_create.add_argument("--config", action="append", default=[], help="Channel config as KEY=VALUE.")
    notify_create.add_argument("--secret-file", help="JSON file containing write-only secret fields.")

    notify_delete = notify_sub.add_parser("delete")
    notify_delete.add_argument("channel_id")

    notify_test = notify_sub.add_parser("test")
    notify_test.add_argument("channel_id")
    notify_test.add_argument("--format", choices=("text", "json"), default="text")

    notify_events = notify_sub.add_parser("events")
    notify_events.add_argument("--status")
    notify_events.add_argument("--channel", dest="channel_id")
    notify_events.add_argument("--trigger")
    notify_events.add_argument("--limit", type=int, default=50)
    notify_events.add_argument("--offset", type=int, default=0)
    notify_events.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

    return parser


def _add_atlas_common_filters(parser: argparse.ArgumentParser, *, include_entity_type: bool = True) -> None:
    parser.add_argument("--q")
    parser.add_argument("--project", dest="project_id")
    parser.add_argument("--run-id")
    parser.add_argument("--orphan-filter", choices=("hide", "all", "only"), default="hide")
    parser.add_argument("--suppression-filter", choices=("hide", "all", "only"), default="hide")
    if include_entity_type:
        parser.add_argument("--entity-type", choices=("domain", "ip", "url", "hash", "cve"))


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        client = DarklabClient(load_config(args))
        return _dispatch(client, args)
    except DarklabCliError as exc:
        return die(str(exc))


def _dispatch(client: DarklabClient, args: argparse.Namespace) -> int:
    match args.command:
        case "whoami":
            return _print_payload(client.request("GET", "/whoami"), "json")
        case "run":
            return _run(client, args)
        case "tail":
            return _tail(client, args.run_id, args.format, after=args.after)
        case "cancel":
            return _print_payload(client.request("POST", f"/runs/{args.run_id}/cancel"), "json")
        case "history":
            payload = client.request("GET", "/history", params=_page_params(args))
            return _print_collection(
                payload,
                "runs",
                args.format,
                fields=("finished", "id", "status", "exit_code", "command"),
                reverse=True,
            )
        case "grep":
            params = {**_page_params(args), "q": args.pattern, "context": args.context}
            payload = client.request("GET", "/history/search", params=params)
            return _print_search_matches(payload, args.format)
        case "show":
            payload = client.request("GET", f"/history/{args.run_id}")
            if args.format == "json":
                return _print_payload(payload, "json")
            run = payload.get("run", {})
            print(f"{run.get('id')}  {run.get('status')}  {run.get('command')}")
            if args.lines:
                output = client.request("GET", f"/history/{args.run_id}/output", params={"format": "json"})
                for line in output.get("lines", [])[-args.lines:]:
                    print(line)
            return 0
        case "output":
            params = {"format": args.format, "range": args.line_range}
            if args.format == "json":
                return _print_payload(client.request("GET", f"/runs/{args.run_id}/output", params=params), "json")
            text = client.request("GET", f"/runs/{args.run_id}/output", params=params)
            print(text, end="" if str(text).endswith("\n") else "\n")
            return 0
        case "artifacts":
            payload = client.request("GET", f"/history/{args.run_id}/artifacts")
            return _print_collection(payload, "artifacts", "text", fields=("id", "byte_size", "display_name"))
        case "projects":
            payload = client.request("GET", "/projects", params=_page_params(args))
            return _print_collection(payload, "projects", args.format, fields=("id", "status", "name"))
        case "project":
            payload = client.request("GET", f"/projects/{args.project_id}")
            return _print_payload(payload, args.format)
        case "project-findings":
            payload = client.request("GET", f"/projects/{args.project_id}/findings", params=_page_window_params(args))
            return _print_collection(payload, "findings", args.format, fields=("id", "status", "severity", "title"))
        case "project-runs":
            payload = client.request("GET", f"/projects/{args.project_id}/runs", params=_page_window_params(args))
            return _print_collection(payload, "runs", args.format, fields=("started", "id", "exit_code", "command"))
        case "project-entities":
            params = {**_page_window_params(args), "entity_type": args.entity_type}
            payload = client.request("GET", f"/projects/{args.project_id}/entities", params=params)
            return _print_collection(payload, "entities", args.format, fields=("type", "id", "value"))
        case "project-packages":
            payload = client.request("GET", f"/projects/{args.project_id}/packages", params=_page_window_params(args))
            return _print_collection(payload, "packages", args.format, fields=("id", "status", "name"))
        case "atlas":
            return _atlas(client, args)
        case "notify":
            return _notify(client, args)
        case "download":
            target = client.download(
                f"/history/{args.run_id}/artifacts/{args.artifact}",
                args.out,
            )
            print(target)
            return 0
    return die("unknown command")


NOTIFICATION_SECRET_FIELDS = {
    "webhook": ("url",),
    "slack": ("url",),
    "discord": ("url",),
    "telegram": ("bot_token",),
    "pushover": ("app_token", "user_key"),
    "email": (),
}


def _notify(client: DarklabClient, args: argparse.Namespace) -> int:
    match args.notify_command:
        case "list":
            payload = client.request("GET", "/notification-channels")
            return _print_collection(payload, "channels", args.format, fields=("id", "kind", "muted", "label"))
        case "create":
            body = {
                "kind": args.kind,
                "label": args.label,
                "triggers": args.trigger,
                "config": _parse_key_values(args.config),
                "secret_values": _notification_secret_values(args.kind, args.secret_file),
            }
            payload = client.request("POST", "/notification-channels", body=body)
            channel = payload.get("channel") if isinstance(payload, dict) else {}
            if isinstance(channel, dict):
                print("  ".join(str(channel.get(field, "")) for field in ("id", "kind", "muted", "label")))
            return 0
        case "delete":
            return _print_payload(client.request("DELETE", f"/notification-channels/{args.channel_id}"), "json")
        case "test":
            payload = client.request("POST", f"/notification-channels/{args.channel_id}/test")
            if args.format == "json":
                return _print_payload(payload, "json")
            print(f"queued: {payload.get('queued', 0)}")
            for event_id in payload.get("event_ids", []):
                print(event_id)
            return 0
        case "events":
            payload = client.request("GET", "/notification-events", params={
                "status": args.status,
                "channel_id": args.channel_id,
                "trigger": args.trigger,
                "limit": args.limit,
                "offset": args.offset,
            })
            return _print_collection(
                payload,
                "events",
                args.format,
                fields=("created", "id", "status", "trigger", "channel_id", "run_id"),
            )
    return die("unknown notify command")


def _parse_key_values(values: list[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise DarklabCliError("--config values must use KEY=VALUE.")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise DarklabCliError("--config keys cannot be empty.")
        parsed[key] = value.strip()
    return parsed


def _notification_secret_values(kind: str, secret_file: str | None) -> dict[str, str]:
    expected = NOTIFICATION_SECRET_FIELDS.get(kind, ())
    if not expected:
        return {}
    if secret_file:
        path = Path(secret_file)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise DarklabCliError(f"could not read secret file: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise DarklabCliError(f"secret file must be JSON: {exc}") from exc
        if not isinstance(raw, dict):
            raise DarklabCliError("secret file must contain a JSON object.")
        values = {field: str(raw.get(field) or "") for field in expected}
    else:
        values = {field: getpass.getpass(f"{kind} {field}: ") for field in expected}
    missing = [field for field in expected if not str(values.get(field) or "").strip()]
    if missing:
        raise DarklabCliError(f"missing secret field(s): {', '.join(missing)}")
    return values


def _atlas(client: DarklabClient, args: argparse.Namespace) -> int:
    match args.atlas_command:
        case "summary":
            return _print_atlas_summary(client.request("GET", "/atlas", params=_atlas_filter_params(args)), args.format)
        case "runs":
            payload = client.request("GET", "/atlas/runs", params={
                "q": args.q,
                "run_id": args.run_id,
                "limit": args.limit,
            })
            return _print_collection(payload, "runs", args.format, fields=("id", "entity_count", "finding_count", "command"))
        case "entities":
            payload = client.request("GET", "/atlas/entities", params={**_atlas_filter_params(args), **_page_window_params(args)})
            return _print_collection(
                payload,
                "entities",
                args.format,
                fields=("type", "id", "occurrence_count", "canonical_value"),
            )
        case "entity":
            payload = client.request("GET", f"/atlas/entities/{args.entity_id}")
            if args.format == "json":
                return _print_payload(payload, "json")
            entity = payload.get("entity") if isinstance(payload, dict) else {}
            if isinstance(entity, dict):
                print("  ".join(str(entity.get(field, "")) for field in ("type", "id", "occurrence_count", "canonical_value")))
            return 0
        case "findings":
            params = {**_atlas_filter_params(args), **_page_window_params(args), "review_state": args.review_state}
            payload = client.request("GET", "/atlas/findings", params=params)
            return _print_collection(payload, "findings", args.format, fields=("id", "status", "severity", "title"))
        case "finding":
            payload = client.request("GET", f"/atlas/findings/{args.finding_id}")
            if args.format == "json":
                return _print_payload(payload, "json")
            finding = payload.get("finding") if isinstance(payload, dict) else {}
            if isinstance(finding, dict):
                print("  ".join(str(finding.get(field, "")) for field in ("id", "status", "severity", "title")))
            return 0
    return die("unknown atlas command")


def _atlas_filter_params(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "q": getattr(args, "q", None),
        "project_id": getattr(args, "project_id", None),
        "run_id": getattr(args, "run_id", None),
        "entity_type": getattr(args, "entity_type", None),
        "orphan_filter": getattr(args, "orphan_filter", None),
        "suppression_filter": getattr(args, "suppression_filter", None),
    }


def _print_atlas_summary(payload: dict[str, Any], output_format: str) -> int:
    if output_format == "json":
        return _print_payload(payload, "json")
    counts = payload.get("counts") if isinstance(payload, dict) else {}
    if not isinstance(counts, dict):
        counts = {}
    print(f"entities: {payload.get('total', 0)}")
    print(f"findings: {payload.get('findings', 0)}")
    for entity_type in sorted(counts):
        print(f"{entity_type}: {counts[entity_type]}")
    return 0


def _run(client: DarklabClient, args: argparse.Namespace) -> int:
    if args.project_id and args.link_project:
        return die("--project and --link-project cannot be used together.")
    if args.follow and args.format == "json":
        if not args.wait:
            return die(
                "--format json is start-only; use --no-follow --format json, "
                "--wait --format json, or --format ndjson to stream events."
            )
    if not args.follow and args.format == "ndjson":
        return die("--format ndjson is stream-only; remove --no-follow or use --format json.")
    if args.wait and args.format == "ndjson":
        return die("--format ndjson is stream-only; remove --wait or use --format json.")
    project_id = args.project_id or (_resolve_project_id(client, args.link_project) if args.link_project else None)
    payload = client.request(
        "POST",
        "/runs",
        body={"command": args.run_command, "project_id": project_id},
    )
    if args.wait:
        wait_params = {"timeout": args.wait_timeout}
        waited = client.request("POST", f"/runs/{payload['id']}/wait", params=wait_params)
        return _print_wait_result(waited, args.format)
    if not args.follow:
        return _print_payload(payload, args.format)
    return _tail(client, payload["id"], "ndjson" if args.format == "ndjson" else "text")


def _resolve_project_id(client: DarklabClient, name_or_id: object) -> str:
    needle = str(name_or_id or "").strip()
    if not needle:
        raise DarklabCliError("--link-project requires a project name.")
    matches: list[dict[str, Any]] = []
    offset = 0
    while True:
        payload = client.request("GET", "/projects", params={"limit": 100, "offset": offset})
        projects = payload.get("projects") if isinstance(payload, dict) else []
        if not isinstance(projects, list):
            break
        for project in projects:
            if not isinstance(project, dict):
                continue
            if str(project.get("id") or "") == needle:
                return str(project["id"])
            if str(project.get("name") or "").casefold() == needle.casefold():
                matches.append(project)
        offset += len(projects)
        if not payload.get("has_more") or not projects:
            break
    if len(matches) == 1:
        return str(matches[0]["id"])
    if matches:
        raise DarklabCliError(f"--link-project is ambiguous: {needle}")
    raise DarklabCliError(f"project not found: {needle}")


def _print_wait_result(payload: dict[str, Any], output_format: str) -> int:
    if output_format == "json":
        return _print_payload(payload, "json")
    run = payload.get("run") if isinstance(payload, dict) else {}
    if not isinstance(run, dict):
        return die("wait response did not include a run payload.")
    print("  ".join(str(run.get(field, "")) for field in ("id", "status", "exit_code", "command")))
    return _exit_code_from_run(run)


def _tail(client: DarklabClient, run_id: str, output_format: str, *, after: str = "") -> int:
    if output_format == "ndjson":
        response = client.request("GET", f"/runs/{run_id}/stream", params={"format": "ndjson", "after": after}, stream=True)
        exit_code = 0
        terminal_seen = False
        for raw in response:
            line = raw.decode("utf-8", errors="replace")
            print(line, end="")
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            exit_code = _exit_code_from_event(payload, exit_code)
            terminal_seen = terminal_seen or _is_terminal_event(payload)
        if not terminal_seen:
            return _stream_incomplete(run_id)
        return exit_code

    response = client.request("GET", f"/runs/{run_id}/stream", params={"after": after}, stream=True)
    exit_code = 0
    terminal_seen = False
    for event in iter_sse_events(response):
        if event.get("type") in {"output", "notice"} and event.get("text") is not None:
            sys.stdout.write(str(event.get("text")).rstrip("\r\n") + "\n")
        exit_code = _exit_code_from_event(event, exit_code)
        terminal_seen = terminal_seen or _is_terminal_event(event)
    if not terminal_seen:
        return _stream_incomplete(run_id)
    return exit_code


def _stream_incomplete(run_id: str) -> int:
    print(f"run stream ended before {run_id} reached a terminal event", file=sys.stderr)
    return STREAM_INCOMPLETE_EXIT_CODE


def _is_terminal_event(event: dict[str, Any]) -> bool:
    return str(event.get("type") or event.get("event") or "") in {"exit", "error", "killed"}


def _exit_code_from_event(event: dict[str, Any], current: int) -> int:
    event_type = str(event.get("type") or event.get("event") or "")
    if event_type == "exit":
        try:
            return int(event.get("code") or 0)
        except (TypeError, ValueError):
            return 1
    if event_type in {"error", "killed"}:
        return 1
    return current


def _exit_code_from_run(run: dict[str, Any]) -> int:
    status = str(run.get("status") or "")
    if status in {"failed", "killed", "error"}:
        return 1
    if run.get("exit_code") is None:
        return 0
    try:
        return int(run.get("exit_code") or 0)
    except (TypeError, ValueError):
        return 1


def _page_params(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "project_id": getattr(args, "project_id", None),
        "since": getattr(args, "since", None),
        "until": getattr(args, "until", None),
        "limit": getattr(args, "limit", None),
        "offset": getattr(args, "offset", None),
    }


def _page_window_params(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "limit": getattr(args, "limit", None),
        "offset": getattr(args, "offset", None),
    }


def _print_payload(payload: Any, output_format: str) -> int:
    if output_format == "json":
        print_json(payload)
        return 0
    if isinstance(payload, dict):
        for key, value in payload.items():
            print(f"{key}: {value}")
        return 0
    print(payload)
    return 0


def _print_collection(
    payload: dict[str, Any],
    key: str,
    output_format: str,
    *,
    fields: tuple[str, ...],
    reverse: bool = False,
) -> int:
    items = payload.get(key) if isinstance(payload, dict) else []
    if not isinstance(items, list):
        items = []
    if reverse:
        items = list(reversed(items))
    if output_format == "json":
        if isinstance(payload, dict):
            payload = {**payload, key: items}
        print_json(payload)
        return 0
    if output_format == "ndjson":
        for item in items:
            print(json.dumps(item, sort_keys=True))
        return 0
    for item in items:
        if not isinstance(item, dict):
            continue
        print("  ".join(str(item.get(field, "")) for field in fields))
    return 0


def _print_search_matches(payload: dict[str, Any], output_format: str) -> int:
    matches = payload.get("matches") if isinstance(payload, dict) else []
    if not isinstance(matches, list):
        matches = []
    if output_format == "json":
        print_json(payload)
        return 0
    if output_format == "ndjson":
        for match in matches:
            print(json.dumps(match, sort_keys=True))
        return 0
    for index, match in enumerate(matches):
        if not isinstance(match, dict):
            continue
        run_id = str(match.get("run_id") or "")
        try:
            line_number = int(match.get("line_number") or 0)
        except (TypeError, ValueError):
            line_number = 0
        before_value = match.get("context_before")
        after_value = match.get("context_after")
        before: list[Any] = before_value if isinstance(before_value, list) else []
        after: list[Any] = after_value if isinstance(after_value, list) else []
        before_start = line_number - len(before)
        for offset, line in enumerate(before):
            print(f"{run_id}:{before_start + offset}- {line}")
        print(f"{run_id}:{line_number}: {match.get('line', '')}")
        for offset, line in enumerate(after, start=1):
            print(f"{run_id}:{line_number + offset}+ {line}")
        if index < len(matches) - 1:
            print("--")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
