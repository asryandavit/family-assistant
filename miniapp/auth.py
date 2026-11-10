"""Telegram Mini App initData check (docs/briefs/MINI_APP.md §6). Pure functions, no I/O.

The page sends Telegram.WebApp.initData (the raw signed string) as
`Authorization: tma <initData>`. Telegram's documented algorithm:

    secret_key = HMAC_SHA256(key="WebAppData", msg=bot_token)
    hash       = hex(HMAC_SHA256(key=secret_key, msg=data_check_string))

data_check_string is every received field except `hash`, as key=value, sorted by key,
joined by "\\n". Since Bot API 8.0 initData also carries `signature` (an Ed25519 signature
for third-party checks); the HMAC covers it like any other field. Settled by a real
initData captured on this PC on 2026-11-10 (fields auth_date, hash, query_id, signature,
user): its hash matches with `signature` included and not without
(tests/test_miniapp_auth.py, RealCapture).

Every rejection raises AuthError. Its `reason` is for tests and the local log only and
never reaches the page (the page only ever learns "unauthorized" or "private").
"""
import hashlib
import hmac
import json
from urllib.parse import parse_qsl, urlencode

SCHEME = "tma "
MAX_HEADER = 8192          # initData is ~0.5–1 KB; anything this big is not Telegram's
FUTURE_SKEW_S = 300        # auth_date may be at most 5 minutes ahead of our clock


class AuthError(Exception):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def init_data_from_header(header):
    """The raw initData from an Authorization header value."""
    if not header or not isinstance(header, str):
        raise AuthError("empty header")
    if len(header) > MAX_HEADER:
        raise AuthError("header too long")
    if not header.startswith(SCHEME):
        raise AuthError("wrong scheme")
    raw = header[len(SCHEME):].strip()
    if not raw:
        raise AuthError("empty initData")
    return raw


def parse_fields(raw):
    """initData query string -> dict. Rejects duplicates, a missing hash, bad encoding."""
    try:
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True,
                          errors="strict", max_num_fields=64)
    except (ValueError, UnicodeDecodeError) as e:
        raise AuthError("malformed query string") from e
    fields = {}
    for k, v in pairs:
        if k in fields:
            raise AuthError("duplicate key")
        fields[k] = v
    if not fields.get("hash"):
        raise AuthError("missing hash")
    return fields


def secret_key(bot_token):
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def data_check_string(fields, exclude=("hash",)):
    return "\n".join(f"{k}={fields[k]}" for k in sorted(fields) if k not in exclude)


def _expected(fields, key, exclude):
    return hmac.new(key, data_check_string(fields, exclude).encode(),
                    hashlib.sha256).hexdigest()


def check(raw, bot_token, now, max_age_s):
    """Validate raw initData. Returns {"user": dict, "auth_date": int}. Raises AuthError."""
    if not bot_token:
        raise AuthError("no bot token")
    fields = parse_fields(raw)
    got = fields["hash"]
    key = secret_key(bot_token)
    if not hmac.compare_digest(_expected(fields, key, ("hash",)), got):
        raise AuthError("bad hash")

    try:
        auth_date = int(fields.get("auth_date", ""))
    except ValueError as e:
        raise AuthError("bad auth_date") from e
    if auth_date > now + FUTURE_SKEW_S:
        raise AuthError("auth_date in the future")
    if now - auth_date > max_age_s:
        raise AuthError("expired")

    try:
        user = json.loads(fields.get("user", ""))
    except ValueError as e:
        raise AuthError("user is not JSON") from e
    if not isinstance(user, dict):
        raise AuthError("user is not an object")
    uid = user.get("id")
    if not isinstance(uid, int) or isinstance(uid, bool) or uid <= 0:
        raise AuthError("user has no id")
    return {"user": user, "auth_date": auth_date}


def sign(fields, bot_token):
    """Signed initData for `fields` (dict without hash). For tests and local tools only:
    the real string always comes from Telegram."""
    h = _expected(fields, secret_key(bot_token), ("hash",))
    return urlencode({**fields, "hash": h})
