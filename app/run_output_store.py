"""
Split run-output persistence helpers.

Preview output stays in SQLite for fast history/permalink access.
Optional full output is written to compressed artifact files under /data.
"""

from __future__ import annotations

from collections import deque
import gzip
import os


DATA_DIR = "/data" if os.path.isdir("/data") else "/tmp"  # nosec B108
RUN_OUTPUT_DIR = os.path.join(DATA_DIR, "run-output")


def ensure_run_output_dir():
    os.makedirs(RUN_OUTPUT_DIR, exist_ok=True)


class RunOutputCapture:
    def __init__(self, run_id: str, preview_limit: int, persist_full_output: bool, full_output_max_bytes: int):
        self.run_id = run_id
        self.preview_limit = max(0, int(preview_limit or 0))
        self.persist_full_output = bool(persist_full_output)
        self.full_output_max_bytes = max(0, int(full_output_max_bytes or 0))
        self.preview_lines: deque[str] = deque()
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

    def add_line(self, text: str):
        line = str(text).rstrip("\n")
        self.output_line_count += 1

        if self.preview_limit == 0:
            self.preview_lines.append(line)
        else:
            if len(self.preview_lines) >= self.preview_limit:
                self.preview_lines.popleft()
                self.preview_truncated = True
            self.preview_lines.append(line)

        if not self._artifact_file:
            return

        encoded = (line + "\n").encode("utf-8")
        if self.full_output_max_bytes and self.full_output_bytes + len(encoded) > self.full_output_max_bytes:
            self.full_output_truncated = True
            self.close()
            return

        self._artifact_file.write(line + "\n")
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
    with gzip.open(get_artifact_path(rel_path), "rt", encoding="utf-8") as f:
        return f.read().splitlines()
