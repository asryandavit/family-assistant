# MINI_APP.md — Telegram Mini App, steps 0 and 1 (built)

Status: **step 0 done 2026-11-10 (decisions 094, 096) — owner demo passed: owner and adult, dark mode, Home list,
back button, PC-not-reachable. Step 1 (China results, §12) built 2026-11-10 (decision 097), phone demo next.**
Direction approved by the owner 2026-11-09 ("go with C"): our own small app, React + Vite + Telegram UI + Telegram's
official script, Python API on the PC. Navigation became a Home list instead of the tabs in §1
(decision 096). Direction and later screens:
`docs/VISION.md` §4, `docs/ROADMAP.md`.

---

## 1. What step 0 delivers

A working, secure, **empty** Mini App:

- A **🏠 Family** button in Davit's and Karine's chats (the chat menu button) opens the app inside
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
Telegram chat ── 🏠 Family (menu button) ──► https://<app-host>/            (public HTTPS)
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
| `miniapp/setup_bot.py` | one-off: sets the 🏠 Family menu button for the allowed chats (`setChatMenuButton`), and clears it with `--remove` |
| `miniapp/web/` | React + Vite + TypeScript app. `package.json` and `package-lock.json` are committed with exact versions. `dist/` is gitignored and built on the PC. |
| `config_miniapp.json` | port, public URL, max initData age, tab list |
| `scheduler/register-miniapp.ps1` | builds the web app with the PC's Windows Node (`npm ci && npm run build`), registers the logon task |
| `tests/test_miniapp_auth.py`, `tests/test_miniapp_server.py` | §8 |
| `lib/telegram.py` (own commit, §7) | additive: `web_app` inline buttons |

## 5. Tunnel: public HTTPS without opening the PC

Telegram needs an HTTPS URL that stays the same: the menu button stores it. Quick tunnels with
random URLs that change on every restart don't qualify. **Chosen: B, Tailscale Funnel** (owner,
2026-11-10). Tailscale is installed and running on the PC; Funnel is not configured yet. The
options as compared:

| | A. Cloudflare Tunnel (named) | B. Tailscale Funnel |
|---|---|---|
| URL | `app.<your-domain>` | `<pc-name>.<tailnet>.ts.net` |
| Needs | a domain on Cloudflare (~$10/year) + free Cloudflare account | free Tailscale account |
| Later | Cloudflare Access, a static "PC is off" page, moves to a server easily | simplest; ties the URL to this PC's name |
| Recommendation | ✅ if you have or will buy a domain | ✅ otherwise |

- Tailscale already runs as a Windows service. Setup, once, by the owner, following a step list
  in `docs/SECRETS.md`:
  1. In the Tailscale admin console, enable HTTPS certificates and allow Funnel for this device
     (the `funnel` node attribute in the tailnet policy).
  2. Run `tailscale funnel --bg <port>`. This publishes `https://<pc-name>.<tailnet>.ts.net/` on
     port 443 and forwards it to `127.0.0.1:<port>`.
- `register-miniapp.ps1` checks `tailscale funnel status` and does not change it.
- The public hostname is machine-specific. It lives in `machine.json` (`miniapp_public_url`), not
  in Git.
- Funnel hostnames show up in public certificate logs. That reveals the PC and tailnet name, not
  any data. Every request is still checked as in §6.
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
- **Request framing (decision 099).** A request must leave nothing unread in its connection:
  the tunnel reuses one connection to the server for several clients, so leftover bytes would
  be run as somebody's next request. A GET that announces a body (`Content-Length` above 0 or
  any `Transfer-Encoding`) is a 400 and the connection is closed. A POST whose announced body
  does not arrive within the 20 s socket timeout is a 408, the connection is closed and
  nothing runs.
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
  - docs updated: SECRETS.md (tunnel), TELEGRAM_UX.md (🏠 Family button), `ARCHITECHTURE.MD`
    (process and tunnel), ROADMAP, and VISION §4 (hosting line).

