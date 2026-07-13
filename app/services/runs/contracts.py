"""Shared run-start exceptions."""

from typing import Any, Callable


class RunPreparationError(Exception):
    def __init__(self, message: str, *, status_code: int = 403):
        super().__init__(message)
        self.status_code = status_code


class RunSpawnError(Exception):
    pass


class RunStartRejected(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def create_run_capture(run_id: str, factory: Callable[[str], Any], hook: Callable[..., Any] | None) -> Any:
    capture = factory(run_id)
    if hook:
        hook(run_id, capture)
    return capture


def attach_started_run(started: Any, hook: Callable[..., Any] | None) -> None:
    if not hook:
        return
    try:
        hook(started.run_id, started.capture)
    except Exception as exc:
        try:
            started.proc.terminate()
        except (AttributeError, OSError):
            pass
        raise RunSpawnError("Could not attach the run to its workflow step.") from exc
