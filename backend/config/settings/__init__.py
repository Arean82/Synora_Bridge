"""
Settings package — a single settings module driven by `config.ini`.

The [Server] environment flag is the source of truth:
- environment = development â†’ SQLite (locked), DEBUG per config, console email
- environment = production  â†’ hardened, invariants enforced; the database
  engine is the section whose `enabled = true` ([POSTGRES] — requires a
  verified connection before the config API persists the switch — or [SQLITE],
  the standalone default). Exactly one must be enabled.

Point DJANGO_SETTINGS_MODULE at `config.settings` (the package) — all behavior
flows from the config file, exactly like the original original app.
"""
from .base import *  # noqa: F401,F403
