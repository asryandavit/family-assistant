"""miniapp.auth + miniapp.people (docs/briefs/MINI_APP.md §6, §8). Strings are signed here with
a test token; the field layout (query_id, user JSON, auth_date, signature, hash) is Telegram's
documented initData. RealCapture checks a real string captured on this PC and is skipped when
tmp/miniapp_initdata.txt is absent (it holds a live signature and is never committed)."""
import json
import os
import unittest
from typing import ClassVar
from urllib.parse import parse_qsl, urlencode

from miniapp import CAPTURE, auth, bot_token, load_config, people

TOKEN = "123456:TEST-token-not-real"
NOW = 1_800_000_000
DAY = 24 * 3600
USER = {"id": 111222333, "first_name": "Test", "language_code": "en",
        "allows_write_to_pm": True}


def fields(**over):
    f = {"query_id": "AAHtest", "user": json.dumps(USER, separators=(",", ":")),
         "auth_date": str(NOW - 60)}
    f.update(over)
    return f


def signed(**over):
    return auth.sign(fields(**over), TOKEN)


def resign_without_signature(f):
    """A string whose hash covers every field except `signature`."""
    h = auth._expected(f, auth.secret_key(TOKEN), ("hash", "signature"))
    return urlencode({**f, "hash": h})


class Accept(unittest.TestCase):
    def test_valid(self):
        r = auth.check(signed(), TOKEN, NOW, DAY)
        self.assertEqual(r["user"]["id"], USER["id"])
        self.assertEqual(r["auth_date"], NOW - 60)

    def test_header_round_trip(self):
        raw = auth.init_data_from_header("tma " + signed())
        self.assertEqual(auth.check(raw, TOKEN, NOW, DAY)["user"]["id"], USER["id"])

    def test_signature_covered(self):
        auth.check(signed(signature="sig-abc"), TOKEN, NOW, DAY)

    def test_known_vector(self):
        # hand-computed with the documented formula, independent of auth.sign
        import hashlib
        import hmac
        f = fields()
        dcs = "\n".join(f"{k}={f[k]}" for k in sorted(f))
        key = hmac.new(b"WebAppData", TOKEN.encode(), hashlib.sha256).digest()
        h = hmac.new(key, dcs.encode(), hashlib.sha256).hexdigest()
        auth.check(urlencode({**f, "hash": h}), TOKEN, NOW, DAY)


class Reject(unittest.TestCase):
    def reason(self, raw, token=TOKEN, now=NOW):
        with self.assertRaises(auth.AuthError) as cm:
            auth.check(raw, token, now, DAY)
        return cm.exception.reason

    def test_tampered_field(self):
        d = dict(parse_qsl(signed()))
        d["user"] = d["user"].replace(str(USER["id"]), "999")
        self.assertEqual(self.reason(urlencode(d)), "bad hash")

    def test_tampered_auth_date(self):
        d = dict(parse_qsl(signed()))
        d["auth_date"] = str(NOW)
        self.assertEqual(self.reason(urlencode(d)), "bad hash")

    def test_tampered_signature_when_covered(self):
        d = dict(parse_qsl(signed(signature="sig-abc")))
        d["signature"] = "sig-xyz"
        self.assertEqual(self.reason(urlencode(d)), "bad hash")

    def test_hash_without_signature_rejected(self):
        # the real capture showed Telegram's hash covers `signature`; a hash that skips it
        # is not Telegram's and lets `signature` be swapped freely
        raw = resign_without_signature(fields(signature="sig-abc"))
        self.assertEqual(self.reason(raw), "bad hash")

    def test_wrong_hash(self):
        d = dict(parse_qsl(signed()))
        d["hash"] = "0" * 64
        self.assertEqual(self.reason(urlencode(d)), "bad hash")

    def test_wrong_token(self):
        self.assertEqual(self.reason(signed(), token="654321:other"), "bad hash")

    def test_no_token_configured(self):
        self.assertEqual(self.reason(signed(), token=""), "no bot token")

    def test_missing_hash(self):
        self.assertEqual(self.reason(urlencode(fields())), "missing hash")

    def test_empty_hash(self):
        self.assertEqual(self.reason(urlencode({**fields(), "hash": ""})), "missing hash")

    def test_duplicate_key(self):
        raw = signed() + "&auth_date=" + str(NOW)
        self.assertEqual(self.reason(raw), "duplicate key")

    def test_duplicate_hash(self):
        raw = signed() + "&hash=" + "0" * 64
        self.assertEqual(self.reason(raw), "duplicate key")

    def test_expired(self):
        self.assertEqual(self.reason(signed(auth_date=str(NOW - DAY - 1))), "expired")

    def test_future(self):
        self.assertEqual(self.reason(signed(auth_date=str(NOW + 301))),
                         "auth_date in the future")

    def test_small_clock_skew_ok(self):
        auth.check(signed(auth_date=str(NOW + 120)), TOKEN, NOW, DAY)

    def test_auth_date_not_int(self):
        self.assertEqual(self.reason(signed(auth_date="yesterday")), "bad auth_date")

    def test_missing_auth_date(self):
        f = fields()
        del f["auth_date"]
        self.assertEqual(self.reason(auth.sign(f, TOKEN)), "bad auth_date")

    def test_malformed_user_json(self):
        self.assertEqual(self.reason(signed(user="{id:1")), "user is not JSON")

    def test_user_not_object(self):
        self.assertEqual(self.reason(signed(user="[1,2]")), "user is not an object")

    def test_user_without_id(self):
        self.assertEqual(self.reason(signed(user='{"first_name":"x"}')), "user has no id")

    def test_user_id_string(self):
        self.assertEqual(self.reason(signed(user='{"id":"111"}')), "user has no id")

    def test_missing_user(self):
        f = fields()
        del f["user"]
        self.assertEqual(self.reason(auth.sign(f, TOKEN)), "user is not JSON")

    def test_malformed_query(self):
        self.assertEqual(self.reason("no-equals-sign"), "malformed query string")

    def test_bad_percent_encoding(self):
        self.assertEqual(self.reason("user=%ff%fe&hash=ab"), "malformed query string")


