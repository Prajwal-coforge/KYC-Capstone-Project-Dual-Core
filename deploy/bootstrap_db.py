"""Create the limited database user from inside the network. Never prints the URL."""

from __future__ import annotations

import json
from pathlib import Path

from psycopg import sql


def ensure_app_user(conn, password: str) -> None:
    """kyc_app can connect and install the copilot tables. It cannot create a database."""
    exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", ("kyc_app",)).fetchone()
    statement = (
        "ALTER USER kyc_app WITH PASSWORD {}"
        if exists
        else ("CREATE USER kyc_app WITH PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE")
    )
    conn.execute(sql.SQL(statement).format(sql.Literal(password)))
    conn.execute("GRANT CONNECT ON DATABASE kyc TO kyc_app")
    conn.execute("GRANT USAGE, CREATE ON SCHEMA public TO kyc_app")


def main() -> None:
    import sys

    import psycopg

    if len(sys.argv) > 1 and sys.argv[1] == "--check":
        app = json.loads(Path("/run/kyc/app.json").read_text())
        with psycopg.connect(app["url"]) as conn:
            conn.execute("SELECT 1")
        return
    admin = json.loads(Path("/run/kyc/admin.json").read_text())
    password = Path("/run/kyc/app.pass").read_text().strip()
    with psycopg.connect(admin["url"], autocommit=True) as conn:
        ensure_app_user(conn, password)


if __name__ == "__main__":
    main()
