"""
Synora Bridge - one-command system initialization (setup_db + activate_db combined).

Runs the full flow in one go:
  1. Which environment?  (development / production)
  2. Development -> SQLite only. Production -> which database? (postgres / sqlite)
  3. PostgreSQL bootstrap (role + db) OR SQLite config write
  4. [SECURITY] keys ensured (generated when missing)
  5. python manage.py migrate
  6. Copy existing SQLite data into PostgreSQL? (PostgreSQL engine only, one-way)
  7. Insert demo data? (default yes) + create demo admin?

The standalone scripts (scripts/setup_db.py, scripts/activate_db.py) remain
unchanged and can still be run separately - this file drives them in one flow.

Usage:
    python scripts/initialize_system.py                    # interactive
    python scripts/initialize_system.py --yes              # defaults: development + SQLite + demo
    python scripts/initialize_system.py --environment production --database postgres
    python scripts/initialize_system.py --no-demo-data --no-migrate
"""
import argparse
import base64
import getpass
import os
import secrets
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path resolution + shared helpers
# ---------------------------------------------------------------------------
SCRIPTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = SCRIPTS_DIR.parent / "backend"
CONFIG_PATH = BACKEND_DIR / "config.ini"

sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

from config.ini_config import get_config_dict, set_ini_value  # noqa: E402
import setup_db  # noqa: E402  (reuses prompts + PG bootstrap functions)


def random_secret_key():
    from django.core.management.utils import get_random_secret_key

    return get_random_secret_key()


def random_encryption_key():
    return base64.b64encode(secrets.token_bytes(32)).decode()


def ensure_security_keys(cfg_path):
    """Generate [SECURITY] keys when empty (production refuses to boot without
    them). Never overwrites existing user values."""
    cfg = get_config_dict(str(cfg_path))
    sec = cfg.get("SECURITY", {})
    writes = []
    if not sec.get("secret_key"):
        set_ini_value(cfg_path, "SECURITY", "secret_key", random_secret_key())
        writes.append("secret_key")
    if not sec.get("encryption_key"):
        set_ini_value(cfg_path, "SECURITY", "encryption_key", random_encryption_key())
        writes.append("encryption_key")
    return writes


