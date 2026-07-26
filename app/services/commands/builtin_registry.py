# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Deterministic registry contracts for app-owned helper commands."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, TypeAlias, cast

import config as app_config
from services.commands.features import feature_enabled
from services.commands.registry_validation import split_command_argv
from services.teams import scope as team_scope
from services.teams.scope import OwnerContext


BuiltinEvent: TypeAlias = dict[str, object]
BuiltinEvents: TypeAlias = list[BuiltinEvent]
BuiltinResult: TypeAlias = BuiltinEvents | tuple[BuiltinEvents, int]
BuiltinHandler: TypeAlias = Callable[[str, "BuiltinExecutionContext"], BuiltinResult]

_UNSET = object()


class BuiltinExecutionOwner(str, Enum):
    """The runtime that owns a helper command's user-facing execution."""

    SERVER = "server"
    BROWSER = "browser"
    MIXED = "mixed"


class BuiltinMatchStrategy(str, Enum):
    """Reviewed pre-dispatch matchers supported by the helper registry."""

    ROOT = "root"
    WORKSPACE_ALIAS = "workspace_alias"
    FORK_BOMB = "fork_bomb"


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return MappingProxyType({
            str(key): _freeze_value(item)
            for key, item in value.items()
        })
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze_value(item) for item in value)
    return value


def _thaw_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _thaw_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, frozenset)):
        return [_thaw_value(item) for item in value]
    return value


@dataclass(slots=True)
class BuiltinExecutionContext:
    """Cheap request context with lazy, per-execution derived values."""

    session_id: str
    tab_id: str = ""
    team_id: str = ""
    team_role: str = ""
    supplied_owner_context: OwnerContext | None = None
    config_resolver: Callable[[], Mapping[str, Any]] | None = field(
        default=None,
        repr=False,
    )
    owner_context_resolver: Callable[..., OwnerContext] | None = field(
        default=None,
        repr=False,
    )
    _effective_cfg: object = field(default=_UNSET, init=False, repr=False)
    _owner_context: object = field(default=_UNSET, init=False, repr=False)

    @property
    def effective_cfg(self) -> Mapping[str, Any]:
        if self._effective_cfg is _UNSET:
            resolver = self.config_resolver or app_config.resolve_effective_cfg
            self._effective_cfg = resolver()
        return cast(Mapping[str, Any], self._effective_cfg)

    @property
    def owner_context(self) -> OwnerContext:
        if self._owner_context is _UNSET:
            if self.supplied_owner_context is not None:
                self._owner_context = self.supplied_owner_context
            else:
                resolver = self.owner_context_resolver or team_scope.owner_context_for_scope
                self._owner_context = resolver(
                    self.session_id,
                    team_id=self.team_id,
                )
        return cast(OwnerContext, self._owner_context)


