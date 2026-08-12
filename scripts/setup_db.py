"""
Synora Bridge - database setup (SQLite or PostgreSQL).

First asks which environment you are setting up:

  development  -> SQLite only (development is locked to SQLite by design):
                  config = development + SQLite.
  production   -> asks which database:
                    postgres  -> the PostgreSQL bootstrap flow: connect as a
                                 superuser, create the application role +
                                 database, grant privileges, and switch the
                                 config to production + PostgreSQL.
                    sqlite    -> production + SQLite (hardened values, no
                                 server, SQLite auto-creates its file).

Everything prompts with numbered menus; free-text fields show defaults in
brackets. Everything can also be passed as a flag for scripting/CI (--yes).

Usage:
    python scripts/setup_db.py                    # interactive, defaults
    python scripts/setup_db.py --environment production --database sqlite
    python scripts/setup_db.py --environment production --database postgres --db-name prod_db
    python scripts/setup_db.py --pg-password s3cret
    python scripts/setup_db.py --yes              # non-interactive (defaults)

No hardcoded paths: the config file is resolved relative to this script
(<repo>/backend/config.ini). PostgreSQL bootstrap is idempotent: existing
DB/role are never dropped, only ensured + their password updated.
"""
import argparse
import getpass
import os
import secrets
import string
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path resolution (no hardcoding - relative to this file)
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


def ask_choice(prompt: str, options: list[str], default: str | None = None) -> str:
    """Numbered selection menu - the user types the number of the option."""
    print(prompt)
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    while True:
        value = input(f"Choose 1-{len(options)} [{default}]: " if default else f"Choose 1-{len(options)}: ").strip()
        if not value and default:
            return default
        if value.isdigit() and 1 <= int(value) <= len(options):
            return options[int(value) - 1]
        print(f"  Please enter a number between 1 and {len(options)}.")


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

    conn = psycopg2.connect(
        host=host, port=port, user=user, password=password,
        dbname=dbname, connect_timeout=10,
    )
    # Session-wide autocommit: bootstrap DDL (CREATE ROLE, CREATE DATABASE,
    # ALTER DATABASE ... OWNER) must NOT run inside a transaction block. With
    # autocommit on, every statement commits immediately and no stale open
    # transaction can leak between steps (the previous code called
    # conn.set_session(autocommit=True) after a SELECT - psycopg2 had already
    # opened a transaction, so it raised "set_session cannot be used inside a
    # transaction"; and ensure_role() returned before its conn.commit()).
    conn.autocommit = True
    return conn


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


def ensure_database(conn, dbname, owner):
    """Create the database if missing, owned by the app role. Returns created flag."""
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
        exists = cur.fetchone() is not None
        if not exists:
            # CREATE DATABASE cannot run inside a transaction block - the
            # connection is already in autocommit mode (see connect_superuser).
            cur.execute(f'CREATE DATABASE "{dbname}" OWNER "{owner}"')
            return True
    return False


def ensure_privileges(conn, dbname, owner):
    """Grant all privileges on the database and public schema to the role."""
    with conn.cursor() as cur:
        cur.execute(f'ALTER DATABASE "{dbname}" OWNER TO "{owner}"')
        cur.execute(f'GRANT ALL PRIVILEGES ON DATABASE "{dbname}" TO "{owner}"')


def write_production_pg_config(cfg_path, pg_host, pg_port, db_name, db_user, db_password):
    """Write the full production+PostgreSQL config."""
    set_ini_value(cfg_path, "POSTGRES", "host", pg_host)
    set_ini_value(cfg_path, "POSTGRES", "port", pg_port)
    set_ini_value(cfg_path, "POSTGRES", "database", db_name)
    set_ini_value(cfg_path, "POSTGRES", "username", db_user)
    set_ini_value(cfg_path, "POSTGRES", "password", db_password)
    set_ini_value(cfg_path, "Server", "environment", "production")
    set_ini_value(cfg_path, "Server", "debug", "false")
    set_ini_value(cfg_path, "CELERY", "always_eager", "false")
    set_ini_value(cfg_path, "POSTGRES", "enabled", "true")
    set_ini_value(cfg_path, "SQLITE", "enabled", "false")


def write_sqlite_config(cfg_path, env_choice):
    """Write the SQLite config for the chosen environment (SQLite auto-creates)."""
    set_ini_value(cfg_path, "POSTGRES", "enabled", "false")
    set_ini_value(cfg_path, "SQLITE", "enabled", "true")
    set_ini_value(cfg_path, "Server", "environment", env_choice)
    if env_choice == "production":
        set_ini_value(cfg_path, "Server", "debug", "false")
        set_ini_value(cfg_path, "CELERY", "always_eager", "false")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        description="Set up the Synora Bridge database: SQLite (env choice) or PostgreSQL (bootstrap + config switch).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--database", default=None, help="Database to use: 'sqlite' or 'postgres' (default: prompt; --yes -> postgres)")
    p.add_argument("--environment", default=None, help="Environment for SQLite: 'development' or 'production' (default: prompt; --yes -> development)")
    p.add_argument("--pg-host", default=None, help=f"PostgreSQL superuser host (default: {DEFAULTS['pg_host']})")
    p.add_argument("--pg-port", default=None, help=f"PostgreSQL superuser port (default: {DEFAULTS['pg_port']})")
    p.add_argument("--pg-user", default=None, help=f"PostgreSQL superuser user (default: {DEFAULTS['pg_user']})")
    p.add_argument("--pg-db", default=None, help=f"Maintenance database to connect to (default: {DEFAULTS['pg_db']})")
    p.add_argument("--pg-password", default=None, help="PostgreSQL superuser password (default: prompt, or PG_SUPERUSER_PASSWORD env; --yes tries empty)")
    p.add_argument("--db-name", default=None, help=f"Application database to create (default: {DEFAULTS['db_name']})")
    p.add_argument("--db-user", default=None, help=f"Application role to create (default: {DEFAULTS['db_user']})")
    p.add_argument("--db-password", default=None, help="Application password (blank = auto-generate)")
    p.add_argument("--config", default=str(CONFIG_PATH), help="config.ini path to update")
    p.add_argument("--yes", action="store_true", help="Non-interactive: use all defaults")
    p.add_argument("--dry-run", action="store_true", help="Validate params + write the production config without touching PostgreSQL")
    return p