def run_manage_command(args_list, label):
    """Run a manage.py command in the backend with the same interpreter.

    Output is captured (not streamed) so a Ctrl+C during the child can NEVER
    spray a traceback to the console — the interrupt exits cleanly instead.
    """
    print(f"\n[{label}] python manage.py {' '.join(args_list)}")
    try:
        proc = subprocess.run(
            [sys.executable, "manage.py", *args_list],
            cwd=BACKEND_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
    except KeyboardInterrupt:
        print("\nInterrupted. Nothing was changed.")
        sys.exit(130)
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.returncode != 0:
        print(f"[error] {label} failed (exit {proc.returncode}).", file=sys.stderr)
        sys.exit(1)


# ---------------------------------------------------------------------------
# PostgreSQL bootstrap (reuses setup_db's helpers)
# ---------------------------------------------------------------------------
def postgres_bootstrap(args, cfg_path):
    def resolve(name, value):
        if value is not None:
            return value
        if args.yes:
            return setup_db.DEFAULTS[name]
        return setup_db.ask(f"PostgreSQL {name.replace('_', '-')}", setup_db.DEFAULTS[name])

    print("PostgreSQL connection (superuser):")
    pg_host = resolve("pg_host", args.pg_host)
    pg_port = resolve("pg_port", args.pg_port)
    pg_user = resolve("pg_user", args.pg_user)
    pg_db = resolve("pg_db", args.pg_db)

    pg_password = args.pg_password
    if pg_password is None:
        pg_password = os.environ.get("PG_SUPERUSER_PASSWORD")
    if pg_password is None and not args.yes:
        pg_password = getpass.getpass("PostgreSQL superuser password (blank = no password): ") or ""

    print("\nApplication database to create:")
    db_name = resolve("db_name", args.db_name)
    db_user = resolve("db_user", args.db_user)
    db_password = args.db_password or (setup_db.DEFAULTS["db_password"] if args.yes else None)
    if db_password is None:
        db_password = setup_db.generate_password() if args.yes else setup_db.ask(
            "Application DB password", None, secret=True
        ) or setup_db.generate_password()

    print(f"\nConfig file : {cfg_path}")
    print(f"PG endpoint : {pg_host}:{pg_port} (user {pg_user}@db {pg_db})")
    print(f"Will create : db '{db_name}' owner/user '{db_user}'")
    if args.yes:
        print(f"  -> generated app password: {db_password}")

    try:
        conn = setup_db.connect_superuser(pg_host, pg_port, pg_user, pg_password, pg_db)
    except Exception as exc:
        print(f"\n[error] Could not connect to PostgreSQL as '{pg_user}': {exc}", file=sys.stderr)
        print("  Check that the server is running and the superuser credentials are correct.", file=sys.stderr)
        sys.exit(1)
    print(f"[ok] PostgreSQL connection verified ({pg_user}@{pg_host}:{pg_port}/{pg_db}).")

    try:
        role_created = setup_db.ensure_role(conn, db_user, db_password)
        db_created = setup_db.ensure_database(conn, db_name, db_user)
        setup_db.ensure_privileges(conn, db_name, db_user)
        print(f"\nRole '{db_user}': {'created' if role_created else 'already existed (password updated)'}")
        print(f"Database '{db_name}': {'created' if db_created else 'already existed'}")
        print("Privileges: database ownership + ALL granted.")
    except Exception as exc:
        print(f"\n[error] Failed during PostgreSQL bootstrap: {exc}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()

    setup_db.write_production_pg_config(cfg_path, pg_host, pg_port, db_name, db_user, db_password)
    print("\n[ok] config.ini set to production + PostgreSQL "
          "(POSTGRES enabled=true, SQLITE enabled=false, debug=false, always_eager=false).")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def build_parser():
    p = argparse.ArgumentParser(
        description="One-command Synora Bridge initialization: database setup + migrate + optional demo seed.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--environment", default=None, help="'development' or 'production' (default: prompt; --yes -> development)")
    p.add_argument("--database", default=None, help="Production database: 'postgres' or 'sqlite' (default: prompt; --yes -> postgres)")
    p.add_argument("--pg-host", default=None)
    p.add_argument("--pg-port", default=None)
    p.add_argument("--pg-user", default=None)
    p.add_argument("--pg-db", default=None)
    p.add_argument("--pg-password", default=None)
    p.add_argument("--db-name", default=None)
    p.add_argument("--db-user", default=None)
    p.add_argument("--db-password", default=None)
    p.add_argument("--no-demo-data", action="store_true", help="Do NOT insert demo data.")
    p.add_argument("--no-migrate", action="store_true", help="Do NOT ask about copying SQLite data (PostgreSQL engine only).")
    p.add_argument("--create-admin", action="store_true", help="Create demo admin user (admin/admin123) with demo data.")
    p.add_argument("--yes", action="store_true", help="Non-interactive: use defaults (development + SQLite + demo).")
    return p


def main():
    args = build_parser().parse_args()

    print("=" * 62)
    print("  Synora Bridge - system initialization")
    print("=" * 62)

    if not CONFIG_PATH.exists():
        print(f"\n[error] config.ini not found at {CONFIG_PATH}", file=sys.stderr)
        sys.exit(1)

    # --- 1) Environment ---
    env_choice = (args.environment or "").strip().lower()
    if not env_choice:
        if args.yes:
            env_choice = "development"
        else:
            env_choice = setup_db.ask_choice("Which environment do you want to use:", ["development", "production"])
    if env_choice not in ("development", "production"):
        print(f"\n[error] Unknown environment '{env_choice}' - choose 'development' or 'production'.", file=sys.stderr)
        sys.exit(1)

    # --- 2) Database ---
    if env_choice == "development":
        print("\nDevelopment always uses SQLite (no PostgreSQL in development).")
        setup_db.write_sqlite_config(CONFIG_PATH, "development")
        print("[ok] config.ini set to development + SQLite (SQLITE enabled=true).")
    else:
        db_choice = (args.database or "").strip().lower()
        if not db_choice:
            if args.yes:
                db_choice = "postgres"
            else:
                db_choice = setup_db.ask_choice("Which database do you want to use (production):", ["postgres", "sqlite"])
        if db_choice not in ("postgres", "sqlite"):
            print(f"\n[error] Unknown database '{db_choice}' - choose 'postgres' or 'sqlite'.", file=sys.stderr)
            sys.exit(1)
        if db_choice == "sqlite":
            setup_db.write_sqlite_config(CONFIG_PATH, "production")
            print("\n[ok] config.ini set to production + SQLite "
                  "(debug=false, always_eager=false, SQLITE enabled=true).")
        else:
            postgres_bootstrap(args, CONFIG_PATH)

    # --- 3) SECURITY keys (production requires them) ---
    written_keys = ensure_security_keys(CONFIG_PATH)
    if written_keys:
        print(f"[setup] [SECURITY] keys generated: {', '.join(written_keys)}.")
    if env_choice == "production":
        print("  NOTE: production requires [SECURITY] secret_key + encryption_key - set them")
        print("        before starting the app (the backend refuses to start without them).")

    # --- 4) Migrate ---
    run_manage_command(["migrate"], "migrate")

    # --- 5) Load Django + the seed script (activate_db) in-process ---
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
    import django  # noqa: E402

    try:
        django.setup()
    except RuntimeError as exc:
        print(f"\n[error] {exc}", file=sys.stderr)
        print("  Fix backend/config.ini and re-run.", file=sys.stderr)
        sys.exit(1)

    import activate_db  # noqa: E402  (seed + sqlite->pg copy; config is now final)

    # --- 6) Copy SQLite data into PostgreSQL? (PostgreSQL engine only, one-way) ---
    if activate_db._db_engine == "postgresql":
        if args.no_migrate or args.yes:
            migrate = False
        else:
            migrate = setup_db.ask_choice("Copy existing SQLite data into PostgreSQL?", ["Yes", "No"]) == "Yes"
        if migrate:
            activate_db._migrate_sqlite_to_pg()

    # --- 7) Demo data (default yes) + admin ---
    if args.no_demo_data:
        demo = False
    elif args.yes:
        demo = True
    else:
        demo = setup_db.ask_choice("Insert demo data?", ["Yes", "No"]) == "Yes"

    if demo:
        create_admin = args.create_admin
        if not args.yes and not args.create_admin:
            create_admin = setup_db.ask_choice("Create demo admin user (admin/admin123)?", ["Yes", "No"]) == "Yes"
        activate_db.seed(create_admin=create_admin)
    else:
        print("Skipping demo data.")

    print("\n[done] System initialized. Start: daphne -b 127.0.0.1 -p 8000 config.asgi:application  (+ celery worker/beat)")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nInterrupted. Nothing was changed (config.ini and the database left as they were).")
        sys.exit(130)