@dataclass(frozen=True, slots=True)
class BuiltinCommandSpec:
    """Immutable metadata and handler contract for one app-owned helper."""

    handler_key: str
    handler: BuiltinHandler
    name: str = ""
    description: str = ""
    category: str = "Built-in commands"
    root: str = ""
    autocomplete_root: str = ""
    autocomplete_description: str = ""
    exact_aliases: tuple[str, ...] = ()
    feature_required: tuple[str, ...] = ()
    execution_owner: BuiltinExecutionOwner = BuiltinExecutionOwner.SERVER
    browser_owned_subcommands: tuple[str, ...] = ()
    browser_fallback_stub: bool = False
    match_strategy: BuiltinMatchStrategy = BuiltinMatchStrategy.ROOT
    autocomplete: Mapping[str, object] = field(default_factory=dict)
    examples: tuple[Mapping[str, object], ...] = ()
    knowledge: Mapping[str, object] = field(default_factory=dict)
    user_facing: bool = True

    def __post_init__(self) -> None:
        handler_key = str(self.handler_key or "").strip()
        root = str(self.root or "").strip().lower()
        autocomplete_root = str(self.autocomplete_root or root).strip().lower()
        autocomplete_description = str(self.autocomplete_description or "").strip()
        if not handler_key:
            raise ValueError("Built-in command handler_key cannot be empty")
        if self.match_strategy is BuiltinMatchStrategy.ROOT and not root and not self.exact_aliases:
            raise ValueError(
                f"Built-in command {handler_key!r} must declare a root or exact alias"
            )
        if self.match_strategy is BuiltinMatchStrategy.WORKSPACE_ALIAS and not root:
            raise ValueError(
                f"Workspace-alias command {handler_key!r} must declare a root"
            )
        if self.match_strategy is BuiltinMatchStrategy.FORK_BOMB and root:
            raise ValueError(
                f"Fork-bomb command {handler_key!r} cannot declare a root"
            )
        exact_aliases = tuple(
            dict.fromkeys(
                " ".join(str(alias or "").strip().lower().split())
                for alias in self.exact_aliases
                if str(alias or "").strip()
            )
        )
        required_features = tuple(
            dict.fromkeys(
                str(feature or "").strip().lower()
                for feature in self.feature_required
                if str(feature or "").strip()
            )
        )
        browser_owned_subcommands = tuple(
            dict.fromkeys(
                str(subcommand or "").strip().lower()
                for subcommand in self.browser_owned_subcommands
                if str(subcommand or "").strip()
            )
        )
        if self.execution_owner is BuiltinExecutionOwner.BROWSER and not self.browser_fallback_stub:
            raise ValueError(
                f"Browser-owned command {handler_key!r} must declare an explicit fallback stub"
            )
        object.__setattr__(self, "handler_key", handler_key)
        object.__setattr__(self, "root", root)
        object.__setattr__(self, "autocomplete_root", autocomplete_root)
        object.__setattr__(self, "autocomplete_description", autocomplete_description)
        object.__setattr__(self, "exact_aliases", exact_aliases)
        object.__setattr__(self, "feature_required", required_features)
        object.__setattr__(self, "browser_owned_subcommands", browser_owned_subcommands)
        object.__setattr__(self, "autocomplete", _freeze_value(self.autocomplete))
        object.__setattr__(
            self,
            "examples",
            tuple(cast(Mapping[str, object], _freeze_value(example)) for example in self.examples),
        )
        object.__setattr__(self, "knowledge", _freeze_value(self.knowledge))

    def catalog_entry(self) -> dict[str, object]:
        from services.commands.registry_catalog import autocomplete_catalog_details

        entry: dict[str, object] = {
            "root": self.root or self.autocomplete_root or self.handler_key,
            "name": self.name or self.root or self.autocomplete_root or self.handler_key,
            "description": self.description,
            "category": self.category,
            "execution_owner": self.execution_owner.value,
        }
        if self.feature_required:
            entry["feature_required"] = list(self.feature_required)
        if self.browser_owned_subcommands:
            entry["browser_owned_subcommands"] = list(self.browser_owned_subcommands)
        if self.examples:
            entry["examples"] = _thaw_value(self.examples)
        if self.knowledge:
            entry["knowledge"] = _thaw_value(self.knowledge)
        if self.autocomplete:
            autocomplete = _thaw_value(self.autocomplete)
            entry["autocomplete"] = autocomplete
            entry.update(autocomplete_catalog_details(autocomplete))
        else:
            raw_examples = entry.get("examples")
            entry.update({
                "arguments": [],
                "examples": (
                    list(raw_examples)
                    if isinstance(raw_examples, (list, tuple))
                    else []
                ),
                "flags": [],
                "subcommands": [],
            })
        return entry


@dataclass(frozen=True, slots=True)
class BuiltinResolution:
    """One validated registry match ready for execution."""

    spec: BuiltinCommandSpec
    command: str
    argv: tuple[str, ...]

    @property
    def handler_key(self) -> str:
        return self.spec.handler_key


WorkspaceAliasValidator: TypeAlias = Callable[[Sequence[str]], bool]
ForkBombMatcher: TypeAlias = Callable[[str], bool]


