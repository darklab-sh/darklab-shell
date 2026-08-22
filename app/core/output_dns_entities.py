# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Record-aware entity extraction for dig and nslookup output."""

from __future__ import annotations

from collections.abc import Sequence
import re

from core.output_dns_command import clean_dns_host, parse_dns_command
from core.output_entities import (
    _DOMAIN_SUFFIX_EXTRACTOR,
    _add_entity,
    _domain_candidate_has_allowed_suffix,
    _entity_domain_labels,
    _is_public_ip,
)
from services.intel.canonical import CanonicalizationError, canonical_domain, canonical_ip


_DIG_RECORD_RE = re.compile(
    r"^(?P<owner>\S+)\s+(?:(?P<ttl>\d+)\s+)?(?:(?:IN|CH|HS)\s+)?"
    r"(?P<record_type>A|AAAA|ANY|CAA|CNAME|DNSKEY|DS|MX|NS|NSEC|NSEC3|NSEC3PARAM|"
    r"PTR|RRSIG|SOA|SRV|TXT)(?:\s+(?P<data>.*))?$",
    re.I,
)
_DIG_SECTION_RE = re.compile(r"^;;\s+(QUESTION|ANSWER|AUTHORITY|ADDITIONAL) SECTION:$", re.I)
_NSLOOKUP_CNAME_RE = re.compile(r"^(?P<owner>\S+)\s+canonical name\s*=\s*(?P<target>\S+)", re.I)
_NSLOOKUP_OWNERLESS_CNAME_RE = re.compile(r"^canonical name\s*=\s*(?P<target>\S+)", re.I)
_NSLOOKUP_PTR_RE = re.compile(r"^(?P<owner>\S+)\s+name\s*=\s*(?P<target>\S+)", re.I)
_NSLOOKUP_NS_RE = re.compile(r"^(?P<owner>\S+)\s+nameserver\s*=\s*(?P<target>\S+)", re.I)
_NSLOOKUP_MX_RE = re.compile(
    r"^(?P<owner>\S+)\s+mail exchanger\s*=\s*\d+\s+(?P<target>\S+)", re.I,
)
_NSLOOKUP_SRV_RE = re.compile(
    r"^(?P<owner>\S+)\s+service\s*=\s*(?P<data>\d+\s+\d+\s+\d+\s+\S+)", re.I,
)
_NSLOOKUP_CAA_RE = re.compile(r"^(?P<owner>\S+)\s+(?:rdata_257|caainfo)\s*=", re.I)
_NSLOOKUP_TXT_RE = re.compile(r"^(?P<owner>\S+)\s+text\s*=", re.I)
_NSLOOKUP_NAME_RE = re.compile(r"^Name:\s*(?P<owner>\S+)", re.I)
_NSLOOKUP_ADDRESS_RE = re.compile(r"^Address(?:es)?:\s*(?P<addresses>.+)$", re.I)
_NSLOOKUP_INTERNET_ADDRESS_RE = re.compile(r"^internet address\s*=\s*(?P<address>\S+)", re.I)
_NSLOOKUP_ARROW_OWNER_RE = re.compile(r"^->\s+(?P<owner>\S+)")


