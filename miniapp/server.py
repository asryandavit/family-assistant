"""Mini App server (docs/briefs/MINI_APP.md §3, §6): `python -m miniapp.server`.

stdlib ThreadingHTTPServer on 127.0.0.1 only:
    GET  /                  built web app (miniapp/web/dist), nothing outside that folder
    GET  /api/me            who you are: name, role, sections
    GET  /api/status        server time in Yerevan, version
    GET  /api/china         your chat's latest /china result as display JSON (step 1)
    POST /api/china/action  👁 Watch / 💬 Reviews, exactly as the chat buttons (step 1)
    GET  /api/china/status  is a China search running / how many of yours wait (step 2)
    GET  /api/plan/<today|meals|training|week>, /api/market, /api/basket/<weekly|monthly>,
         /api/travel        read-only screens built from what the chat shows (step 2)
    POST /api/run           run a chat command (basket, flights, stays, price, china, scan,
                            digest, watch check) via the listener's inbox (step 2)
    POST /api/market/action, /api/market/add   edit the Market watch list (step 2)
Every /api request carries `Authorization: tma <initData>`, checked by miniapp.auth. The only
request bodies accepted are JSON on POST /api/... up to MAX_BODY bytes.

Never logged: initData, hashes, tokens, full user ids. A log line is masked user id, path
(no query string), status and duration. --capture-initdata saves the first valid initData
from a known person to tmp/ (gitignored) for the local-only real-data test, then stops
capturing.
"""
import argparse
import json
import logging
import os
import posixpath
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from logging.handlers import RotatingFileHandler
from urllib.parse import unquote, urlsplit

from lib.ui import now_local
from miniapp import (
    CAPTURE,
    DIST,
    LOG_DIR,
    __version__,
    actions,
    auth,
    bot_token,
    china_view,
    load_config,
    people,
    screens,
)

log = logging.getLogger("miniapp")

CSP = ("default-src 'self'; script-src 'self' https://telegram.org; "
       "style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; "
       "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; "
       "frame-ancestors https://web.telegram.org")
COMMON_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": CSP,
    "Strict-Transport-Security": "max-age=31536000",
}
MAX_BODY = 1024            # the largest POST body (an action is ~50 bytes)
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
         ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
         ".ico": "image/x-icon", ".json": "application/json", ".woff2": "font/woff2",
         ".webp": "image/webp", ".txt": "text/plain; charset=utf-8"}


class RateLimiter:
    """At most `limit` hits per key in any 60-second window."""

    def __init__(self, limit, window=60.0):
        self.limit, self.window = limit, window
        self.hits = {}
        self.lock = threading.Lock()

    def allow(self, key, now):
        with self.lock:
            q = self.hits.setdefault(key, deque())
            while q and now - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False
            q.append(now)
            return True


def default_china_load(chat_id):
    """The chat's latest /china result (china/search.load_last, kept 24 h) or None."""
    from china import search
    from miniapp import ROOT
    return search.load_last(ROOT, chat_id, 24)


def default_china_action(chat_id, action, job, n):
    """Exactly what a tap on 👁 Watch / 💬 Reviews in the chat does (china/bot.callback).
    Returns the reply text the chat would show (HTML)."""
    from china import bot as cbot
    from lib import config
    from miniapp import ROOT
    return cbot.callback(config.load(), ROOT, f"cn:{action}:{job}:{n}", chat_id)


class Services:
    """The real work behind the step 2 screens and forms; tests pass a fake with the same
    methods. Everything takes the asking person's chat id (private chat: the user id)."""

    def __init__(self):
        from lib import config
        from miniapp import ROOT
        self.root, self.cfg = ROOT, config.load()

    def plan_page(self, chat_id, name):
        return screens.plan_page(self.root, name, chat_id)

    def market_view(self):
        return screens.market_view(self.root)

    def basket_view(self, kind):
        return screens.basket_view(self.root, kind)

    def travel_view(self):
        return screens.travel_view(self.cfg, self.root)

    def run(self, chat_id, job, args):
        return actions.run(self.root, self.cfg, chat_id, job, args)

    def china_status(self, chat_id):
        return actions.china_status(self.root, chat_id)

    def china_cancel(self, chat_id):
        return actions.china_cancel(self.root, chat_id)

    def market_action(self, chat_id, action, item_id):
        return actions.market_action(self.cfg, self.root, chat_id, action, item_id)

    def market_add(self, chat_id, name, link, weight):
        return actions.market_add(self.cfg, self.root, chat_id, name, link, weight)


