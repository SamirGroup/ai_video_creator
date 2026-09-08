from config.settings.base import *  # noqa: F401,F403

DEBUG = True

# Local/dev convenience: never use console email or an ephemeral encryption
# key in a real deployment (see core/crypto.py — it warns loudly if this
# happens outside DEBUG).