class Header(unittest.TestCase):
    def reason(self, header):
        with self.assertRaises(auth.AuthError) as cm:
            auth.init_data_from_header(header)
        return cm.exception.reason

    def test_empty_header(self):
        self.assertEqual(self.reason(""), "empty header")
        self.assertEqual(self.reason(None), "empty header")

    def test_scheme_only(self):
        self.assertEqual(self.reason("tma "), "empty initData")

    def test_wrong_scheme(self):
        self.assertEqual(self.reason("Bearer abc"), "wrong scheme")

    def test_too_long(self):
        self.assertEqual(self.reason("tma " + "a" * 9000), "header too long")


class People(unittest.TestCase):
    CFG: ClassVar[dict] = {"people": [{"env": "A", "name": "Davit", "role": "owner"},
                                      {"env": "B", "name": "Karine", "role": "adult"}]}

    def test_both(self):
        p = people.load(self.CFG, {"A": "111", "B": " 222 "})
        self.assertEqual(p[111], people.Person(111, "Davit", "owner"))
        self.assertEqual(p[222].role, "adult")

    def test_unknown_user(self):
        p = people.load(self.CFG, {"A": "111"})
        self.assertIsNone(people.lookup(p, 999))
        self.assertEqual(list(p), [111])

    def test_skips_bad_values(self):
        self.assertEqual(people.load(self.CFG, {"A": "-100123", "B": "abc"}), {})

    def test_same_id_keeps_first_role(self):
        self.assertEqual(people.load(self.CFG, {"A": "111", "B": "111"})[111].role, "owner")

    def test_bad_role_rejected(self):
        with self.assertRaises(ValueError):
            people.load({"people": [{"env": "A", "name": "x", "role": "admin"}]}, {"A": "1"})

    def test_mask(self):
        self.assertEqual(people.mask(123456789), "…789")
        self.assertNotIn("123456", people.mask(123456789))
        self.assertEqual(people.mask(12), "…")

    def test_repo_config_roles(self):
        roles = [(p["name"], p["role"]) for p in load_config()["people"]]
        self.assertEqual(roles, [("Davit", "owner"), ("Karine", "adult")])


@unittest.skipUnless(os.path.exists(CAPTURE) and bot_token(),
                     "no real initData capture in tmp/ (local-only test)")
class RealCapture(unittest.TestCase):
    """A real initData saved by `python -m miniapp.server --capture-initdata` validates against
    the real token (age ignored: the capture is old by the time the test runs)."""

    def test_real_initdata_validates(self):
        with open(CAPTURE, encoding="utf-8") as f:
            raw = f.read().strip()
        r = auth.check(raw, bot_token(), r_now(raw), 10**9)
        persons = people.load(load_config())
        self.assertIsNotNone(people.lookup(persons, r["user"]["id"]))


def r_now(raw):
    return int(dict(parse_qsl(raw))["auth_date"])


if __name__ == "__main__":
    unittest.main()