class App:
    """Everything a request needs; built once, shared read-only by the handler threads."""

    def __init__(self, cfg, token, persons, dist=DIST, clock=time.time, capture_path=None,
                 china_load=default_china_load, china_action=default_china_action, svc=None):
        self.cfg = cfg
        self.token = token
        self.people = persons
        self.dist = os.path.realpath(dist)
        self.clock = clock
        self.max_age_s = int(cfg.get("max_age_hours", 24)) * 3600
        self.limiter = RateLimiter(int(cfg.get("rate_limit_per_min", 60)))
        self.capture_path = capture_path
        self.capture_lock = threading.Lock()
        self.china_load = china_load
        self.china_action = china_action
        self._svc = svc
        self.run_limiter = RateLimiter(int(cfg.get("run_limit_per_min", 10)))

    @property
    def svc(self):
        if self._svc is None:                       # built on first use, so the static files
            self._svc = Services()                  # and GET-only tests never load the config
        return self._svc

    # ---- API
    def api(self, path, auth_header, method="GET", ctype="", body=b""):
        """(status, body dict, masked user) for an /api request. Order for every request:
        signature -> rate limit (per user) -> known person -> route -> module permission."""
        try:
            raw = auth.init_data_from_header(auth_header)
            checked = auth.check(raw, self.token, int(self.clock()), self.max_age_s)
        except auth.AuthError as e:
            log.info("auth rejected: %s", e.reason)
            if not self.limiter.allow("unauthenticated", self.clock()):
                return 429, {"error": "slow down"}, "-"
            if e.reason == "expired":
                # the signature was Telegram's, the session is just old: the page may say
                # "close and reopen" instead of "private" (decision 099). Still no data.
                return 401, {"error": "expired"}, "-"
            return 401, {"error": "unauthorized"}, "-"
        uid = checked["user"]["id"]
        who = people.mask(uid)
        if not self.limiter.allow(uid, self.clock()):
            return 429, {"error": "slow down"}, who
        person = people.lookup(self.people, uid)
        if person is None:
            return 403, {"error": "private"}, who
        self._maybe_capture(raw)
        route = ROUTES.get((method, path))
        if route is None:
            known = any(p == path for _, p in ROUTES)
            return (405, {"error": "method not allowed"}, who) if known else \
                   (404, {"error": "not found"}, who)
        module, fn = route
        if module and not people.can(person, module):
            return 403, {"error": "not allowed"}, who
        status, out = fn(self, person, ctype, body)
        return status, out, who

    def me(self, person, _ctype, _body):
        return 200, {"name": person.name, "role": person.role,
                     "tabs": list(self.cfg.get("tabs", []))}

    def status(self, _person, _ctype, _body):
        now = now_local()
        return 200, {"ok": True, "time_local": now.strftime("%Y-%m-%d %H:%M"),
                     "tz": "Asia/Yerevan", "version": __version__}

    def china(self, person, _ctype, _body):
        # in a private chat the chat id is the user id: a person only ever sees their own chat
        return 200, china_view.view(self.china_load(str(person.user_id)))

    def china_post(self, person, ctype, body):
        """{"action": "watch"|"reviews", "job": "<8 hex>", "n": 1..99} -> the chat's reply."""
        if ctype.split(";")[0].strip().lower() != "application/json":
            return 415, {"error": "send JSON"}
        try:
            d = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return 400, {"error": "bad JSON"}
        if not isinstance(d, dict) or set(d) != {"action", "job", "n"}:
            return 400, {"error": "expected action, job, n"}
        action, job, n = d["action"], d["job"], d["n"]
        if (action not in ("watch", "reviews") or not isinstance(job, str)
                or not china_view.JOB_RE.match(job) or not isinstance(n, int)
                or isinstance(n, bool) or not 1 <= n <= 99):
            return 400, {"error": "bad action, job or n"}
        reply = self.china_action(str(person.user_id), "watch" if action == "watch" else "rev",
                                  job, n)
        text = "\n".join(china_view.plain(str(reply or "").replace("\n", "<br>")))
        ok = text.startswith(("👁 Added", "👁 Already", "⏳"))
        log.info("china %s %s #%d -> %s", action, job, n, "ok" if ok else "refused")
        return 200, {"ok": ok, "message": text}

    # ---- step 2: screens and forms
    @staticmethod
    def _body(ctype, body, required, optional=()):
        """Parse a JSON object body whose keys are `required` plus some of `optional`, every
        value a short string. -> (dict, None) or (None, (status, error))."""
        if ctype.split(";")[0].strip().lower() != "application/json":
            return None, (415, {"error": "send JSON"})
        try:
            d = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            return None, (400, {"error": "bad JSON"})
        if (not isinstance(d, dict) or not set(required) <= set(d)
                or not set(d) <= set(required) | set(optional)
                or not all(isinstance(v, str) and len(v) <= 300 for v in d.values())):
            return None, (400, {"error": "bad request"})
        return d, None

    def plan(self, person, name):
        page = self.svc.plan_page(str(person.user_id), name)
        return 200, ({"unreadable": True} if page is None else page)

    def market(self, _person, _ctype, _body):
        return 200, self.svc.market_view()

    def basket(self, _person, kind):
        v = self.svc.basket_view(kind)
        return (200, v) if v is not None else (404, {"error": "not found"})

    def travel(self, _person, _ctype, _body):
        return 200, self.svc.travel_view()

    def china_status(self, person, _ctype, _body):
        return 200, self.svc.china_status(str(person.user_id))

    def china_cancel_post(self, person, ctype, body):
        """POST {} : drop the signed person's waiting China searches (the body carries nothing:
        whose chat is decided by the signature)."""
        _, err = self._body(ctype, body, ())
        if err:
            return err
        ok, msg = self.svc.china_cancel(str(person.user_id))
        log.info("china cancel -> %s", "removed" if ok else "nothing")
        return 200, {"ok": ok, "message": msg}

    def run_post(self, person, ctype, body):
        d, err = self._body(ctype, body, ("job",), ("args",))
        if err:
            return err
        if d["job"] not in actions.JOBS:
            return 400, {"error": "unknown action"}
        if not self.run_limiter.allow(person.user_id, self.clock()):
            return 429, {"error": "slow down"}
        ok, msg = self.svc.run(str(person.user_id), d["job"], d.get("args", ""))
        log.info("run %s -> %s", d["job"], "queued" if ok else "refused")
        return 200, {"ok": ok, "message": msg}

    def market_action_post(self, person, ctype, body):
        d, err = self._body(ctype, body, ("action", "id"))
        if err:
            return err
        if d["action"] not in ("bought", "remove") or not actions.ID_RE.match(d["id"]):
            return 400, {"error": "bad action or id"}
        ok, msg = self.svc.market_action(str(person.user_id), d["action"], d["id"])
        log.info("market %s -> %s", d["action"], "ok" if ok else "refused")
        return 200, {"ok": ok, "message": msg}

    def market_add_post(self, person, ctype, body):
        d, err = self._body(ctype, body, ("name", "link"), ("weight",))
        if err:
            return err
        ok, msg = self.svc.market_add(str(person.user_id), d["name"], d["link"],
                                      d.get("weight", ""))
        log.info("market add -> %s", "ok" if ok else "refused")
        return 200, {"ok": ok, "message": msg}

    def _maybe_capture(self, raw):
        if not self.capture_path:
            return
        with self.capture_lock:
            if self.capture_path and not os.path.exists(self.capture_path):
                os.makedirs(os.path.dirname(self.capture_path), exist_ok=True)
                with open(self.capture_path, "w", encoding="utf-8") as f:
                    f.write(raw)
                log.info("captured one initData to tmp/ (local test only); capture off")
            self.capture_path = None

    # ---- static files
    def static_file(self, url_path):
        """Absolute file path inside dist for a URL path, or None (-> 404)."""
        p = unquote(url_path, errors="strict")
        if "\x00" in p or "\\" in p:
            return None
        p = posixpath.normpath("/" + p.lstrip("/"))
        if p == "/":
            p = "/index.html"
        parts = [s for s in p.split("/") if s]
        if any(s in (".", "..") or ":" in s for s in parts):
            return None
        full = os.path.realpath(os.path.join(self.dist, *parts))
        if os.path.commonpath([full, self.dist]) != self.dist or not os.path.isfile(full):
            return None
        return full


