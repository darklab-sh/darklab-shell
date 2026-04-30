from __future__ import annotations

from pathlib import Path
from typing import Iterable

import yaml

APP_DIR = Path(__file__).resolve().parent
WORDLIST_CATALOG_FILE = APP_DIR / "conf" / "wordlists.yaml"
DEFAULT_WORDLIST_ROOT = Path("/usr/share/wordlists/seclists")

_IGNORED_NAMES = {
    "readme",
    "readme.md",
    "license",
    "license.md",
    "copyright",
}
_IGNORED_SUFFIXES = {
    ".7z",
    ".bak",
    ".gz",
    ".html",
    ".md",
    ".png",
    ".py",
    ".rb",
    ".swf",
    ".zip",
}


def _load_yaml_mapping(path: str | Path = WORDLIST_CATALOG_FILE) -> dict:
    try:
        loaded = yaml.safe_load(Path(path).read_text()) or {}
    except (FileNotFoundError, OSError, yaml.YAMLError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _normalize_category(value: object) -> str:
    return str(value or "").strip().lower()


def _configured_root(config: dict, root: str | Path | None = None) -> Path:
    if root is not None:
        return Path(root)
    raw_root = str(config.get("root") or "").strip()
    return Path(raw_root) if raw_root else DEFAULT_WORDLIST_ROOT


def _is_probable_wordlist(path: Path) -> bool:
    name = path.name.lower()
    if name in _IGNORED_NAMES:
        return False
    if path.suffix.lower() in _IGNORED_SUFFIXES:
        return False
    return path.is_file()


def _safe_config_pattern(pattern: object) -> str:
    text = str(pattern or "").strip().lstrip("/")
    if not text or "\x00" in text:
        return ""
    parts = Path(text).parts
    if any(part in {"", ".", ".."} for part in parts):
        return ""
    return text


def _iter_matches(root: Path, pattern: str) -> Iterable[Path]:
    if any(char in pattern for char in "*?["):
        yield from sorted(root.glob(pattern), key=lambda path: path.as_posix().lower())
        return
    yield root / pattern


def _entry_aliases(relpath: str, name: str) -> list[str]:
    basename = Path(relpath).name
    stem = Path(relpath).stem
    aliases = {basename, stem, name}
    return sorted(alias for alias in aliases if alias)


def _entry_name(relpath: str, seen: set[str]) -> str:
    path = Path(relpath)
    base = path.name
    candidate = base
    if candidate.lower() in seen:
        parent = path.parent.name
        candidate = f"{parent}/{base}" if parent else base
    seen.add(candidate.lower())
    return candidate


def _build_entry(path: Path, root: Path, category: dict, seen_names: set[str]) -> dict:
    relpath = path.relative_to(root).as_posix()
    name = _entry_name(relpath, seen_names)
    category_key = _normalize_category(category.get("key"))
    category_label = str(category.get("label") or category_key).strip()
    return {
        "name": name,
        "category": category_key,
        "category_label": category_label,
        "description": str(category.get("description") or "").strip(),
        "path": path.as_posix(),
        "relpath": relpath,
        "aliases": _entry_aliases(relpath, name),
    }


def load_wordlist_categories(config_path: str | Path = WORDLIST_CATALOG_FILE) -> list[dict]:
    config = _load_yaml_mapping(config_path)
    categories = []
    for raw in config.get("categories") or []:
        if not isinstance(raw, dict):
            continue
        key = _normalize_category(raw.get("key"))
        if not key:
            continue
        include = [
            pattern for pattern in (_safe_config_pattern(item) for item in raw.get("include") or [])
            if pattern
        ]
        categories.append({
            "key": key,
            "label": str(raw.get("label") or key).strip(),
            "description": str(raw.get("description") or "").strip(),
            "include": include,
        })
    return categories


def load_wordlist_catalog(
    *,
    config_path: str | Path = WORDLIST_CATALOG_FILE,
    root: str | Path | None = None,
    include_all: bool = False,
) -> dict:
    config = _load_yaml_mapping(config_path)
    wordlist_root = _configured_root(config, root)
    categories = load_wordlist_categories(config_path)
    if not wordlist_root.is_dir():
        return {
            "root": wordlist_root.as_posix(),
            "categories": categories,
            "items": [],
            "all_items": [] if include_all else None,
        }

    seen_paths: set[str] = set()
    seen_names: set[str] = set()
    items: list[dict] = []
    for category in categories:
        for pattern in category.get("include") or []:
            for path in _iter_matches(wordlist_root, pattern):
                try:
                    resolved = path.resolve()
                    resolved.relative_to(wordlist_root.resolve())
                except (OSError, ValueError):
                    continue
                if not _is_probable_wordlist(path):
                    continue
                relpath = path.relative_to(wordlist_root).as_posix()
                key = f"{category['key']}:{relpath.lower()}"
                if key in seen_paths:
                    continue
                seen_paths.add(key)
                items.append(_build_entry(path, wordlist_root, category, seen_names))

    items.sort(key=lambda item: (item["category"], item["relpath"].lower()))
    all_items = _scan_all_wordlists(wordlist_root) if include_all else None
    return {
        "root": wordlist_root.as_posix(),
        "categories": categories,
        "items": items,
        "all_items": all_items,
    }


def _scan_all_wordlists(root: Path) -> list[dict]:
    entries = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix().lower()):
        if not _is_probable_wordlist(path):
            continue
        relpath = path.relative_to(root).as_posix()
        entries.append({
            "name": path.name,
            "category": "all",
            "category_label": "All",
            "description": "",
            "path": path.as_posix(),
            "relpath": relpath,
            "aliases": _entry_aliases(relpath, path.name),
        })
    return entries


def filter_wordlists(
    items: Iterable[dict],
    *,
    category: str | Iterable[str] | None = None,
    search: str | None = None,
) -> list[dict]:
    if isinstance(category, str):
        categories = {_normalize_category(category)}
    elif category is None:
        categories = set()
    else:
        categories = {_normalize_category(value) for value in category if _normalize_category(value)}
    needle = str(search or "").strip().lower()
    filtered = []
    for item in items:
        if categories and _normalize_category(item.get("category")) not in categories:
            continue
        haystack = " ".join([
            str(item.get("name") or ""),
            str(item.get("category") or ""),
            str(item.get("category_label") or ""),
            str(item.get("description") or ""),
            str(item.get("path") or ""),
            str(item.get("relpath") or ""),
            " ".join(str(alias) for alias in item.get("aliases") or []),
        ]).lower()
        if needle and needle not in haystack:
            continue
        filtered.append(item)
    return sorted(filtered, key=lambda item: (str(item.get("category") or ""), str(item.get("relpath") or "").lower()))


def find_wordlist(identifier: str, items: Iterable[dict]) -> dict | None:
    target = str(identifier or "").strip().lower()
    if not target:
        return None
    for item in items:
        candidates = {
            str(item.get("name") or "").lower(),
            str(item.get("relpath") or "").lower(),
            str(item.get("path") or "").lower(),
            f"{item.get('category')}/{item.get('name')}".lower(),
        }
        candidates.update(str(alias).lower() for alias in item.get("aliases") or [])
        if target in candidates:
            return item
    return None


def wordlist_autocomplete_items(*, root: str | Path | None = None) -> list[dict]:
    catalog = load_wordlist_catalog(root=root)
    items = []
    for item in catalog["items"]:
        items.append({
            "value": item["path"],
            "label": item["relpath"],
            "description": f"{item['category_label']} wordlist",
            "category": item["category"],
            "wordlist_category": item["category"],
            "name": item["name"],
        })
    return items