def main():
    args = build_parser().parse_args()
    cfg_path = Path(args.config)

    if not cfg_path.exists():
        print(f"\n[error] config.ini not found at {cfg_path}", file=sys.stderr)
        sys.exit(1)

    # --- 1) Which environment? ---
    env_choice = (args.environment or "").strip().lower()
    if not env_choice:
        if args.yes:
            env_choice = "development"
        else:
            env_choice = ask_choice("Which environment do you want to use:", ["development", "production"])
    if env_choice not in ("development", "production"):
        print(f"\n[error] Unknown environment '{env_choice}' - choose 'development' or 'production'.", file=sys.stderr)
        sys.exit(1)

    # --- 2) Development is SQLite only (locked by design) ---
    if env_choice == "development":
        print("\nDevelopment always uses SQLite (no PostgreSQL in development).")
        write_sqlite_config(cfg_path, "development")
        print("\n[ok] config.ini set to development + SQLite (SQLITE enabled=true).")
        print("  Next: python manage.py migrate && python manage.py sync_beat")
        return

    # --- 3) Production: which database? ---
    db_choice = (args.database or "").strip().lower()
    if not db_choice:
        if args.yes:
            db_choice = "postgres"
        else:
            db_choice = ask_choice("Which database do you want to use (production):", ["postgres", "sqlite"])
    if db_choice not in ("sqlite", "postgres"):
        print(f"\n[error] Unknown database '{db_choice}' - choose 'sqlite' or 'postgres'.", file=sys.stderr)
        sys.exit(1)

    # --- 4) Production + SQLite (standalone) ---
    if db_choice == "sqlite":
        write_sqlite_config(cfg_path, "production")
        print("\n[ok] config.ini set to production + SQLite "
              "(debug=false, always_eager=false, SQLITE enabled=true).")
        print("  NOTE: production requires [SECURITY] secret_key + encryption_key - set them")
        print("        before starting the app (the backend refuses to start without them).")
        print("  Next: python manage.py migrate && python manage.py sync_beat")
        return

    # --- 5) Production + PostgreSQL bootstrap ---
    # Resolve parameters: flag > prompt (default) > DEFAULTS.
    def resolve(name, value):
        if value is not None:
            return value
        if args.yes:
            return DEFAULTS[name]
        return ask(f"PostgreSQL {name.replace('_', '-')}", DEFAULTS[name])

    print("PostgreSQL connection (superuser):")
    pg_host = resolve("pg_host", args.pg_host)
    pg_port = resolve("pg_port", args.pg_port)
    pg_user = resolve("pg_user", args.pg_user)
    pg_db = resolve("pg_db", args.pg_db)

    # Superuser password: flag > PG_SUPERUSER_PASSWORD env > prompt > --yes.
    # Blank = try no password (trust/peer auth on the maintenance database).
    pg_password = args.pg_password
    if pg_password is None:
        pg_password = os.environ.get("PG_SUPERUSER_PASSWORD")
    if pg_password is None and not args.yes:
        pg_password = getpass.getpass(
            "PostgreSQL superuser password (blank = no password): "
        ) or ""

    # Verify the connection RIGHT AFTER the PG details, before asking anything
    # else - fail fast with the real server error (skipped in --dry-run).
    conn = None
    if not args.dry_run:
        try:
            conn = connect_superuser(pg_host, pg_port, pg_user, pg_password, pg_db)
        except Exception as exc:
            print(f"\n[error] Could not connect to PostgreSQL as '{pg_user}': {exc}", file=sys.stderr)
            print("  Check that the server is running and the superuser credentials are correct.", file=sys.stderr)
            sys.exit(1)
        print(f"\n[ok] PostgreSQL connection verified ({pg_user}@{pg_host}:{pg_port}/{pg_db}).")

    print("\nApplication database to create:")
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

    if args.dry_run:
        write_production_pg_config(cfg_path, pg_host, pg_port, db_name, db_user, db_password)
        print("\n[dry-run] config.ini updated to production + PostgreSQL "
              "(POSTGRES enabled=true, SQLITE enabled=false, debug=false, always_eager=false); PostgreSQL left untouched.")
        return

    # --- Bootstrap on the already-verified connection ---
    assert conn is not None, "connection must be verified before bootstrap (dry-run returns above)"
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

    # --- Write config.ini (production + PostgreSQL) ---
    write_production_pg_config(cfg_path, pg_host, pg_port, db_name, db_user, db_password)
    print("\n[ok] config.ini updated to production + PostgreSQL "
          "(POSTGRES enabled=true, SQLITE enabled=false, debug=false, always_eager=false).")
    print("  NOTE: production requires [SECURITY] secret_key + encryption_key - set them")
    print("        before starting the app (the backend refuses to start without them).")
    print("  Next: python manage.py migrate && python manage.py sync_beat")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted. Nothing was changed (config.ini and PostgreSQL left as they were).")
        sys.exit(130)
