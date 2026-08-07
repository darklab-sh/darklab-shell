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
    completed: tuple[int, ...] = ()
    failed: tuple[int, ...] = ()
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

    def mark_completed(self, ordinals: tuple[int, ...] | list[int]) -> "FanoutCheckpoint":
        return self._advance(ordinals, completed=True)

    def mark_failed(self, ordinals: tuple[int, ...] | list[int]) -> "FanoutCheckpoint":
        return self._advance(ordinals, completed=False)

    def cancel(self) -> "FanoutCheckpoint":
        return FanoutCheckpoint(self.pending, self.completed, self.failed, True)

    def _advance(self, ordinals: tuple[int, ...] | list[int], *, completed: bool) -> "FanoutCheckpoint":
        chosen = {int(item) for item in ordinals if int(item) in self.pending}
        pending = tuple(item for item in self.pending if item not in chosen)
        target = tuple(dict.fromkeys((*self.completed, *chosen))) if completed else self.completed
        failures = self.failed if completed else tuple(dict.fromkeys((*self.failed, *chosen)))
        if any(item < 0 for item in (*pending, *target, *failures)):
            raise ValueError("checkpoint ordinals must be non-negative")
        if len(pending) + len(target) + len(failures) > MAX_CHECKPOINT_ITEMS:
            raise ValueError("fan-out checkpoint exceeds the item limit")
        return FanoutCheckpoint(pending, target, failures, self.cancelled)


def create_fanout_checkpoint(child_count: int) -> FanoutCheckpoint:
    """Create a checkpoint for a bounded child plan."""
    try:
        count = int(child_count)
    except (TypeError, ValueError) as exc:
        raise ValueError("fan-out child count must be an integer") from exc
    if not 0 <= count <= MAX_CHECKPOINT_ITEMS:
        raise ValueError(f"fan-out child count must be between 0 and {MAX_CHECKPOINT_ITEMS}")
    return FanoutCheckpoint(pending=tuple(range(count)))