ROUTES = {
    ("GET", "/api/me"): (None, App.me),
    ("GET", "/api/status"): (None, App.status),
    ("GET", "/api/china"): ("china", App.china),
    ("POST", "/api/china/action"): ("china", App.china_post),
    ("GET", "/api/china/status"): ("china", App.china_status),
    ("POST", "/api/china/cancel"): ("china", App.china_cancel_post),
    ("GET", "/api/market"): ("market", App.market),
    ("POST", "/api/market/action"): ("market", App.market_action_post),
    ("POST", "/api/market/add"): ("market", App.market_add_post),
    ("GET", "/api/travel"): ("travel", App.travel),
    ("POST", "/api/run"): ("run", App.run_post),
}
for _n in screens.PLAN_NAMES:
    ROUTES[("GET", f"/api/plan/{_n}")] = ("plan", lambda a, p, _c, _b, n=_n: a.plan(p, n))
for _k in ("weekly", "monthly"):
    ROUTES[("GET", f"/api/basket/{_k}")] = ("basket", lambda a, p, _c, _b, k=_k: a.basket(p, k))


class Handler(BaseHTTPRequestHandler):
    server_version = "miniapp"
    protocol_version = "HTTP/1.1"
    timeout = 20

    @property
    def app(self):
        return self.server.app

    def version_string(self):        # no Python version in the Server header
        return self.server_version

    def log_message(self, fmt, *args):   # silence the default stderr access log
        pass

    def _send(self, status, body, ctype, extra=None):
        self.send_response(status)
        for k, v in COMMON_HEADERS.items():
            self.send_header(k, v)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _has_body(self):
        """True when the request announces a body (any Transfer-Encoding, or a Content-Length
        that is not zero)."""
        return bool(self.headers.get("Transfer-Encoding")
                    or (self.headers.get("Content-Length") or "0").strip() != "0")

    def _json(self, status, obj):
        self._send(status, json.dumps(obj).encode(), "application/json",
                   {"Cache-Control": "no-store"})

    def do_GET(self):
        t0 = time.monotonic()
        who, status = "-", 500
        try:
            path = urlsplit(self.path).path
            if self._has_body():
                # A GET has no body here. Unread, it would stay in the socket and be run as
                # the next request on this connection (request smuggling: the tunnel reuses one
                # connection for several clients). Refuse and close (decision 099).
                status = 400
                self.close_connection = True
                self._json(400, {"error": "no body on GET"})
            elif path.startswith("/api/") or path == "/api":
                status, body, who = self.app.api(path, self.headers.get("Authorization"))
                self._json(status, body)
            else:
                try:
                    full = self.app.static_file(path)
                except UnicodeDecodeError:
                    full = None
                if full is None:
                    status = 404
                    self._send(404, b"Not found", "text/plain; charset=utf-8",
                               {"Cache-Control": "no-store"})
                else:
                    status = 200
                    with open(full, "rb") as f:
                        data = f.read()
                    ext = os.path.splitext(full)[1].lower()
                    hashed = "/assets/" in full.replace("\\", "/")
                    cache = ("public, max-age=31536000, immutable" if hashed else "no-cache")
                    self._send(200, data, TYPES.get(ext, "application/octet-stream"),
                               {"Cache-Control": cache})
        except Exception as e:  # noqa: BLE001  any failure -> 500, never a trace to the page
            log.error("error on %s: %s", urlsplit(self.path).path, type(e).__name__)
            status = 500
            try:
                self._json(500, {"error": "server error"})
            except OSError:
                pass
        finally:
            log.info("%s %s %d %dms", who, urlsplit(self.path).path, status,
                     (time.monotonic() - t0) * 1000)

    def do_POST(self):
        t0 = time.monotonic()
        who, status = "-", 500
        path = urlsplit(self.path).path
        try:
            if not path.startswith("/api/"):
                status = 405
                self._not_allowed(log_it=False)
                return
            try:
                length = int(self.headers.get("Content-Length") or "-1")
            except ValueError:
                length = -1
            if length < 0 or length > MAX_BODY or self.headers.get("Transfer-Encoding"):
                status = 413 if length > MAX_BODY else 411
                self.close_connection = True      # an unread body would corrupt the next request
                self._json(status, {"error": "body too large" if status == 413 else
                                    "length required"})
                return
            try:
                body = self.rfile.read(length)
            except OSError:                       # timeout: the announced body never arrived
                body = b""
            if len(body) < length:
                status = 408
                self.close_connection = True      # the socket is out of step: never reuse it
                self._json(408, {"error": "body not received"})
                return
            status, out, who = self.app.api(path, self.headers.get("Authorization"), "POST",
                                            self.headers.get("Content-Type") or "", body)
            self._json(status, out)
        except Exception as e:  # noqa: BLE001  any failure -> 500, never a trace to the page
            log.error("error on POST %s: %s", path, type(e).__name__)
            status = 500
            try:
                self._json(500, {"error": "server error"})
            except OSError:
                pass
        finally:
            log.info("%s POST %s %d %dms", who, path, status, (time.monotonic() - t0) * 1000)

    def _not_allowed(self, log_it=True):
        self.close_connection = True
        self._send(405, b"Method not allowed", "text/plain; charset=utf-8",
                   {"Allow": "GET, POST", "Cache-Control": "no-store"})
        if log_it:
            log.info("- %s %s 405", self.command, urlsplit(self.path).path)

    do_PUT = do_DELETE = do_PATCH = do_OPTIONS = do_HEAD = _not_allowed


