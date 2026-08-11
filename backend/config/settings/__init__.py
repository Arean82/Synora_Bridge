"""
Settings package — a single settings module driven by `config.ini`.

The [Server] environment flag is the source of truth:
- environment = development â†’ SQLite, DEBUG per config, console email
- environment = production  â†’ PostgreSQL, hardened, invariants enforced

Point DJANGO_SETTINGS_MODULE at `config.settings` (the package) — all behavior
flows from the config file, exactly like the original original app.
"""
from .base import *  # noqa: F401,F403
