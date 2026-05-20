"""Command line entry point for the darklab API client."""

from __future__ import annotations

import argparse
import json
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

    show = sub.add_parser("show")
    show.add_argument("run_id")
    show.add_argument("--lines", type=int, default=0)
    show.add_argument("--format", choices=("text", "json"), default="text")

    output = sub.add_parser("output")
    output.add_argument("run_id")
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

    project_packages = sub.add_parser("project-packages")
    project_packages.add_argument("project_id")
    project_packages.add_argument("--limit", type=int, default=50)
    project_packages.add_argument("--offset", type=int, default=0)
    project_packages.add_argument("--format", choices=("text", "json", "ndjson"), default="text")

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

    return parser


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
            if args.format == "json":
                return _print_payload(client.request("GET", f"/history/{args.run_id}/output", params={"format": "json"}), "json")
            text = client.request("GET", f"/history/{args.run_id}/output", params={"format": "text"})
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
            payload = client.request("GET", f"/projects/{args.project_id}/findings", params=_page_params(args))
            return _print_collection(payload, "findings", args.format, fields=("id", "status", "severity", "title"))
        case "project-packages":
            payload = client.request("GET", f"/projects/{args.project_id}/packages", params=_page_params(args))
            return _print_collection(payload, "packages", args.format, fields=("id", "status", "name"))
        case "download":
            target = client.download(
                f"/history/{args.run_id}/artifacts/{args.artifact}",
                args.out,
            )
            print(target)
            return 0
    return die("unknown command")


def _run(client: DarklabClient, args: argparse.Namespace) -> int:
    if args.follow and args.format == "json":
        return die("--format json is start-only; use --no-follow --format json or --format ndjson to stream events.")
    if not args.follow and args.format == "ndjson":
        return die("--format ndjson is stream-only; remove --no-follow or use --format json.")
    payload = client.request(
        "POST",
        "/runs",
        body={"command": args.run_command, "project_id": args.project_id},
    )
    if not args.follow:
        return _print_payload(payload, args.format)
    return _tail(client, payload["id"], "ndjson" if args.format == "ndjson" else "text")


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


def _page_params(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "project_id": getattr(args, "project_id", None),
        "since": getattr(args, "since", None),
        "until": getattr(args, "until", None),
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


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
