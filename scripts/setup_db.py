"""
Synora Bridge — one-time PostgreSQL bootstrap.

Connects to a running PostgreSQL instance as a superuser, then:
  1. Creates the application database (if it does not exist)
  2. Creates the application user/role (if it does not exist) with a password
  3. Grants ownership + privileges so the app can fully manage its database
  4. Writes the credentials into backend/config.ini [POSTGRES]

Fully interactive: every parameter prompts with a default shown in brackets —
just press Enter to accept it. Everything can also be passed as a flag for
scripting/CI (pass --yes to skip all prompts and use defaults).

Usage:
    python scripts/setup_db.py                     # interactive, defaults
    python scripts/setup_db.py --db-name prod_db   # override one parameter
    python scripts/setup_db.py --yes               # non-interactive (defaults)
    python scripts/setup_db.py --help              # all parameters + defaults

No hardcoded paths: the config file is resolved relative to this script
(<repo>/backend/config.ini). Idempotent: existing DB/role are never dropped,
only ensured + their password updated.
"""
import argparse
import getpass
import secrets
import string
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path resolution (no hardcoding — relative to this file)
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent / "backend"
CONFIG_PATH = BACKEND_DIR / "config.ini"

# ---------------------------------------------------------------------------
# Parameter defaults (shown in prompts / --help)
# ---------------------------------------------------------------------------
DEFAULTS = {
    "pg_host": "localhost",
    "pg_port": "5432",
    "pg_user": "postgres",
    "pg_db": "postgres",          # maintenance database used to connect
    "db_name": "bridge_db",       # application database to create
    "db_user": "bridge_user",     # application role to create
    "db_password": None,          # None = auto-generate a secure password
}


def ask(prompt: str, default: str | None, secret: bool = False) -> str:
    """Prompt the user; empty Enter returns the default."""
    if default is None:
        label = f"{prompt}: "
        value = getpass.getpass(label) if secret else input(label).strip()
        return value
    value = (
        getpass.getpass(f"{prompt} [{default}]: ").strip()
        if secret
        else input(f"{prompt} [{default}]: ").strip()
    )
    return value or default


