# MINI_APP.md — Telegram Mini App, step 0 (brief, not built)

Status: **direction approved by the owner 2026-11-09 ("go with C"): our own small app, React +
Vite + Telegram UI + Telegram's official script, Python API on the PC. This brief covers step 0
only.** Open questions in §10 need answers before the build starts. Direction and later screens:
`docs/VISION.md` §4, `docs/ROADMAP.md`.

---

## 1. What step 0 delivers

A working, secure, **empty** Mini App:

- A **📱 App** button in Davit's and Karine's chats (the chat menu button) opens the app inside
  Telegram.
- The app knows who opened it: "Signed in as Davit · owner". It checks this on the server against
  Telegram's signature, not by trusting the phone.
- Tabs: **Today · China · Market · Basket · Travel**. Each one shows "Coming soon".
- A status card that reads from the PC: server time in Yerevan, and the PC is reachable.
- It follows Telegram's light/dark theme and back button, and looks like Telegram.
- Anyone who is not Davit or Karine gets "This app is private" and no data.

No real family data is shown in step 0. Step 1 is the China results screen (§9).

## 2. Why our own app (agreed)

Templates were reviewed on 2026-11-09:
- the dev.to React/Next.js article (2022) does no server-side signature check;
- the awesome-telegram-mini-apps list is community-run, and much of it is TON/crypto starters.

Next.js adds a server we don't need. A Mini App only runs inside Telegram, so server rendering
buys nothing. We take the parts that are good:
- Telegram's official `telegram-web-app.js` script;
- the **Telegram UI** component kit, for the native look;
- the Vite boilerplate, read as reference only.

## 3. Shape

```
Telegram chat ── 📱 App (menu button) ──► https://<app-host>/            (public HTTPS)
                                               │  tunnel (§5), no open port on the PC
                                               ▼
                         PC: miniapp server on 127.0.0.1:<port>  (Python, own process)
                              ├─ GET /            → built web app (static files)
                              ├─ GET /api/me      → who you are, role
                              └─ GET /api/status  → server time (Yerevan), version
                         every /api request: Authorization: tma <initData> → checked (§6)
```

- **One origin.** The PC serves the web files and the API through the same tunnel. There is no
  CORS and no public repository. This replaces "GitHub Pages" in VISION §4.
  - **Why:** GitHub Pages needs a public repo, or a paid plan for a private one. The data is on the
    PC anyway, so when the PC is off the app could not show anything.
  - **Trade-off:** when the PC is off, Telegram shows its own "page not available" screen. A static
    "PC is off" page on a public host can come later if this bothers us.
- **Own process, not inside `listener.py`.** The listener stays as it is (frozen platform rule).
  The server is `python -m miniapp.server`. It starts at logon from its own scheduled task,
  `FamilyAssistant-MiniApp`, registered by `scheduler/register-miniapp.ps1`.
- It listens on 127.0.0.1 only. Nothing on the LAN or the internet reaches it except through the
  tunnel.

## 4. Files (planned)

| Path | What |
|---|---|
| `miniapp/__init__.py`, `miniapp/server.py` | stdlib `ThreadingHTTPServer`: static files + JSON API; security headers; no request bodies in step 0 (GET only) |
| `miniapp/auth.py` | initData check (§6): pure functions, no I/O |
| `miniapp/people.py` | who may enter and with which role. Step 0 reads the two existing chat ids. This is the seed for Users and roles. |
| `miniapp/setup_bot.py` | one-off: sets the 📱 App menu button for the allowed chats (`setChatMenuButton`), and clears it with `--remove` |
| `miniapp/web/` | React + Vite + TypeScript app. `package.json` and `package-lock.json` are committed with exact versions. `dist/` is gitignored and built on the PC. |
| `config_miniapp.json` | port, public URL, max initData age, tab list |
| `scheduler/register-miniapp.ps1` | builds the web app (`npm ci && npm run build`), registers the logon task |
| `tests/test_miniapp_auth.py`, `tests/test_miniapp_server.py` | §8 |
| `lib/telegram.py` (own commit, §7) | additive: `web_app` inline buttons |

## 5. Tunnel: public HTTPS without opening the PC

Telegram needs an HTTPS URL that stays the same: the menu button stores it. Quick tunnels with
random URLs that change on every restart don't qualify. There are two ways, and the owner picks one
in §10 Q1:

| | A. Cloudflare Tunnel (named) | B. Tailscale Funnel |
|---|---|---|
| URL | `app.<your-domain>` | `<pc-name>.<tailnet>.ts.net` |
| Needs | a domain on Cloudflare (~$10/year) + free Cloudflare account | free Tailscale account |
| Later | Cloudflare Access, a static "PC is off" page, moves to a server easily | simplest; ties the URL to this PC's name |
| Recommendation | ✅ if you have or will buy a domain | ✅ otherwise |

- Either one runs as a Windows service that `register-miniapp.ps1` checks but does not install. The
  owner installs it once by following a step list in `docs/SECRETS.md`.
- The tunnel credentials are a secret. They go in SECRETS.md, never in Git.
- Check the current terms of both services when building. This table reflects what we know, not a
  re-check made today.

## 6. Security: the part that matters most

The app's URL is public. The data is protected only by checking **Telegram's signature on every
request**, done in `miniapp/auth.py` following Telegram's documented algorithm:

1. The page sends `Telegram.WebApp.initData` (the raw string, never `initDataUnsafe`) in the header
   `Authorization: tma <initData>`.
2. The server parses it as a query string. The request is rejected if any of these hold:
   - `hash` is missing;
   - a key is duplicated;
   - `user` is not valid JSON.
