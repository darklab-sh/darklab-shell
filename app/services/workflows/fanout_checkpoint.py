# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Bounded, serializable checkpoint state for workflow fan-out."""

from __future__ import annotations

from dataclasses import dataclass

MAX_CHECKPOINT_ITEMS = 32


@dataclass(frozen=True)
class FanoutCheckpoint:
    """Child ordinal state retained by a durable execution owner."""

    pending: tuple[int, ...] = ()
    running: tuple[int, ...] = ()
    completed: tuple[int, ...] = ()
    failed: tuple[int, ...] = ()
    skipped: tuple[int, ...] = ()
    cancelled: bool = False

    def next_batch(self, limit: int) -> tuple[int, ...]:
        """Return unlaunched ordinals in stable order for the next checkpoint."""
        try:
            batch_limit = max(int(limit), 1)
        except (TypeError, ValueError) as exc:
            raise ValueError("checkpoint batch limit must be an integer") from exc
        if self.cancelled:
            return ()
        return self.pending[:batch_limit]

    def mark_running(self, ordinals: tuple[int, ...] | list[int]) -> "FanoutCheckpoint":
        chosen = {int(item) for item in ordinals if int(item) in self.pending}
        pending = tuple(item for item in self.pending if item not in chosen)
        running = tuple(dict.fromkeys((*self.running, *sorted(chosen))))
        return FanoutCheckpoint(
            pending, running, self.completed, self.failed, self.skipped, self.cancelled
        )

    def mark_completed(self, ordinals: tuple[int, ...] | list[int]) -> "FanoutCheckpoint":
        return self._advance(ordinals, completed=True)

    def mark_failed(self, ordinals: tuple[int, ...] | list[int]) -> "FanoutCheckpoint":
        return self._advance(ordinals, completed=False)

    def mark_skipped(self, ordinals: tuple[int, ...] | list[int]) -> "FanoutCheckpoint":
        """Move selected unfinished ordinals into a terminal skipped state."""
        unfinished = set(self.pending) | set(self.running)
        chosen = {int(item) for item in ordinals if int(item) in unfinished}
        pending = tuple(item for item in self.pending if item not in chosen)
        running = tuple(item for item in self.running if item not in chosen)
        skipped = tuple(dict.fromkeys((*self.skipped, *sorted(chosen))))
        return FanoutCheckpoint(
            pending, running, self.completed, self.failed, skipped, self.cancelled
        )

    def reset_running(self, ordinals: tuple[int, ...] | list[int]) -> "FanoutCheckpoint":
        """Return unbound launching children to stable pending order."""
        chosen = {int(item) for item in ordinals if int(item) in self.running}
        pending = tuple(sorted(dict.fromkeys((*self.pending, *chosen))))
        running = tuple(item for item in self.running if item not in chosen)
        return FanoutCheckpoint(
            pending, running, self.completed, self.failed, self.skipped, self.cancelled
        )

    def cancel(self) -> "FanoutCheckpoint":
        return FanoutCheckpoint(
            self.pending, self.running, self.completed, self.failed, self.skipped, True
        )

    def to_payload(self) -> dict[str, object]:
        """Return a bounded JSON-compatible checkpoint payload."""
        return {
            "pending": list(self.pending),
            "running": list(self.running),
            "completed": list(self.completed),
            "failed": list(self.failed),
            "skipped": list(self.skipped),
            "cancelled": self.cancelled,
        }

    def _advance(self, ordinals: tuple[int, ...] | list[int], *, completed: bool) -> "FanoutCheckpoint":
        available = set(self.pending) | set(self.running)
        chosen = {int(item) for item in ordinals if int(item) in available}
        pending = tuple(item for item in self.pending if item not in chosen)
        running = tuple(item for item in self.running if item not in chosen)
        ordered = tuple(sorted(chosen))
        target = tuple(dict.fromkeys((*self.completed, *ordered))) if completed else self.completed
        failures = self.failed if completed else tuple(dict.fromkeys((*self.failed, *ordered)))
        if any(item < 0 for item in (*pending, *running, *target, *failures, *self.skipped)):
            raise ValueError("checkpoint ordinals must be non-negative")
        if (
            len(pending) + len(running) + len(target) + len(failures) + len(self.skipped)
            > MAX_CHECKPOINT_ITEMS
        ):
            raise ValueError("fan-out checkpoint exceeds the item limit")
        return FanoutCheckpoint(
            pending, running, target, failures, self.skipped, self.cancelled
        )


def checkpoint_from_payload(value: object) -> FanoutCheckpoint:
    """Restore checkpoint state, rejecting malformed or oversized payloads."""
    if not isinstance(value, dict):
        raise ValueError("fan-out checkpoint must be an object")

    def ordinals(name: str) -> tuple[int, ...]:
        raw = value.get(name, [])
        if not isinstance(raw, list) or len(raw) > MAX_CHECKPOINT_ITEMS:
            raise ValueError(f"fan-out checkpoint {name} is invalid")
        result = []
        for item in raw:
            if isinstance(item, bool):
                raise ValueError(f"fan-out checkpoint {name} contains an invalid ordinal")
            try:
                ordinal = int(item)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"fan-out checkpoint {name} contains an invalid ordinal") from exc
            if ordinal < 0 or ordinal in result:
                raise ValueError(f"fan-out checkpoint {name} contains an invalid ordinal")
            result.append(ordinal)
        return tuple(result)

    pending = ordinals("pending")
    running = ordinals("running")
    completed = ordinals("completed")
    failed = ordinals("failed")
    skipped = ordinals("skipped")
    groups = (set(pending), set(running), set(completed), set(failed), set(skipped))
    if any(left & right for index, left in enumerate(groups) for right in groups[index + 1:]):
        raise ValueError("fan-out checkpoint states overlap")
    if len(pending) + len(running) + len(completed) + len(failed) + len(skipped) > MAX_CHECKPOINT_ITEMS:
        raise ValueError("fan-out checkpoint exceeds the item limit")
    cancelled = value.get("cancelled", False)
    if not isinstance(cancelled, bool):
        raise ValueError("fan-out checkpoint cancelled must be a boolean")
    return FanoutCheckpoint(pending, running, completed, failed, skipped, cancelled)


def create_fanout_checkpoint(child_count: int) -> FanoutCheckpoint:
    """Create a checkpoint for a bounded child plan."""
    try:
        count = int(child_count)
    except (TypeError, ValueError) as exc:
        raise ValueError("fan-out child count must be an integer") from exc
    if not 0 <= count <= MAX_CHECKPOINT_ITEMS:
        raise ValueError(f"fan-out child count must be between 0 and {MAX_CHECKPOINT_ITEMS}")
    return FanoutCheckpoint(pending=tuple(range(count)))