class DnsEntityState:
    """Extract only query-owned DNS observations while following output sections."""

    def __init__(self, command: str, extra_domain_suffixes: Sequence[str] = ()) -> None:
        self.spec = parse_dns_command(command)
        self.extra_domain_suffixes = tuple(extra_domain_suffixes)
        self.section = ""
        self.dig_parenthesis_depth = 0
        self.nslookup_owner = ""
        self.short_owner = self.spec.query
        self.answer_names = {
            canonical for query in self.spec.queries
            if (canonical := _canonical_domain_or_empty(query))
        }

    def entities_for_line(self, text: str, source_line: int | None) -> list[dict[str, object]]:
        stripped = str(text or "").strip()
        if not stripped:
            return []
        if self.spec.root == "dig":
            return self._dig_entities(stripped, source_line)
        if self.spec.root == "nslookup":
            return self._nslookup_entities(stripped, source_line)
        return []

    def _dig_entities(self, stripped: str, source_line: int | None) -> list[dict[str, object]]:
        if self.dig_parenthesis_depth:
            self.dig_parenthesis_depth = max(
                0, self.dig_parenthesis_depth + _parenthesis_delta(stripped),
            )
            return []
        section_match = _DIG_SECTION_RE.match(stripped)
        if section_match:
            self.section = section_match.group(1).lower()
            return []
        if stripped.startswith(";; OPT PSEUDOSECTION:"):
            self.section = "additional"
            return []
        if self.spec.nssearch or stripped.startswith(";") or " bytes from " in stripped:
            return []
        record = _DIG_RECORD_RE.match(stripped)
        if record:
            if self.section not in {"", "answer"}:
                return []
            data = record.group("data") or ""
            self.dig_parenthesis_depth = max(0, _parenthesis_delta(data))
            return self._record_entities(
                record.group("owner"),
                record.group("record_type"),
                data,
                source_line,
                trace=self.spec.trace,
            )
        if self.spec.trace or self.section not in {"", "answer"}:
            return []
        return self._short_dig_entities(stripped, source_line)

    def _short_dig_entities(self, stripped: str, source_line: int | None) -> list[dict[str, object]]:
        record_type = self.spec.record_type
        data = stripped
        if record_type in {"a", "aaaa"} and _canonical_domain_or_empty(stripped):
            entities = self._record_entities(self.short_owner, "cname", stripped, source_line)
            self.short_owner = clean_dns_host(stripped)
            return entities
        if not _short_answer_data(record_type, data):
            return []
        return self._record_entities(self.short_owner, record_type, data, source_line)

    def _record_entities(
        self,
        owner: str,
        record_type: str,
        data: str,
        source_line: int | None,
        *,
        trace: bool = False,
    ) -> list[dict[str, object]]:
        kind = str(record_type or "").lower()
        owner_value = clean_dns_host(owner)
        owner_canonical = _canonical_domain_or_empty(owner_value)
        owner_ip = _canonical_ip_or_empty(owner_value)
        reverse_owner = owner_value.lower().endswith((".in-addr.arpa", ".ip6.arpa"))
        if not owner_canonical and not reverse_owner and not (
            owner_ip and owner_ip == _canonical_ip_or_empty(self.spec.query)
        ):
            return []
        if trace and (kind not in {"a", "aaaa", "cname"} or owner_canonical not in self.answer_names):
            return []
        if owner_canonical and owner_canonical not in self.answer_names and not (kind == "ptr" and reverse_owner):
            return []
        entities: list[dict[str, object]] = []
        seen: set[tuple[str, str]] = set()
        if kind != "ptr":
            self._add_domain(entities, seen, owner_value, source_line)
        first = str(data or "").strip().split()[0] if str(data or "").strip() else ""
        if kind in {"a", "aaaa"}:
            self._add_ip(entities, seen, first, source_line)
        elif kind == "cname":
            target = clean_dns_host(first)
            if self._add_domain(entities, seen, target, source_line):
                self.answer_names.add(_canonical_domain_or_empty(target))
        elif kind == "ptr":
            if self._add_domain(entities, seen, first, source_line):
                self.answer_names.add(_canonical_domain_or_empty(first))
            self._add_ip(entities, seen, self.spec.query, source_line)
        elif kind in {"mx", "ns", "srv"}:
            parts = str(data or "").strip().split()
            candidate = clean_dns_host(first if kind == "ns" else (parts[-1] if parts else ""))
            if self._same_project_domain(candidate) and self._add_domain(
                entities, seen, candidate, source_line,
            ):
                self.answer_names.add(_canonical_domain_or_empty(candidate))
        return entities

    def _nslookup_entities(self, stripped: str, source_line: int | None) -> list[dict[str, object]]:
        lowered = stripped.lower()
        if lowered in {"questions:", "question section:"}:
            self.section = "question"
            return []
        if lowered in {"answers:", "answer section:", "non-authoritative answer:"}:
            self.section = "answer"
            return []
        if lowered.startswith(("authority records:", "additional records:", "authoritative answers can be found")):
            self.section = "authority"
            return []
        if lowered.startswith(("server:", "resolver:")):
            self.nslookup_owner = ""
            return []
        if "can't find" in lowered:
            return []
        arrow_match = _NSLOOKUP_ARROW_OWNER_RE.match(stripped)
        if arrow_match:
            self.nslookup_owner = clean_dns_host(arrow_match.group("owner"))
            return []
        if self.section in {"question", "authority"}:
            return []
        ownerless_cname = _NSLOOKUP_OWNERLESS_CNAME_RE.match(stripped)
        if ownerless_cname and self.nslookup_owner:
            target = ownerless_cname.group("target")
            entities = self._record_entities(self.nslookup_owner, "cname", target, source_line)
            self.nslookup_owner = clean_dns_host(target)
            return entities
        for pattern, kind in (
            (_NSLOOKUP_CNAME_RE, "cname"),
            (_NSLOOKUP_PTR_RE, "ptr"),
            (_NSLOOKUP_NS_RE, "ns"),
            (_NSLOOKUP_MX_RE, "mx"),
        ):
            match = pattern.match(stripped)
            if match:
                target = clean_dns_host(match.group("target"))
                entities = self._record_entities(
                    match.group("owner"), kind, match.group("target"), source_line,
                )
                self.nslookup_owner = target
                return entities
        srv_match = _NSLOOKUP_SRV_RE.match(stripped)
        if srv_match:
            entities = self._record_entities(
                srv_match.group("owner"), "srv", srv_match.group("data"), source_line,
            )
            target = clean_dns_host(srv_match.group("data").split()[-1])
            self.nslookup_owner = target
            return entities
        caa_match = _NSLOOKUP_CAA_RE.match(stripped)
        if caa_match:
            return self._record_entities(caa_match.group("owner"), "caa", "", source_line)
        txt_match = _NSLOOKUP_TXT_RE.match(stripped)
        if txt_match:
            return self._record_entities(txt_match.group("owner"), "txt", "", source_line)
        name_match = _NSLOOKUP_NAME_RE.match(stripped)
        if name_match:
            candidate = clean_dns_host(name_match.group("owner"))
            entities = self._record_entities(candidate, "a", "", source_line)
            self.nslookup_owner = candidate
            return entities
        address_match = _NSLOOKUP_ADDRESS_RE.match(stripped)
        if address_match:
            if "#" in address_match.group("addresses"):
                return []
            return self._nslookup_address_entities(address_match.group("addresses"), source_line)
        internet_match = _NSLOOKUP_INTERNET_ADDRESS_RE.match(stripped)
        if internet_match:
            return self._nslookup_address_entities(internet_match.group("address"), source_line)
        if lowered.startswith(("origin =", "mail addr =")):
            return []
        if self.section == "answer" and _canonical_domain_or_empty(stripped) == _canonical_domain_or_empty(self.spec.query):
            return self._record_entities(stripped, self.spec.record_type, "", source_line)
        return []

    def _nslookup_address_entities(self, value: str, source_line: int | None) -> list[dict[str, object]]:
        entities: list[dict[str, object]] = []
        seen: set[tuple[str, str]] = set()
        owner_canonical = _canonical_domain_or_empty(self.nslookup_owner)
        if self.nslookup_owner and owner_canonical not in self.answer_names:
            return []
        if owner_canonical:
            self._add_domain(entities, seen, self.nslookup_owner, source_line)
        for candidate in str(value or "").split():
            raw_candidate = candidate.strip(",")
            if not self.nslookup_owner and _canonical_ip_or_empty(raw_candidate) == _canonical_ip_or_empty(
                self.spec.resolver
            ):
                continue
            self._add_ip(entities, seen, raw_candidate, source_line)
        return entities

    def _same_project_domain(self, value: str) -> bool:
        query_root = _registrable_domain(self.spec.query, self.extra_domain_suffixes)
        value_root = _registrable_domain(value, self.extra_domain_suffixes)
        return bool(query_root and value_root and query_root == value_root)

    def _add_domain(
        self,
        entities: list[dict[str, object]],
        seen: set[tuple[str, str]],
        value: str,
        source_line: int | None,
    ) -> bool:
        raw = _domain_entity_value(value)
        if not raw or raw.lower().endswith((".in-addr.arpa", ".ip6.arpa")):
            return False
        try:
            canonical = canonical_domain(raw)
        except CanonicalizationError:
            return False
        if not _domain_candidate_has_allowed_suffix(canonical, self.extra_domain_suffixes):
            return False
        _add_entity(
            entities, seen, entity_type="domain", value=raw,
            canonical_value=canonical, source_line=source_line,
        )
        return True

    @staticmethod
    def _add_ip(
        entities: list[dict[str, object]],
        seen: set[tuple[str, str]],
        value: str,
        source_line: int | None,
    ) -> None:
        raw = str(value or "").strip().strip("[]").rstrip(".")
        try:
            canonical = canonical_ip(raw)
        except CanonicalizationError:
            return
        if not _is_public_ip(canonical):
            return
        _add_entity(
            entities, seen, entity_type="ip", value=raw,
            canonical_value=canonical, source_line=source_line,
        )


