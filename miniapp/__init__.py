"""Telegram Mini App, step 0 (docs/briefs/MINI_APP.md): a small server on the PC that serves the
built web app and a JSON API, reached from Telegram through Tailscale Funnel."""
import json
import os

__version__ = "0.1.0"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST = os.path.join(ROOT, "miniapp", "web", "dist")
LOG_DIR = os.path.join(ROOT, ".browser")      # gitignored, next to listener.log
TMP = os.path.join(ROOT, "tmp")
CAPTURE = os.path.join(TMP, "miniapp_initdata.txt")   # gitignored; live signature


def load_config(path=None):
    with open(path or os.path.join(ROOT, "config_miniapp.json"), encoding="utf-8") as f:
        return json.load(f)


def load_machine(path=None):
    """machine.json (gitignored) or {} when the file is absent."""
    p = path or os.path.join(ROOT, "machine.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def public_url(machine=None):
    """The https URL Telegram opens (machine.json miniapp_public_url), or "" if unset."""
    u = str((load_machine() if machine is None else machine).get("miniapp_public_url") or "")
    return u if u.startswith("https://") else ""


def bot_token():
    """The bot token from the env var named in config.json (never logged, never sent)."""
    with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
        env = json.load(f)["telegram"]["bot_token_env"]
    return os.environ.get(env, "")