class BuiltinCommandRegistry:
    """Explicit, duplicate-safe, freeze-once registry for built-in helpers."""

    def __init__(
        self,
        *,
        workspace_alias_validator: WorkspaceAliasValidator | None = None,
        fork_bomb_matcher: ForkBombMatcher | None = None,
    ) -> None:
        self._specs_by_key: dict[str, BuiltinCommandSpec] = {}
        self._specs_by_root: dict[str, BuiltinCommandSpec] = {}
        self._specs_by_autocomplete_root: dict[str, BuiltinCommandSpec] = {}
        self._specs_by_exact_alias: dict[str, BuiltinCommandSpec] = {}
        self._fork_bomb_spec: BuiltinCommandSpec | None = None
        self._workspace_alias_validator = workspace_alias_validator
        self._fork_bomb_matcher = fork_bomb_matcher
        self._frozen = False

    @property
    def frozen(self) -> bool:
        return self._frozen

    def register(self, spec: BuiltinCommandSpec) -> None:
        if self._frozen:
            raise RuntimeError("Built-in command registry is frozen")
        if spec.handler_key in self._specs_by_key:
            raise ValueError(
                f"Duplicate built-in handler key: {spec.handler_key}"
            )
        if spec.root and spec.root in self._specs_by_root:
            other = self._specs_by_root[spec.root]
            raise ValueError(
                f"Duplicate built-in root {spec.root!r}: "
                f"{other.handler_key!r} and {spec.handler_key!r}"
            )
        if (
            spec.autocomplete_root
            and spec.autocomplete_root in self._specs_by_autocomplete_root
        ):
            other = self._specs_by_autocomplete_root[spec.autocomplete_root]
            raise ValueError(
                f"Duplicate built-in autocomplete root {spec.autocomplete_root!r}: "
                f"{other.handler_key!r} and {spec.handler_key!r}"
            )
        for alias in spec.exact_aliases:
            if alias in self._specs_by_exact_alias:
                other = self._specs_by_exact_alias[alias]
                raise ValueError(
                    f"Duplicate built-in exact alias {alias!r}: "
                    f"{other.handler_key!r} and {spec.handler_key!r}"
                )
        if spec.match_strategy is BuiltinMatchStrategy.FORK_BOMB:
            if self._fork_bomb_spec is not None:
                raise ValueError(
                    "Duplicate built-in fork-bomb matcher: "
                    f"{self._fork_bomb_spec.handler_key!r} and {spec.handler_key!r}"
                )
            if self._fork_bomb_matcher is None:
                raise ValueError("Fork-bomb matcher strategy has no configured matcher")
        if (
            spec.match_strategy is BuiltinMatchStrategy.WORKSPACE_ALIAS
            and self._workspace_alias_validator is None
        ):
            raise ValueError("Workspace-alias strategy has no configured validator")

        self._specs_by_key[spec.handler_key] = spec
        if spec.root:
            self._specs_by_root[spec.root] = spec
        if spec.autocomplete_root:
            self._specs_by_autocomplete_root[spec.autocomplete_root] = spec
        for alias in spec.exact_aliases:
            self._specs_by_exact_alias[alias] = spec
        if spec.match_strategy is BuiltinMatchStrategy.FORK_BOMB:
            self._fork_bomb_spec = spec

    def freeze(self) -> "BuiltinCommandRegistry":
        self._frozen = True
        return self

    def spec_for_key(self, handler_key: str) -> BuiltinCommandSpec | None:
        return self._specs_by_key.get(str(handler_key or "").strip())

    def specs(self) -> tuple[BuiltinCommandSpec, ...]:
        return tuple(self._specs_by_key.values())

    def _enabled(
        self,
        spec: BuiltinCommandSpec,
        *,
        context: BuiltinExecutionContext | None = None,
        cfg: Mapping[str, Any] | None = None,
    ) -> bool:
        if not spec.feature_required:
            return True
        active_cfg = context.effective_cfg if context is not None else cfg
        return all(feature_enabled(feature, active_cfg) for feature in spec.feature_required)

    def resolve(
        self,
        command: str,
        *,
        context: BuiltinExecutionContext | None = None,
        cfg: Mapping[str, Any] | None = None,
    ) -> BuiltinResolution | None:
        stripped = str(command or "").strip()
        if not stripped:
            return None

        exact_resolution = self.resolve_exact(command, context=context, cfg=cfg)
        if exact_resolution is not None:
            return exact_resolution

        argv = tuple(split_command_argv(command))
        if not argv:
            return None
        root = argv[0].strip().lower()
        spec = self._specs_by_root.get(root)
        if spec is None or not self._enabled(spec, context=context, cfg=cfg):
            return None
        if spec.match_strategy is BuiltinMatchStrategy.WORKSPACE_ALIAS:
            validator = self._workspace_alias_validator
            if validator is None or not validator(argv):
                return None
        return BuiltinResolution(spec, command, argv)

    def resolve_exact(
        self,
        command: str,
        *,
        context: BuiltinExecutionContext | None = None,
        cfg: Mapping[str, Any] | None = None,
    ) -> BuiltinResolution | None:
        stripped = str(command or "").strip()
        if not stripped:
            return None
        normalized = " ".join(stripped.lower().split())
        exact_spec = self._specs_by_exact_alias.get(normalized)
        if exact_spec is not None and self._enabled(exact_spec, context=context, cfg=cfg):
            return BuiltinResolution(exact_spec, command, tuple(split_command_argv(command)))

        if (
            self._fork_bomb_spec is not None
            and self._fork_bomb_matcher is not None
            and self._fork_bomb_matcher(stripped)
            and self._enabled(self._fork_bomb_spec, context=context, cfg=cfg)
        ):
            return BuiltinResolution(
                self._fork_bomb_spec,
                command,
                tuple(split_command_argv(command)),
            )
        return None

    def roots(
        self,
        *,
        cfg: Mapping[str, Any] | None = None,
        include_exact_alias_roots: bool = False,
    ) -> tuple[str, ...]:
        roots = {
            root
            for root, spec in self._specs_by_root.items()
            if self._enabled(spec, cfg=cfg)
        }
        if include_exact_alias_roots:
            roots.update(
                alias_root
                for alias, spec in self._specs_by_exact_alias.items()
                if alias
                for alias_root in (alias.split()[0],)
                if self._enabled(
                    self._specs_by_root.get(alias_root, spec),
                    cfg=cfg,
                )
            )
        return tuple(sorted(roots))

    def registered_roots(
        self,
        *,
        include_exact_alias_roots: bool = False,
    ) -> tuple[str, ...]:
        """Return all configured roots without applying runtime feature gates."""
        roots = set(self._specs_by_root)
        if include_exact_alias_roots:
            roots.update(
                alias.split()[0]
                for alias in self._specs_by_exact_alias
                if alias
            )
        return tuple(sorted(roots))

    def exact_aliases(self, *, cfg: Mapping[str, Any] | None = None) -> tuple[str, ...]:
        return tuple(sorted(
            alias
            for alias, spec in self._specs_by_exact_alias.items()
            if self._enabled(spec, cfg=cfg)
        ))

    def catalog(self, *, cfg: Mapping[str, Any] | None = None) -> list[dict[str, object]]:
        entries = [
            spec.catalog_entry()
            for spec in self._specs_by_key.values()
            if spec.user_facing and self._enabled(spec, cfg=cfg)
        ]
        return sorted(entries, key=lambda entry: str(entry.get("root") or ""))

    def catalog_entry(
        self,
        root: str,
        subcommand: str | None = None,
        *,
        cfg: Mapping[str, Any] | None = None,
    ) -> dict[str, object] | None:
        wanted_root = str(root or "").strip().lower()
        wanted_subcommand = str(subcommand or "").strip().lower()
        if not wanted_root:
            return None
        for entry in self.catalog(cfg=cfg):
            if str(entry.get("root") or "").strip().lower() != wanted_root:
                continue
            if not wanted_subcommand:
                return entry
            raw_subcommands = entry.get("subcommands")
            subcommands = raw_subcommands if isinstance(raw_subcommands, list) else []
            for sub in subcommands:
                if not isinstance(sub, dict):
                    continue
                if str(sub.get("name") or "").strip().lower() != wanted_subcommand:
                    continue
                scoped = dict(entry)
                scoped["subcommand"] = wanted_subcommand
                scoped["description"] = str(
                    sub.get("description") or scoped.get("description") or ""
                )
                scoped["examples"] = sub.get("examples") or entry.get("examples") or []
                scoped["flags"] = sub.get("flags") or []
                scoped["arguments"] = sub.get("arguments") or []
                scoped["subcommands"] = []
                return scoped
            return None
        return None

    def autocomplete_context(
        self,
        *,
        cfg: Mapping[str, Any] | None = None,
    ) -> dict[str, dict[str, object]]:
        context: dict[str, dict[str, object]] = {}
        for spec in self._specs_by_key.values():
            if (
                not spec.autocomplete_root
                or not spec.autocomplete
                or not self._enabled(spec, cfg=cfg)
            ):
                continue
            autocomplete = cast(dict[str, object], _thaw_value(spec.autocomplete))
            description = spec.autocomplete_description or spec.description
            if description:
                autocomplete["description"] = description
            if spec.feature_required:
                autocomplete["feature_required"] = (
                    spec.feature_required[0]
                    if len(spec.feature_required) == 1
                    else list(spec.feature_required)
                )
            context[spec.autocomplete_root] = autocomplete
        return context

    def execute(
        self,
        command: str,
        context: BuiltinExecutionContext,
    ) -> tuple[BuiltinEvents, int]:
        resolution = self.resolve(command, context=context)
        if resolution is None:
            return [{
                "type": "output",
                "text": f"Unsupported built-in command: {str(command or '').strip()}",
            }], 1
        result = resolution.spec.handler(command, context)
        if isinstance(result, tuple):
            events, exit_code = result
            return list(events), int(exit_code)
        return list(result), 0