def _canonical_domain_or_empty(value: str) -> str:
    cleaned = _domain_entity_value(value)
    if _canonical_ip_or_empty(cleaned):
        return ""
    try:
        return canonical_domain(cleaned)
    except CanonicalizationError:
        return ""


def _canonical_ip_or_empty(value: str) -> str:
    try:
        return canonical_ip(str(value or "").strip().strip("[]"))
    except CanonicalizationError:
        return ""


def _short_answer_data(record_type: str, value: str) -> bool:
    kind = str(record_type or "").lower()
    raw = str(value or "").strip()
    if not raw:
        return False
    if kind in {"a", "aaaa"}:
        try:
            canonical_ip(raw.split()[0])
        except CanonicalizationError:
            return False
        return True
    if kind in {"cname", "ns", "ptr"}:
        return bool(_canonical_domain_or_empty(raw.split()[0]))
    if kind in {"mx", "srv"}:
        return bool(_canonical_domain_or_empty(raw.split()[-1]))
    return True


def _domain_entity_value(value: str) -> str:
    raw = clean_dns_host(value)
    if raw.startswith("*."):
        raw = raw[2:]
    return "" if "*" in raw else raw


def _parenthesis_delta(value: str) -> int:
    depth = 0
    quote = ""
    escaped = False
    for char in str(value or ""):
        if escaped:
            escaped = False
        elif char == "\\" and quote:
            escaped = True
        elif char == quote:
            quote = ""
        elif char in {"'", '"'}:
            quote = char
        elif char == ";" and not quote:
            break
        elif not quote:
            depth += (char == "(") - (char == ")")
    return depth


def _registrable_domain(value: str, extra_suffixes: Sequence[str] = ()) -> str:
    labels = _entity_domain_labels(value)
    if not labels:
        return ""
    extracted = _DOMAIN_SUFFIX_EXTRACTOR(".".join(labels))
    if extracted.domain and extracted.suffix:
        return f"{extracted.domain}.{extracted.suffix}".lower()
    ordered_suffixes = sorted(extra_suffixes, key=lambda item: len(_entity_domain_labels(item)), reverse=True)
    for raw_suffix in ordered_suffixes:
        suffix_labels = _entity_domain_labels(raw_suffix)
        if suffix_labels and len(labels) > len(suffix_labels) and labels[-len(suffix_labels):] == suffix_labels:
            return ".".join(labels[-(len(suffix_labels) + 1):])
    return ""


__all__ = ["DnsEntityState"]