3. Build `data_check_string`: every field except `hash` (and `signature`), written as `key=value`,
   sorted by key, joined by `\n`.
4. `secret_key = HMAC_SHA256(key="WebAppData", msg=bot_token)`; the expected hash is
   `hex(HMAC_SHA256(key=secret_key, msg=data_check_string))`. Compare with
   `hmac.compare_digest`.
5. Reject if `auth_date` is older than `max_age_hours` (config, default 24) or more than 5 minutes
   in the future.
6. Look up `user.id` in `people.py`. An unknown id gets **403 and no data**. The reply never says
   why beyond "private".

Rules:
- The bot token comes from the existing env var. It is never sent to the page.
- initData, hashes and tokens are never logged. Logs keep a masked user id, the path, the status
  and the duration.
- Nothing personal goes in URLs or query strings (`/api/...` takes no personal parameters).
- Response headers:
  - `Cache-Control: no-store` on the API;
  - `X-Content-Type-Options: nosniff`;
  - `Referrer-Policy: no-referrer`;
  - a Content-Security-Policy allowing only our origin plus `telegram.org` for the script;
  - `frame-ancestors` limited to Telegram's web clients.
- Static files are served only from `miniapp/web/dist`. Paths are normalised, and anything that
  resolves outside that folder is a 404.
- Rate limit: 60 requests a minute per user id, then 429. This protects the PC, not the data.
- **Household-ready:** access goes by Telegram **user id plus role**, never by chat id. In private
  chats the user id equals the chat id, so step 0 reads `TELEGRAM_CHAT_ID` (role `owner`) and
  `TELEGRAM_CHAT_ID_2` (role `adult`). Users and roles later replaces `people.py`'s source without
  changing its interface.

## 7. Platform change (its own commit, CLAUDE.md §1)

`lib/telegram.py`: `_button()` accepts a third kind of button, `("📱 Open", {"web_app": url})`,
next to callback data and plain URLs.
- It is additive: existing buttons are unchanged.
- It runs the travel regression check (`docs/REGRESSION.md`).
- It updates the architecture doc in the same commit. That doc is at the repo root as
  `ARCHITECHTURE.MD` (sic). The brief does not rename it.

Step 0 doesn't need the change itself (the menu button is set by `setup_bot.py`). It is scheduled
here so step 1's "📱 Open" buttons under China answers aren't a mid-phase surprise.

## 8. Tests and definition of done

- **`test_miniapp_auth.py`**
  - **Accept:** a valid string signed in the test with a test token.
  - **Reject:** tampered field, wrong hash, missing hash, duplicate key, expired `auth_date`,
    future `auth_date`, unknown user, malformed `user` JSON, empty header.
  - **Real data:** the owner opens the app once in a debug mode that saves his real initData to
    `tmp/` (gitignored). A local-only test checks that it validates against the real token. It is
    skipped when the file is absent and never committed, because it contains a live signature.
- **`test_miniapp_server.py`:**
  - `/api/me` with valid, invalid and absent auth;
  - path traversal (`/../config.json`, encoded variants) is a 404;
  - the security headers are present;
  - unknown user gets 403 with no body data;
  - rate limit gives 429.
- **Web:** `npm run build` and `tsc --noEmit` are clean. No front-end test framework in step 0.
- **Done means:**
  - `pytest` green and `ruff` clean;
  - `selfcheck.py` gains a line: server answering on localhost, public URL reachable, menu button
    set;
  - the phone demo below works for Davit and Karine;
  - DECISIONS entry;
  - docs updated: SECRETS.md (tunnel), TELEGRAM_UX.md (📱 App button), `ARCHITECHTURE.MD`
    (process and tunnel), ROADMAP, and VISION §4 (hosting line).

**Phone demo:**
1. Open the bot chat. **📱 App** sits beside the message field.
2. Tap it. The app opens with "Signed in as Davit · owner" and the five tabs.
3. Switch the phone to dark mode, and the app follows.
4. Tap through the tabs and use the back button.
5. Karine does the same and sees "· adult".
6. Stop the server on the PC and reopen the app. The app shows a clear "PC is not reachable" state,
   and the logon staleness audit (leftover in ROADMAP) is noted for when it covers this process.

## 9. Not in step 0

- Any real data screen. Step 1 is the **China results screen**: one card per result with photo,
  ¥/֏/$ price delivered, seller badge, review summary, and its own 👁 Watch / 💬 Reviews /
  "Open in app" buttons. The China answers in chat gain a "📱 Open" button.
- Editing, POST endpoints, uploads.
- Invites, the People screen, and roles beyond the two seeded users (Users and roles phase).
- Payments, other households, a cloud backend.
- Iframes of store pages (not possible usefully; VISION §4).

## 10. Questions for the owner

1. **Tunnel:** do you have a domain, or will you buy one, for Cloudflare (A)? Or use Tailscale
   Funnel, free with no domain (B)?
2. **Node.js on the PC:** OK to install Node LTS to build the app? It is used only at build time;
   the running server is Python.
3. **Button label:** "📱 App", or another name (e.g. "🏠 Family")?
4. **Who:** Davit = owner, Karine = adult in step 0 (both see everything, as agreed for `/china`).
   Correct?

## 11. Effort

One session: about half on the server, auth and tests, a quarter on the web shell, a quarter on the
tunnel, the scheduled task and docs. The `lib/telegram.py` change is a separate short commit in the
same session. The tunnel's one-time install (§5) needs about 10 minutes of the owner's time.
