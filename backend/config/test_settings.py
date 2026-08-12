"""
TEST settings — hermetic Django configuration for the pytest suite.

Forces `config.ini_config` to read `backend/tests/test_config.ini` (a bundled
dev/SQLite fixture) BEFORE the real settings are imported, so the test suite:
- never depends on the developer's real `backend/config.ini` (which may be
  production + PostgreSQL with empty [SECURITY] keys — the production
  invariants would refuse to load),
- runs on a temporary SQLite test database (no PostgreSQL required),
- keeps config-API tests (GET/PUT /api/v1/config/) hermetic: they read and
  write the fixture file, never the developer's config.

Point pytest at it via backend/pytest.ini:
    DJANGO_SETTINGS_MODULE = config.test_settings
"""
from pathlib import Path

import config.ini_config as ic

_TEST_INI = Path(__file__).resolve().parent.parent / "tests" / "test_config.ini"
ic.DEFAULT_PATH = _TEST_INI
ic.load_ini.cache_clear()

# Everything the app settings define (DATABASES, middleware, apps, ...).
from config.settings.base import *  # noqa: E402,F401,F403

# Auto-restart on core config saves is a production behavior. Tests must never
# let a PUT re-exec the test runner (os.execl) — keep it off in the suite.
AUTO_RESTART_ON_SAVE = False
