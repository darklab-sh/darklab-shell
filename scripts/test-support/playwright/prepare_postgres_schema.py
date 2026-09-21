# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Own Postgres browser targets for exactly one Playwright invocation."""

from contextlib import ExitStack, contextmanager
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[3]
PROFILES = json.loads((ROOT / ".tooling/playwright.postgres-profiles.json").read_text())


def selected_slots(selection):
    names = json.loads(selection) if selection else [row[0] for row in PROFILES]
    if not isinstance(names, list) or any(name not in {row[0] for row in PROFILES} for name in names):
        raise ValueError("Unknown Postgres browser project")
    return [row[1] for row in PROFILES if row[0] in names]


@contextmanager
def browser_targets(dsn, directory, slots, *, fresh=False):
    # Test-only sharing; importing conftest here would change cwd and runtime config.
    sys.path.insert(0, str(ROOT / "tests/py"))
    sys.path.insert(0, str(ROOT / "app"))
    from postgres_helpers import PostgresTestDatabases

    metadata = directory / "postgres-targets.json"
    databases = PostgresTestDatabases(dsn)
    with ExitStack() as stack:
        stack.callback(databases.close)
        targets = {}
        started = perf_counter()
        for slot in slots:
            target = stack.enter_context(databases.fresh_schema() if fresh else databases.current_database())
            targets[slot] = {"dsn": target.dsn, "mode": target.mode}
        descriptor = os.open(metadata, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        stack.callback(metadata.unlink, missing_ok=True)
        with os.fdopen(descriptor, "w") as handle:
            json.dump(targets, handle)
        print("DARKLAB_POSTGRES_BROWSER_PREPARATION " + json.dumps({
            "seconds": perf_counter() - started,
            "servers": len(targets), "fresh": fresh,
            "modes": sorted({target["mode"] for target in targets.values()}),
        }), flush=True)
        yield metadata


def run_browser(command):
    def interrupted(_signal, _frame):
        raise KeyboardInterrupt

    previous = signal.signal(signal.SIGTERM, interrupted)
    try:
        with browser_targets(
            os.environ["PW_E2E_POSTGRES_DSN"], Path(os.environ["PW_E2E_SECRET_DIR"]),
            selected_slots(os.environ.get("PW_SELECTED_PROJECTS")),
            fresh=os.environ.get("PW_E2E_POSTGRES_FRESH") == "1",
        ) as metadata:
            env = dict(os.environ, PW_E2E_POSTGRES_TARGETS=str(metadata))
            with subprocess.Popen(command, env=env, start_new_session=True) as child:
                try:
                    return child.wait()
                except BaseException:
                    # Allow Playwright to stop its isolated servers before database cleanup.
                    try:
                        os.killpg(child.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                    try:
                        child.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait()
                    raise
    finally:
        signal.signal(signal.SIGTERM, previous)


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--run":
        return run_browser(sys.argv[2:])
    if len(sys.argv) != 2 or sys.argv[1] not in {row[1] for row in PROFILES}:
        raise ValueError("Expected a Postgres browser slot or --run command")
    targets = json.loads(Path(os.environ["PW_E2E_POSTGRES_TARGETS"]).read_text())
    # Captured by the server helper into DATABASE_URL, never written to its logs.
    print(targets[sys.argv[1]]["dsn"])
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
    except Exception as error:
        # Driver errors can include connection details. Keep failures useful but private.
        print(f"Postgres browser preparation/cleanup failed ({type(error).__name__})", file=sys.stderr)
        raise SystemExit(1) from None
