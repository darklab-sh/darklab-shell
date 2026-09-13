# SPDX-FileCopyrightText: 2026 mmayhew
# SPDX-License-Identifier: AGPL-3.0-only

"""Create one disposable Playwright schema and print its name."""

from __future__ import annotations

import os
import sys
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
from psycopg import sql


def main() -> int:
    if len(sys.argv) != 2 or not sys.argv[1].startswith("pg-"):
        raise SystemExit("expected a PostgreSQL Playwright slot")
    dsn = os.environ["PW_E2E_POSTGRES_DSN"]
    parts = urlsplit(dsn)
    if parts.scheme not in {"postgres", "postgresql"}:
        raise SystemExit("PW_E2E_POSTGRES_DSN must be a PostgreSQL URL")
    schema = f"darklab_e2e_{uuid4().hex}"
    with psycopg.connect(dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    print(schema)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
