"""
Split run-output persistence helpers.

Preview output stays in SQLite for fast history/permalink access.
Optional full output is written to compressed artifact files under the
configured data directory.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence
import gzip
import json
import os

from config import resolve_data_dir

DATA_DIR = resolve_data_dir()
RUN_OUTPUT_DIR = os.path.join(DATA_DIR, "run-output")


def ensure_run_output_dir():
    os.makedirs(RUN_OUTPUT_DIR, exist_ok=True)


class RunOutputCapture:
    def __init__(
        self,
        run_id: str,
        preview_limit: int,
        persist_full_output: bool,
        full_output_max_bytes: int,
        preview_max_bytes: int = 0,
    ):
        self.run_id = run_id
        self.preview_limit = max(0, int(preview_limit or 0))
        self.preview_max_bytes = max(0, int(preview_max_bytes or 0))
        self.persist_full_output = bool(persist_full_output)
        self.full_output_max_bytes = max(0, int(full_output_max_bytes or 0))
        self.preview_lines: deque[dict[str, object]] = deque()
        self.preview_line_bytes: deque[int] = deque()
        self.preview_bytes = 0
        self.preview_truncated = False
        self.output_line_count = 0
        self.full_output_available = False
        self.full_output_truncated = False
        self.full_output_bytes = 0
        self.artifact_rel_path: str | None = None
        self._artifact_file = None

        if self.persist_full_output:
            ensure_run_output_dir()
            self.artifact_rel_path = f"{run_id}.txt.gz"
            artifact_path = get_artifact_path(self.artifact_rel_path)
            self._artifact_file = gzip.open(artifact_path, "wt", encoding="utf-8")

    @staticmethod
    def _entry_storage_bytes(entry: dict[str, object]) -> int:
        # Match the SQLite preview serializer closely enough to keep the byte
        # cap conservative while avoiding re-serializing the whole preview.
        return len(json.dumps(entry).encode("utf-8")) + 2

    def _truncate_preview_entry(self, entry: dict[str, object]) -> dict[str, object]:
        if not self.preview_max_bytes:
            return dict(entry)
        preview_entry = dict(entry)
        if self._entry_storage_bytes(preview_entry) <= self.preview_max_bytes:
            return preview_entry
        original_text = str(preview_entry.get("text", ""))
        marker = " [preview line truncated]"
        low = 0
        high = len(original_text)
        best = ""
        while low <= high:
            mid = (low + high) // 2
            candidate = original_text[:mid] + marker
            preview_entry["text"] = candidate
            if self._entry_storage_bytes(preview_entry) <= self.preview_max_bytes:
                best = candidate
                low = mid + 1
            else:
                high = mid - 1
        preview_entry["text"] = best or marker.strip()
        self.preview_truncated = True
        return preview_entry

    def _drop_oldest_preview_line(self) -> None:
        if not self.preview_lines:
            return
        self.preview_lines.popleft()
        if self.preview_line_bytes:
            self.preview_bytes = max(0, self.preview_bytes - self.preview_line_bytes.popleft())
        self.preview_truncated = True

    def _append_preview_entry(self, entry: dict[str, object]) -> None:
        preview_entry = self._truncate_preview_entry(entry)
        entry_bytes = self._entry_storage_bytes(preview_entry)
        if self.preview_limit > 0:
            while len(self.preview_lines) >= self.preview_limit:
                self._drop_oldest_preview_line()
        self.preview_lines.append(preview_entry)
        self.preview_line_bytes.append(entry_bytes)
        self.preview_bytes += entry_bytes
        if self.preview_max_bytes > 0:
            while self.preview_bytes > self.preview_max_bytes and len(self.preview_lines) > 1:
                self._drop_oldest_preview_line()

    def add_line(
        self,
        text: str,
        cls: str = "",
        ts_clock: str = "",
        ts_elapsed: str = "",
        signals: Sequence[str] | None = None,
        line_index: int | None = None,
        command_root: str = "",
        target: str = "",
    ):
        line = str(text).rstrip("\n")
        entry: dict[str, object] = {
            "text": line,
            "cls": str(cls or ""),
            "tsC": str(ts_clock or ""),
            "tsE": str(ts_elapsed or ""),
        }
        signal_values = [str(signal) for signal in (signals or []) if str(signal)]
        if signal_values:
            entry["signals"] = signal_values
        if line_index is not None:
            entry["line_index"] = int(line_index)
        if command_root:
            entry["command_root"] = str(command_root)
        if target:
            entry["target"] = str(target)
        self.output_line_count += 1

        self._append_preview_entry(entry)

        if not self._artifact_file:
            return

        serialized = json.dumps(entry, separators=(",", ":"))
        encoded = (serialized + "\n").encode("utf-8")
        if self.full_output_max_bytes and self.full_output_bytes + len(encoded) > self.full_output_max_bytes:
            self.full_output_truncated = True
            self.close()
            return

        self._artifact_file.write(serialized + "\n")
        self.full_output_bytes += len(encoded)
        self.full_output_available = True

    def close(self):
        if self._artifact_file:
            self._artifact_file.close()
            self._artifact_file = None

    def finalize(self):
        self.close()
        if not self.full_output_available and self.artifact_rel_path:
            delete_artifact_file(self.artifact_rel_path)
            self.artifact_rel_path = None


def get_artifact_path(rel_path: str) -> str:
    return os.path.join(RUN_OUTPUT_DIR, rel_path)


def delete_artifact_file(rel_path: str | None):
    if not rel_path:
        return
    try:
        os.remove(get_artifact_path(rel_path))
    except FileNotFoundError:
        pass


def load_full_output_lines(rel_path: str) -> list[str]:
    return [str(entry.get("text", "")) for entry in load_full_output_entries(rel_path)]


def load_full_output_entries(rel_path: str) -> list[dict[str, object]]:
    with gzip.open(get_artifact_path(rel_path), "rt", encoding="utf-8") as f:
        rows = f.read().splitlines()

    parsed: list[dict[str, object]] = []
    for row in rows:
        try:
            item = json.loads(row)
        except json.JSONDecodeError:
            return [{"text": line, "cls": "", "tsC": "", "tsE": ""} for line in rows]
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            return [{"text": line, "cls": "", "tsC": "", "tsE": ""} for line in rows]
        entry: dict[str, object] = {
            "text": item["text"],
            "cls": str(item.get("cls", "")),
            "tsC": str(item.get("tsC", "")),
            "tsE": str(item.get("tsE", "")),
        }
        if isinstance(item.get("signals"), list):
            entry["signals"] = [str(signal) for signal in item["signals"] if str(signal)]
        if isinstance(item.get("line_index"), int):
            entry["line_index"] = item["line_index"]
        if isinstance(item.get("command_root"), str):
            entry["command_root"] = item["command_root"]
        if isinstance(item.get("target"), str):
            entry["target"] = item["target"]
        parsed.append(entry)
    return parsed
