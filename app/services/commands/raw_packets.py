# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Readiness checks and policy helpers for opt-in raw-packet scanners."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
from typing import Any, Mapping

CAP_NET_RAW_BIT = 13
RAW_PACKET_TOOLS = ("nmap", "naabu", "masscan")
_EXPECTED_FILE_CAPABILITY = "cap_net_raw"
# The root entrypoint creates this fixed, non-writable marker before dropping privileges.
_RAW_PACKET_FIREWALL_READY_FILE = Path("/tmp/darklab-raw-packet-firewall.ready")  # nosec B108
_NMAP_RAW_SCAN_MODES = {
    "-sA", "-sF", "-sI", "-sM", "-sN", "-sO", "-sS",
    "-sU", "-sW", "-sX", "-sY", "-sZ",
}
_NMAP_SCAN_MODES = _NMAP_RAW_SCAN_MODES | {"-sL", "-sT", "-sn"}
_NMAP_RAW_FEATURES = {
    "-A", "-O", "--osscan-guess", "--osscan-limit", "--traceroute",
    "-PE", "-PP", "-PM", "-PS", "-PA", "-PU", "-PY", "-PR", "-PO",
    "-f", "--mtu", "--send-ip", "-e", "-g", "--source-port",
    "--data", "--data-string", "--data-length", "--ip-options", "--ttl",
    "--badsum", "--adler32",
}
_NMAP_ALWAYS_DENIED_OPTIONS = {
    "--privileged": "the app owns Nmap's trusted privilege setting",
    "-D": "decoy source spoofing is unavailable",
    "-S": "source-address spoofing is unavailable",
    "--spoof-mac": "MAC-address spoofing is unavailable",
    "--send-eth": "link-layer sending bypasses the app's OUTPUT policy",
}


