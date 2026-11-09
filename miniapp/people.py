"""Who may open the Mini App, and with which role (docs/briefs/MINI_APP.md §6).

Access goes by Telegram **user id + role**, never by chat id (household-ready, decision 089).
In a private chat the user id equals the chat id, so step 0 seeds the list from the two
existing chat-id environment variables named in config_miniapp.json `people`. Users and roles
(ROADMAP #4) replaces this source; `load()` / `lookup()` keep their shape.
"""
import os
from dataclasses import dataclass

ROLES = ("owner", "adult", "member", "viewer")


@dataclass(frozen=True)
class Person:
    user_id: int
    name: str
    role: str


def _as_id(value):
    v = str(value or "").strip()
    if not v.lstrip("-").isdigit():
        return None
    n = int(v)
    return n if n > 0 else None   # groups have negative ids; people never do


def load(cfg, env=None):
    """{user_id: Person} from config `people` entries ({"env", "name", "role"}). An entry
    whose variable is unset or not a positive integer is skipped; the first entry for an id
    wins (so the owner keeps the owner role if both variables hold the same id)."""
    env = os.environ if env is None else env
    out = {}
    for p in cfg.get("people", []):
        role = p.get("role")
        if role not in ROLES:
            raise ValueError(f"config_miniapp.json: unknown role {role!r}")
        uid = _as_id(env.get(p["env"]))
        if uid is not None and uid not in out:
            out[uid] = Person(uid, p["name"], role)
    return out


def lookup(people, user_id):
    return people.get(user_id)


def mask(user_id):
    """For logs: never the full id."""
    s = str(user_id)
    return "…" + s[-3:] if len(s) > 3 else "…"