def generate_password(length: int = 20) -> str:
    """Random secure password (letters + digits + a couple of symbols)."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(alphabet) for _ in range(length))



# ---------------------------------------------------------------------------
# config.ini writer - shared implementation from the backend package
# (targeted key replacement; preserves comments/formatting)
# ---------------------------------------------------------------------------
sys.path.insert(0, str(BACKEND_DIR))
from config.ini_config import set_ini_value  # noqa: E402  (needs sys.path above)

def connect_superuser(host, port, user, password, dbname):
    import psycopg2

    return psycopg2.connect(
        host=host, port=port, user=user, password=password,
        dbname=dbname, connect_timeout=10,
    )


def ensure_role(conn, role, password):
    """Create the role if missing, else update its password. Returns created flag."""
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
        exists = cur.fetchone() is not None
        if not exists:
            cur.execute(
                f'CREATE ROLE "{role}" LOGIN PASSWORD %s', (password,)
            )
            return True
        cur.execute(
            f'ALTER ROLE "{role}" WITH LOGIN PASSWORD %s', (password,)
        )
        return False
    conn.commit()


def ensure_database(conn, dbname, owner):
    """Create the database if missing, owned by the app role. Returns created flag."""
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
        exists = cur.fetchone() is not None
        if not exists:
            # CREATE DATABASE cannot run inside a transaction block.
            conn.set_session(autocommit=True)
            cur.execute(f'CREATE DATABASE "{dbname}" OWNER "{owner}"')
            conn.set_session(autocommit=False)
            return True
    return False


def ensure_privileges(conn, dbname, owner):
    """Grant all privileges on the database and public schema to the role."""
    with conn.cursor() as cur:
        cur.execute(f'ALTER DATABASE "{dbname}" OWNER TO "{owner}"')
        cur.execute(f'GRANT ALL PRIVILEGES ON DATABASE "{dbname}" TO "{owner}"')
    conn.commit()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        description="Bootstrap the PostgreSQL database + user for Synora Bridge.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--pg-host", default=None, help=f"PostgreSQL superuser host (default: {DEFAULTS['pg_host']})")
    p.add_argument("--pg-port", default=None, help=f"PostgreSQL superuser port (default: {DEFAULTS['pg_port']})")
    p.add_argument("--pg-user", default=None, help=f"PostgreSQL superuser user (default: {DEFAULTS['pg_user']})")
    p.add_argument("--pg-db", default=None, help=f"Maintenance database to connect to (default: {DEFAULTS['pg_db']})")
    p.add_argument("--db-name", default=None, help=f"Application database to create (default: {DEFAULTS['db_name']})")
    p.add_argument("--db-user", default=None, help=f"Application role to create (default: {DEFAULTS['db_user']})")
    p.add_argument("--db-password", default=None, help="Application password (blank = auto-generate)")
    p.add_argument("--config", default=str(CONFIG_PATH), help="config.ini path to update")
    p.add_argument("--yes", action="store_true", help="Non-interactive: use all defaults")
    p.add_argument("--dry-run", action="store_true", help="Validate params + config update without touching PostgreSQL")
    p.add_argument(
        "--keep-env", action="store_true",
        help="Do NOT flip [Server] environment to production after a successful setup "
        "(keeps the app on SQLite even though PostgreSQL is configured).",
    )
    return p


def main():
    args = build_parser().parse_args()
    cfg_path = Path(args.config)

    # Superuser password is always prompted (never defaulted); --yes means try empty.
    pg_password = None
    if not args.yes:
        pg_password = getpass.getpass("PostgreSQL superuser password: ")

    # Resolve parameters: flag > prompt (default) > DEFAULTS.
    def resolve(name, value):
        if value is not None:
            return value
        if args.yes:
            return DEFAULTS[name]
        return ask(f"PostgreSQL {name.replace('_', '-')}", DEFAULTS[name])

    pg_host = resolve("pg_host", args.pg_host)
    pg_port = resolve("pg_port", args.pg_port)
    pg_user = resolve("pg_user", args.pg_user)
    pg_db = resolve("pg_db", args.pg_db)
    db_name = resolve("db_name", args.db_name)
    db_user = resolve("db_user", args.db_user)
    db_password = args.db_password or (DEFAULTS["db_password"] if args.yes else None)
    if db_password is None:
        db_password = generate_password() if args.yes else ask(
            "Application DB password", None, secret=True
        ) or generate_password()

    print(f"\nConfig file : {cfg_path}")
    print(f"PG endpoint : {pg_host}:{pg_port} (user {pg_user}@db {pg_db})")
    print(f"Will create : db '{db_name}' owner/user '{db_user}'")
    print(f"App password: {'auto-generated (shown below)' if args.db_password is None and args.yes else '<provided>'}")
    if args.yes:
        print(f"  -> generated password: {db_password}")

    if not cfg_path.exists():
        print(f"\n[error] config.ini not found at {cfg_path}", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        set_ini_value(cfg_path, "POSTGRES", "host", pg_host)
        set_ini_value(cfg_path, "POSTGRES", "port", pg_port)
        set_ini_value(cfg_path, "POSTGRES", "database", db_name)
        set_ini_value(cfg_path, "POSTGRES", "username", db_user)
        set_ini_value(cfg_path, "POSTGRES", "password", db_password)
        if not args.keep_env:
            set_ini_value(cfg_path, "Server", "environment", "production")
            print("\n[dry-run] config.ini updated ([POSTGRES] + environment=production); PostgreSQL left untouched.")
        else:
            print("\n[dry-run] config.ini updated ([POSTGRES] only, --keep-env); PostgreSQL left untouched.")
        return

    # --- Connect + create ---
    try:
        conn = connect_superuser(pg_host, pg_port, pg_user, pg_password, pg_db)
    except Exception as exc:
        print(f"\n[error] Could not connect to PostgreSQL as '{pg_user}': {exc}", file=sys.stderr)
        print("  Check that the server is running and the superuser credentials are correct.", file=sys.stderr)
        sys.exit(1)

    try:
        role_created = ensure_role(conn, db_user, db_password)
        db_created = ensure_database(conn, db_name, db_user)
        ensure_privileges(conn, db_name, db_user)

        print(f"\nRole '{db_user}': {'created' if role_created else 'already existed (password updated)'}")
        print(f"Database '{db_name}': {'created' if db_created else 'already existed'}")
        print("Privileges: database ownership + ALL granted.")
    except Exception as exc:
        print(f"\n[error] Failed during PostgreSQL bootstrap: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()

    # --- Write config.ini ---
    set_ini_value(cfg_path, "POSTGRES", "host", pg_host)
    set_ini_value(cfg_path, "POSTGRES", "port", pg_port)
    set_ini_value(cfg_path, "POSTGRES", "database", db_name)
    set_ini_value(cfg_path, "POSTGRES", "username", db_user)
    set_ini_value(cfg_path, "POSTGRES", "password", db_password)

    # Successful PostgreSQL bootstrap -> the app should USE it: flip the
    # environment flag to production so [POSTGRES] is selected instead of
    # SQLite. Use --keep-env to stay on SQLite.
    if not args.keep_env:
        set_ini_value(cfg_path, "Server", "environment", "production")
        env_note = "environment flipped to production"
    else:
        env_note = "environment kept as-is (--keep-env)"

    print(f"\n[ok] config.ini updated: [POSTGRES] credentials written, {env_note}.")
    print("  Next: python manage.py migrate && python manage.py sync_beat")


if __name__ == "__main__":
    main()