def _split_argv(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return command.strip().split()


def _proc_status_fields(path: Path = Path("/proc/self/status")) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    fields: dict[str, str] = {}
    for line in lines:
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip()
    return fields


def _file_capabilities(binary_path: str) -> str:
    getcap = shutil.which("getcap")
    if not getcap:
        return ""
    try:
        result = subprocess.run(
            [getcap, binary_path],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip().lower()


def _has_effective_permitted_file_capability(capabilities: str, capability: str) -> bool:
    for token in capabilities.lower().split():
        if capability not in token:
            continue
        separator = "=" if "=" in token else "+" if "+" in token else ""
        modes = token.rsplit(separator, 1)[-1] if separator else ""
        return "e" in modes and "p" in modes
    return False


def _restricted_cidr_firewall_state() -> tuple[bool, tuple[str, ...]]:
    try:
        marker_stat = _RAW_PACKET_FIREWALL_READY_FILE.stat()
        values = tuple(
            line.strip()
            for line in _RAW_PACKET_FIREWALL_READY_FILE.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    except OSError:
        return False, ()
    protected = marker_stat.st_uid == 0 and not marker_stat.st_mode & 0o022
    return protected, values


@lru_cache(maxsize=1)
def _raw_packet_system_readiness() -> dict[str, Any]:
    status_fields = _proc_status_fields()
    try:
        bounding_set = int(status_fields.get("CapBnd", "0"), 16)
    except ValueError:
        bounding_set = 0
    cap_net_raw_bounded = bool(bounding_set & (1 << CAP_NET_RAW_BIT))
    no_new_privileges = status_fields.get("NoNewPrivs", "0") == "1"

    tools: dict[str, dict[str, Any]] = {}
    for tool in RAW_PACKET_TOOLS:
        binary_path = shutil.which(tool) or ""
        capabilities = _file_capabilities(binary_path) if binary_path else ""
        file_cap_net_raw = _has_effective_permitted_file_capability(capabilities, _EXPECTED_FILE_CAPABILITY)
        tools[tool] = {
            "available": bool(binary_path and file_cap_net_raw),
            "binary_present": bool(binary_path),
            "file_cap_net_raw": file_cap_net_raw,
            "path": binary_path,
        }

    firewall_ready, firewall_cidrs = _restricted_cidr_firewall_state()

    return {
        "linux": sys.platform.startswith("linux"),
        "cap_net_raw_bounded": cap_net_raw_bounded,
        "no_new_privileges": no_new_privileges,
        "restricted_cidr_firewall_ready": firewall_ready,
        "restricted_cidr_firewall_cidrs": firewall_cidrs,
        "tools": tools,
    }


def clear_raw_packet_readiness_cache() -> None:
    _raw_packet_system_readiness.cache_clear()


def raw_packet_runtime_status(
    cfg: Mapping[str, Any] | None,
    *,
    tool: str = "nmap",
) -> dict[str, Any]:
    configured = bool((cfg or {}).get("raw_packet_scanning_enabled", False))
    system = _raw_packet_system_readiness()
    tool_status = dict(system.get("tools", {}).get(tool, {}))
    availability_reason = "ready"
    if not system.get("linux"):
        availability_reason = "linux_required"
    elif system.get("no_new_privileges"):
        availability_reason = "no_new_privileges"
    elif not system.get("cap_net_raw_bounded"):
        availability_reason = "cap_net_raw_not_bounded"
    elif not tool_status.get("binary_present"):
        availability_reason = "scanner_binary_missing"
    elif not tool_status.get("file_cap_net_raw"):
        availability_reason = "scanner_file_capability_missing"
    elif (
        tool == "nmap"
        and (restricted_cidrs := tuple(str(value) for value in (cfg or {}).get("restricted_command_input_cidrs", [])))
        and (
            not system.get("restricted_cidr_firewall_ready")
            or tuple(system.get("restricted_cidr_firewall_cidrs", ())) != restricted_cidrs
        )
    ):
        availability_reason = "restricted_cidr_firewall_unavailable"
    elif tool in {"naabu", "masscan"} and bool((cfg or {}).get("restricted_command_input_cidrs")):
        availability_reason = "packet_socket_egress_policy_required"

    available = availability_reason == "ready"
    return {
        "configured": configured,
        "available": available,
        "active": configured and available,
        "reason": availability_reason if configured else "disabled",
        "availability_reason": availability_reason,
        "tool": tool,
        "linux": bool(system.get("linux")),
        "cap_net_raw_bounded": bool(system.get("cap_net_raw_bounded")),
        "no_new_privileges": bool(system.get("no_new_privileges")),
        "binary_present": bool(tool_status.get("binary_present")),
        "file_cap_net_raw": bool(tool_status.get("file_cap_net_raw")),
        "path": str(tool_status.get("path") or ""),
    }


def raw_packet_scanning_active(cfg: Mapping[str, Any] | None, *, tool: str = "nmap") -> bool:
    return bool(raw_packet_runtime_status(cfg, tool=tool)["active"])


def raw_packet_unavailable_message(cfg: Mapping[str, Any] | None, *, tool: str) -> str:
    status = raw_packet_runtime_status(cfg, tool=tool)
    reasons = {
        "disabled": "raw-packet scanning is disabled by the operator",
        "linux_required": "raw-packet scanning requires a Linux container host",
        "no_new_privileges": "the container's no-new-privileges policy blocks scanner file capabilities",
        "cap_net_raw_not_bounded": "CAP_NET_RAW is missing from the container capability bounding set",
        "scanner_binary_missing": f"the {tool} scanner binary is missing",
        "scanner_file_capability_missing": f"the {tool} binary is missing its CAP_NET_RAW file capability",
        "restricted_cidr_firewall_unavailable": "the restricted-CIDR firewall rules are not confirmed",
        "packet_socket_egress_policy_required": (
            f"{tool} packet-socket traffic needs a host or bridge restricted-CIDR policy"
        ),
    }
    return reasons.get(str(status.get("reason")), "raw-packet scanning is unavailable")


def _nmap_scan_mode(token: str) -> str:
    return next((
        flag
        for flag in _NMAP_SCAN_MODES
        if token == flag
        or token.startswith(f"{flag}=")
        or (token.startswith("-s") and token.startswith(flag) and len(token) > len(flag))
    ), "")


def _nmap_option_requested(token: str, option: str) -> bool:
    if option.startswith("--"):
        return token == option or token.startswith(f"{option}=")
    return token == option or token.startswith(option)


def nmap_raw_scan_restriction_reason(
    command: str,
    *,
    raw_packets_active: bool = False,
    unavailable_reason: str = "raw-packet scanning is unavailable",
) -> str:
    tokens = _split_argv(command)
    if not tokens or tokens[0].lower() != "nmap":
        return ""
    for token in tokens[1:]:
        blocked = next((option for option in _NMAP_ALWAYS_DENIED_OPTIONS if _nmap_option_requested(token, option)), "")
        if blocked:
            return f"nmap {blocked} is blocked: {_NMAP_ALWAYS_DENIED_OPTIONS[blocked]}."
    requested_raw_options: list[str] = []
    for token in tokens[1:]:
        mode = _nmap_scan_mode(token)
        feature = next((
            flag for flag in _NMAP_RAW_FEATURES
            if _nmap_option_requested(token, flag)
        ), "")
        if mode in _NMAP_RAW_SCAN_MODES or feature:
            requested = mode or feature
            requested_raw_options.append(requested)
            if raw_packets_active:
                continue
            return (
                f"nmap raw mode ({requested}) requires raw-packet readiness; "
                f"{unavailable_reason}. Use -sT for a TCP connect scan."
            )
    if raw_packets_active and "-sT" in tokens and requested_raw_options:
        return (
            f"nmap -sT cannot be combined with raw option ({requested_raw_options[0]}) in this app; "
            "remove -sT to use the capability-backed scan or remove the raw option."
        )
    return ""


def raw_packet_command_restriction_reason(command: str, cfg: Mapping[str, Any]) -> str:
    tokens = _split_argv(command)
    root = tokens[0].lower() if tokens else ""
    if root == "nmap":
        reason = nmap_raw_scan_restriction_reason(
            command,
            raw_packets_active=raw_packet_scanning_active(cfg, tool=root),
            unavailable_reason=raw_packet_unavailable_message(cfg, tool=root),
        )
        if reason:
            return reason
    if root == "masscan" and not any(token in {"-h", "--help"} for token in tokens[1:]):
        if not raw_packet_scanning_active(cfg, tool=root):
            return f"masscan requires raw-packet readiness; {raw_packet_unavailable_message(cfg, tool=root)}."
    if root == "naabu" and not raw_packet_scanning_active(cfg, tool=root):
        for index, token in enumerate(tokens[1:], start=1):
            if token.startswith(("-scan-type=", "-st=")):
                scan_type = token.split("=", 1)[1]
            elif token in {"-scan-type", "-st"} and index + 1 < len(tokens):
                scan_type = tokens[index + 1]
            else:
                continue
            if scan_type.lower() not in {"c", "connect"}:
                return (
                    "naabu SYN mode requires raw-packet readiness; "
                    f"{raw_packet_unavailable_message(cfg, tool=root)}. Use -scan-type c instead."
                )
    return ""


def raw_packet_diagnostics(cfg: Mapping[str, Any]) -> dict[str, Any]:
    tools = {tool: raw_packet_runtime_status(cfg, tool=tool) for tool in RAW_PACKET_TOOLS}
    return {**tools["nmap"], "tools": tools}


def scan_transport(command: str, cfg: Mapping[str, Any] | None) -> str:
    tokens = _split_argv(command)
    while tokens and tokens[0] == "env":
        tokens = tokens[1:]
        while tokens and "=" in tokens[0] and not tokens[0].startswith("-"):
            tokens = tokens[1:]
    if not tokens:
        return ""
    root = tokens[0].lower()
    if any(token in {"-h", "--help", "-help", "-V", "--version"} for token in tokens[1:]):
        return ""
    if root == "nmap":
        if "-sL" in tokens:
            return ""
        return "connect" if "-sT" in tokens else ("raw" if raw_packet_scanning_active(cfg, tool=root) else "connect")
    if root == "naabu":
        for index, token in enumerate(tokens[1:], start=1):
            if token.startswith(("-scan-type=", "-st=")):
                scan_type = token.split("=", 1)[1]
                return "connect" if scan_type.lower() in {"c", "connect"} else "raw"
            if token in {"-scan-type", "-st"}:
                if index + 1 < len(tokens):
                    return "connect" if tokens[index + 1].lower() in {"c", "connect"} else "raw"
                return ""
        return "raw" if raw_packet_scanning_active(cfg, tool=root) else "connect"
    if root == "masscan":
        return "raw"
    return ""


def scan_transport_log_context(command: str, cfg: Mapping[str, Any] | None) -> dict[str, str]:
    transport = scan_transport(command, cfg)
    return {"scan_transport": transport} if transport else {}