class Server(ThreadingHTTPServer):
    """One thread per connection, but at most `max_connections` (config, default 32) at once:
    over the cap a connection gets a quick 503 and is closed (decision 102). Idle keep-alive
    connections count until Handler.timeout (20 s) closes them."""
    daemon_threads = True

    def __init__(self, addr, app):
        super().__init__(addr, Handler)
        self.app = app
        self.max_connections = int(app.cfg.get("max_connections", 32))
        self._slots = threading.BoundedSemaphore(self.max_connections)

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            self._refuse(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()

    def _refuse(self, request):
        """503 without a thread. A short read first, so the client's request is not left unread
        (closing on unread bytes can reset the connection and lose the answer)."""
        try:
            request.settimeout(0.05)
            try:
                request.recv(4096)
            except OSError:
                pass
            request.sendall(b"HTTP/1.1 503 Service Unavailable\r\nRetry-After: 2\r\n"
                            b"Connection: close\r\nContent-Length: 0\r\n\r\n")
        except OSError:
            pass
        finally:
            self.shutdown_request(request)


def setup_logging():
    os.makedirs(LOG_DIR, exist_ok=True)
    h = RotatingFileHandler(os.path.join(LOG_DIR, "miniapp.log"), maxBytes=1_000_000,
                            backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(h)
    if sys.stdout is not None:          # None under pythonw.exe (the scheduled task)
        log.addHandler(logging.StreamHandler(sys.stdout))
    log.setLevel(logging.INFO)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Mini App server (127.0.0.1 only)")
    ap.add_argument("--capture-initdata", action="store_true",
                    help="save the first valid initData to tmp/ for the local real-data test")
    args = ap.parse_args(argv)
    setup_logging()
    cfg = load_config()
    token = bot_token()
    if not token:
        log.error("bot token env var not set (docs/SECRETS.md #1); not starting")
        return 2
    persons = people.load(cfg)
    if not persons:
        log.error("no people configured (TELEGRAM_CHAT_ID unset?); not starting")
        return 2
    if not os.path.isfile(os.path.join(DIST, "index.html")):
        log.warning("miniapp/web/dist is not built; the API works, the page will 404 "
                    "(run scheduler/register-miniapp.ps1 or npm run build)")
    app = App(cfg, token, persons, capture_path=CAPTURE if args.capture_initdata else None)
    try:
        srv = Server(("127.0.0.1", int(cfg["port"])), app)
    except OSError as e:
        log.error("cannot listen on 127.0.0.1:%s: %s", cfg["port"], e.strerror or e)
        return 3
    log.info("miniapp %s on http://127.0.0.1:%s (%d people)%s", __version__, cfg["port"],
             len(persons), " — capturing one initData" if args.capture_initdata else "")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
