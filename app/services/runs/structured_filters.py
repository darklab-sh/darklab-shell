"""Structured run-output selectors.

The history/API surfaces accept a small selector language over typed
``LineEvent`` fields. Text search remains separate from these selectors so FTS
can keep doing what it does well while structured filters inspect loaded output
events only when requested.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from services.runs.output_model import LINE_KIND_VALUES, LINE_ROLE_VALUES, LINE_SIGNAL_VALUES, LineEvent


_FILTER_PREFIXES = {
    "signal",
    "signals",
    "kind",
    "not_kind",
    "exclude_kind",
    "role",
    "entity",
    "entity_type",
    "type",
}


@dataclass(frozen=True)
class StructuredOutputFilters:
    signals: tuple[str, ...] = ()
    kinds: tuple[str, ...] = ()
    exclude_kinds: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()
    entities: tuple[str, ...] = ()
    entity_types: tuple[str, ...] = ()

    @property
    def active(self) -> bool:
        return bool(
            self.signals
            or self.kinds
            or self.exclude_kinds
            or self.roles
            or self.entities
            or self.entity_types
        )


def parse_structured_query(value: str) -> tuple[str, StructuredOutputFilters]:
    """Split text query and selector tokens.

    Supported selector tokens are ``signal:<name>``, ``signals:<name>``,
    ``kind:<name>``, ``role:<name>``, and ``entity:<value>``. Invalid tokens are
    left in the text query so they behave like normal search terms instead of
    unexpectedly broadening a search.
    """
    signal_values: list[str] = []
    kind_values: list[str] = []
    exclude_kind_values: list[str] = []
    role_values: list[str] = []
    entity_values: list[str] = []
    entity_type_values: list[str] = []
    text_terms: list[str] = []
    for term in str(value or "").split():
        if "!=" in term:
            prefix, separator, raw = term.partition("!=")
            negate = True
        elif "!:" in term:
            prefix, separator, raw = term.partition("!:")
            negate = True
        else:
            prefix, separator, raw = term.partition(":")
            negate = False
        family = prefix.casefold()
        selector = raw.strip()
        if separator not in {":", "!:", "!="} or family not in _FILTER_PREFIXES or not selector:
            text_terms.append(term)
            continue
        selector = selector.casefold()
        if family in {"signal", "signals"} and selector in LINE_SIGNAL_VALUES:
            signal_values.append(selector)
        elif family == "kind" and negate and selector in LINE_KIND_VALUES:
            exclude_kind_values.append(selector)
        elif family in {"not_kind", "exclude_kind"} and selector in LINE_KIND_VALUES:
            exclude_kind_values.append(selector)
        elif family == "kind" and selector in LINE_KIND_VALUES:
            kind_values.append(selector)
        elif family == "role" and selector in LINE_ROLE_VALUES:
            role_values.append(selector)
        elif family == "entity":
            entity_values.append(selector)
        elif family in {"entity_type", "type"}:
            entity_type_values.append(selector)
        else:
            text_terms.append(term)
    return " ".join(text_terms), StructuredOutputFilters(
        signals=_unique(signal_values),
        kinds=_unique(kind_values),
        exclude_kinds=_unique(exclude_kind_values),
        roles=_unique(role_values),
        entities=_unique(entity_values),
        entity_types=_unique(entity_type_values),
    )


def structured_filters_from_params(params: Mapping[str, object], *, query: str = "") -> tuple[str, StructuredOutputFilters]:
    text_query, query_filters = parse_structured_query(query)
    return text_query, merge_structured_filters(
        query_filters,
        StructuredOutputFilters(
            signals=_values_from_params(params, "signal", "signals"),
            kinds=_values_from_params(params, "kind"),
            exclude_kinds=_values_from_params(params, "not_kind", "exclude_kind"),
            roles=_values_from_params(params, "role"),
            entities=_values_from_params(params, "entity"),
            entity_types=_values_from_params(params, "entity_type"),
        ),
    )


def merge_structured_filters(*filters: StructuredOutputFilters) -> StructuredOutputFilters:
    signals: list[str] = []
    kinds: list[str] = []
    exclude_kinds: list[str] = []
    roles: list[str] = []
    entities: list[str] = []
    entity_types: list[str] = []
    for item in filters:
        signals.extend(item.signals)
        kinds.extend(item.kinds)
        exclude_kinds.extend(item.exclude_kinds)
        roles.extend(item.roles)
        entities.extend(item.entities)
        entity_types.extend(item.entity_types)
    return StructuredOutputFilters(
        signals=_unique(signals),
        kinds=_unique(kinds),
        exclude_kinds=_unique(exclude_kinds),
        roles=_unique(roles),
        entities=_unique(entities),
        entity_types=_unique(entity_types),
    )


def event_matches_structured_filters(event: LineEvent, filters: StructuredOutputFilters) -> bool:
    if filters.signals:
        event_signals = {signal.value for signal in event.signals}
        if not event_signals.intersection(filters.signals):
            return False
    if filters.kinds and event.kind.value not in filters.kinds:
        return False
    if filters.exclude_kinds and event.kind.value in filters.exclude_kinds:
        return False
    if filters.roles and event.role.value not in filters.roles:
        return False
    if filters.entities and not _event_matches_entity_filter(event, filters.entities):
        return False
    if filters.entity_types and not _event_matches_entity_type_filter(event, filters.entity_types):
        return False
    return True


def run_matches_structured_filters(events: Iterable[LineEvent], filters: StructuredOutputFilters) -> bool:
    if not filters.active:
        return True
    return any(event_matches_structured_filters(event, filters) for event in events)


def filter_events(events: Sequence[LineEvent], filters: StructuredOutputFilters) -> list[LineEvent]:
    if not filters.active:
        return list(events)
    return [event for event in events if event_matches_structured_filters(event, filters)]


def filters_need_line_event_scan(filters: StructuredOutputFilters) -> bool:
    """Return true when run-level summaries can only provide a prefilter."""
    line_families = sum((
        bool(filters.signals),
        bool(filters.kinds or filters.exclude_kinds),
        bool(filters.roles),
    ))
    return line_families > 1 or (line_families > 0 and bool(filters.entities or filters.entity_types))


def filters_have_summary_selectors(filters: StructuredOutputFilters) -> bool:
    return bool(filters.signals or filters.kinds or filters.exclude_kinds or filters.roles)


def run_output_summary_exists_clause(filters: StructuredOutputFilters, *, run_alias: str = "r") -> tuple[str, tuple[str, ...]]:
    clauses: list[str] = []
    params: list[str] = []
    if filters.signals:
        clauses.append(_summary_family_exists_clause("signal", filters.signals, run_alias=run_alias))
        params.extend(filters.signals)
    if filters.kinds:
        clauses.append(_summary_family_exists_clause("kind", filters.kinds, run_alias=run_alias))
        params.extend(filters.kinds)
    if filters.exclude_kinds:
        placeholders = ", ".join("?" for _ in filters.exclude_kinds)
        clauses.append(
            " AND EXISTS ("  # nosec
            "SELECT 1 FROM run_output_summary sfk "
            f"WHERE sfk.run_id = {run_alias}.id AND sfk.family = 'kind' "
            f"AND sfk.value NOT IN ({placeholders}))"
        )
        params.extend(filters.exclude_kinds)
    if filters.roles:
        clauses.append(_summary_family_exists_clause("role", filters.roles, run_alias=run_alias))
        params.extend(filters.roles)
    return "".join(clauses), tuple(params)


def entity_run_exists_clause(filters: StructuredOutputFilters, *, run_alias: str = "r") -> tuple[str, tuple[str, ...]]:
    """Build a SQL EXISTS clause for entity-backed structured selectors.

    The returned fragment is intentionally limited to entity and entity-type
    selectors because those are mirrored in the Atlas entity tables. Signal,
    kind, and role selectors still need to inspect line events.
    """
    if not filters.entities and not filters.entity_types:
        return "", ()

    params: list[str] = []
    predicates = [
        f"sfe_erl.run_id = {run_alias}.id",
        f"sfe_e.session_id = {run_alias}.session_id",
    ]
    if filters.entity_types:
        predicates.append("LOWER(sfe_e.type) IN (" + ", ".join("?" for _ in filters.entity_types) + ")")
        params.extend(filters.entity_types)

    entity_predicates: list[str] = []
    plain_entities: list[str] = []
    typed_entities: list[tuple[str, str]] = []
    for selector in filters.entities:
        entity_type, separator, value = selector.partition(":")
        if separator and entity_type and value:
            typed_entities.append((entity_type, value))
        else:
            plain_entities.append(selector)
    if plain_entities:
        entity_predicates.append("LOWER(sfe_e.canonical_value) IN (" + ", ".join("?" for _ in plain_entities) + ")")
        params.extend(plain_entities)
    for entity_type, value in typed_entities:
        entity_predicates.append("(LOWER(sfe_e.type) = ? AND LOWER(sfe_e.canonical_value) = ?)")
        params.extend([entity_type, value])
    if entity_predicates:
        predicates.append("(" + " OR ".join(entity_predicates) + ")")

    sql = (
        " AND EXISTS ("  # nosec
        "SELECT 1 FROM entity_run_links sfe_erl "
        "JOIN entities sfe_e ON sfe_e.id = sfe_erl.entity_id "
        "WHERE " + " AND ".join(predicates) + ")"
    )
    return sql, tuple(params)


def _summary_family_exists_clause(family: str, values: tuple[str, ...], *, run_alias: str) -> str:
    placeholders = ", ".join("?" for _ in values)
    return (
        " AND EXISTS ("  # nosec
        "SELECT 1 FROM run_output_summary sfs "
        f"WHERE sfs.run_id = {run_alias}.id AND sfs.family = '{family}' "
        f"AND sfs.value IN ({placeholders}))"
    )


def _event_matches_entity_filter(event: LineEvent, selectors: tuple[str, ...]) -> bool:
    for entity in event.entities:
        haystack = {
            entity.canonical_value.casefold(),
            entity.value.casefold(),
            f"{entity.type.casefold()}:{entity.canonical_value.casefold()}",
            f"{entity.type.casefold()}:{entity.value.casefold()}",
        }
        if haystack.intersection(selectors):
            return True
    return False


def _event_matches_entity_type_filter(event: LineEvent, selectors: tuple[str, ...]) -> bool:
    return any(entity.type.casefold() in selectors for entity in event.entities)


def _values_from_params(params: Mapping[str, object], *names: str) -> tuple[str, ...]:
    values: list[str] = []
    for name in names:
        raw_values: object
        if hasattr(params, "getlist"):
            raw_values = params.getlist(name)  # type: ignore[attr-defined]
        else:
            raw_values = params.get(name, "")
        if isinstance(raw_values, str):
            values.extend(_split_values(raw_values))
        elif isinstance(raw_values, Iterable):
            for raw in raw_values:
                values.extend(_split_values(str(raw or "")))
    return _unique(value.casefold() for value in values if value)


def _split_values(value: str) -> list[str]:
    return [item.strip() for item in value.replace(",", " ").split() if item.strip()]


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value or "").strip().casefold()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return tuple(result)
