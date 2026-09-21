# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Local-only operator controls for the helper's disposable E2E database."""

import argparse
import json
import os
from pathlib import Path
import sys
import uuid
from datetime import datetime, timedelta, timezone

ENV_KEYS = ("APP_DATA_DIR", "APP_CONF_DIR", "APP_LOCAL_CONF_DIR", "ACCESS_PROFILE", "DATABASE_BACKEND",
            "DATABASE_URL", "PGOPTIONS", "OIDC_ISSUER", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET", "OIDC_REDIRECT_URI",
            "OIDC_PROVISIONING", "OIDC_CA_BUNDLE", "REDIS_URL", "APP_FAKE_REDIS")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("record", "grant", "revoke", "stale", "seed-run"))
    parser.add_argument("metadata")
    parser.add_argument("principal", nargs="?")
    args = parser.parse_args()
    if args.action == "record":
        descriptor = os.open(args.metadata, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            json.dump({key: os.environ[key] for key in ENV_KEYS if key in os.environ}, handle)
        return
    metadata = json.loads(Path(args.metadata).read_text())
    if set(metadata) - set(ENV_KEYS):
        raise SystemExit("Unexpected E2E environment field")
    for key in ENV_KEYS:
        os.environ.pop(key, None)
    os.environ.update(metadata)
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "app"))
    from services.auth.operator_grants import set_grant
    if args.action in {"grant", "revoke"}:
        set_grant(args.principal, granted=args.action == "grant")
    elif args.action == "seed-run":
        seed_run(args.principal)
    else:
        from core.database_access import get_db_connect
        from services.auth.contracts import timestamp
        with get_db_connect()() as conn:
            stale = timestamp(datetime.now(timezone.utc) - timedelta(hours=2))
            conn.execute("UPDATE browser_sessions SET authenticated_at = ?, provider_authenticated_at = ? WHERE principal_id = ?",
                         (stale, stale, args.principal))
            conn.commit()


def seed_run(principal_id):
    """Seed only a completed run; the browser creates and links the real Project."""
    from core.database_access import get_db_connect
    from services.auth.contracts import timestamp
    from services.auth.storage import get_personal_workspace
    run_id = "run_operator_e2e_" + uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    with get_db_connect()() as conn:
        workspace = get_personal_workspace(principal_id, conn=conn)
        conn.execute(
            "INSERT INTO runs (id, personal_workspace_id, run_kind, command, started, finished, exit_code, "
            "output_preview, output_line_count) VALUES (?, ?, 'external', ?, ?, ?, 0, '[]', 0)",
            (run_id, workspace.id, "dig projects.playwright.example +short",
             timestamp(now - timedelta(seconds=1)), timestamp(now)),
        )
        conn.commit()
    print(json.dumps({"run_id": run_id}))


if __name__ == "__main__":
    main()