**Phone demo:**
1. Open the bot chat. **🏠 Family** sits beside the message field.
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

## 10. Owner answers (2026-11-10)

1. **Tunnel:** Tailscale Funnel (B). Tailscale is installed and running; Funnel still needs the
   one-time setup in §5.
2. **Node.js:** the owner offered WSL. The PC already has **Windows Node 24** (via nvm4w), and WSL
   Ubuntu also has Node 22/24 (nvm). **Windows Node is used.** It builds on the same filesystem
   the server reads, with no `/mnt/d` slowdown and no Linux-only native packages in
   `node_modules`. WSL stays a fallback. Either way Node is used at build time only.
3. **Button label:** "🏠 Family".
4. **Who:** Davit = owner, Karine = adult; both see everything.

## 11. Effort

One session: about half on the server, auth and tests, a quarter on the web shell, a quarter on the
tunnel, the scheduled task and docs. The `lib/telegram.py` change is a separate short commit in the
same session. The tunnel's one-time install (§5) needs about 10 minutes of the owner's time.

---

## 12. Step 1 — China results screen (owner: "go next and implement all together", 2026-11-10)

Step 0 is done (owner demo 2026-11-10: owner and adult, dark mode, Home list, PC-not-reachable).
Step 1 follows in the same session at the owner's request.

**What it shows.** 🏠 Family → China (or the new **📱 Open in app** button under every `/china`
answer) opens the asking person's latest `/china` result (`last_<chat>.json`, kept 24 h):
query, when, each site's status, then one card per result in the chat's order and numbering —
🏆 pick marked, title, site, seller class, 🛡 trust, price (¥ → AMD · $), delivered total and
route, warnings (promo, suspiciously cheap, PDD listing price, no weight), and a fold with
every route, weight, trust parts, specs, reviews read, restrictions and the model's "why".
Buttons per card: **Open on <site>** (Telegram opens the link; on a phone the store app takes
it), **👁 Watch**, **💬 Reviews** (when not read yet).

**Numbers are code.** The server turns the saved result into display JSON with the same
`china/report.py` helpers the chat uses (HTML stripped), and the 🏆 pick with
`china/pricing.best_pick`. The page does no arithmetic.

**Actions reuse the chat buttons.** `POST /api/china/action {"action": "watch"|"reviews",
"job", "n"}` calls `china.bot.callback` exactly as a tap on 👁 / 💬 in the chat does: Watch
adds to Market watch now; Reviews queues the Chrome job and the answer arrives in the chat. First
POST endpoint: JSON only, ≤ 1 KB, job id and number validated, same auth, rate limit and 403
as the GETs, plus a per-module permission (`people.can(person, "china")`: owner and adult).
Market watch writes get a cross-process lock (`market/state.items_lock`), because the Mini App
server becomes a second writer next to the listener.

**Found while preparing (captured, not guessed):**
- Saved results carry **no product photos**: the pipeline rejects URLs from the model by design
  (decision 090) and rebuilds links from ids. Photos need a change to the China extraction
  (image ids per site, built into CDN URLs in code) — a China-session follow-up, not this step.
- A `web_app` button **inside a Rich Message** works: `<tg-button type="web_app" url="…">`
  was accepted on 2026-11-10 and came back as `{"web_app": {"url": …}}`
  (`tests/fixtures/miniapp/rich_web_app_button.json`).

**Deep link.** `https://<app>/?screen=china` opens straight on China; Telegram's back button
returns Home. The query holds no personal data.

**Not in step 1:** photos (above), sort and filters, editing a watched item, other screens.

**Done means:** tests for the view (real result fixture, product data only), the endpoints
(auth, 403, permission, body limits, bad input, only your own chat's result), the lock and the
report button; `tsc` + build clean; owner opens a real `/china` result from the 📱 button and
from Home, taps Open, 👁 Watch and 💬 Reviews.
