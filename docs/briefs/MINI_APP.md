# MINI_APP.md — Telegram Mini App, steps 0 and 1 (built)

Status: **step 0 done 2026-11-10 (decisions 094, 096) — owner demo passed: owner and adult, dark mode, Home list,
back button, PC-not-reachable. Step 1 (China results, §12) built 2026-11-10 (decision 097), phone demo next.
Reviewed 2026-11-10 (decision 099): fixes in §6 and §14.1, proposals for the owner in §14–§15.**
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
   in the future. A too-old `auth_date` on a string whose signature is valid answers
   `401 {"error": "expired"}` and the page says "Session expired — close and reopen"
   (decision 099); every other failure stays `401 unauthorized` with no reason.
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

---

## 13. Step 2 — every section a real screen (owner, 2026-11-10: "start and finish all job together")

Built the same day (decision 098). Home → each row opens a screen that shows what the chat shows and
offers the chat's own actions:

| Screen | Shows | Does |
|---|---|---|
| **Today** | Today · Meals · Training · Week tabs (`coach/plan_text`, for the asking person) | read-only |
| **China** | search form (All / PDD / Taobao / 1688) above the latest results (step 1) | `/china …` via the listener; polls the queue and loads the new results |
| **Market** | watch list, best price to Yerevan per item | ✅ Bought · 🗑 Remove · add by store link · 🔄 Check prices now |
| **Basket** | last priced list by shop, totals, cheaper-shop comparison | 🧺 price it again (`/basket`), Price check (`/price`) |
| **Travel** | scan status, cheapest trips, best stays (Sheet, cached 5 min) | Scan now, Send digest, Search flights, Search stays |

**Rule: the Mini App server never starts a job.** `POST /api/run {"job", "args"}` composes a chat
command, validates it with the chat's own parsers (so the form shows the chat's error sentence) and
queues it in `.browser/miniapp_inbox/`; `listener.inbox_loop` runs it through `handle_text` from the
person's chat, so the one-job-at-a-time runner, the validation and the reply are exactly the chat's.
The answer to a run arrives **in the chat**; the app says so. Market edits are direct (same
`market.bot._mutate` and write lock as `/watch`, by item id).

**Limits, honestly:** no photo search in the app (a Mini App cannot give the bot a photo); no
editing of a watched item beyond bought/remove (weights and links: `/watch`); the app cannot see
whether a run it queued has finished except for China (queue status); Basket items are not ticked
off here (the Google checklist is the tick-off list).

**Done means:** tests for blocks, views (real fixtures), composition accept/reject, market add /
bought / remove on a temp dir, endpoints (auth, 403, permission, validation, limits), inbox and
listener thread; `tsc` + build clean; owner phone demo: each screen opens, a China search from the
form runs and its results appear, Basket / Travel / Market buttons answer in the chat.

---

## 14. Review, 2026-11-10 — findings and proposals (for the owner to decide)

An independent review of steps 0 and 1 the day they were built (decision 099). Method: the full
test suite; `tsc` and the build; an attacker's probes over raw sockets against a throwaway server
with a test token; the lock under three processes; the page in a phone-sized browser with a
test-signed initData and the real result fixture. The real token, the real chats and the live
server were not touched.

**Verdict.** The design is right for a family of two and the security core is sound: the
signature check follows Telegram's algorithm; duplicate keys, a second `hash`, a string `id`, a
missing `user`, 24 h 01 min of age and 6 minutes into the future are all refused; an unknown person
gets 403 and nothing else; a person only ever reads their own chat's China result; the token never
reaches the page; the tunnel hostname and the chat ids are not in Git or its history; path
traversal on Windows (device names, `::$DATA`, encoded dots, backslashes) is a 404; the page
computes nothing. What was wrong was at the edges that are hand-built: HTTP framing and the lock
file.

### 14.1 Fixed in this review (each its own commit, each with a test that failed first)

| Severity | Finding | Fix |
|---|---|---|
| must | A GET's body ran as a second request on the same connection (request-smuggling primitive behind the tunnel's shared connection) | 400 and close |
| must | The lock crashed with `PermissionError` on Windows when three writers re-took it (2 runs of 6) | retry; 0 of 6 |
| should | The nightly job wrote the list without the lock (two windows) | both under the lock; busy = a line in the report |
| should | A slow holder removed the next holder's lock file | removes only its own (token) |
| should | A POST whose body never arrives: 500 after 20 s and a traceback | 408 and close |
| should | A window open for more than 24 h said "This app is private" to the owner | "Session expired" + Close |
| should | 👁 Watch twice added the product twice | "Already on Market watch" |
| nice | The China card showed the listing price large and the delivered total small | delivered total first |

### 14.2 Found and left (small; say the word)

- **The Mini App server starts the China worker as its own child** (💬 Reviews →
  `china/queue.start_worker`). Stopping the `FamilyAssistant-MiniApp` task while a reviews job
  runs probably stops that job (not tested — it needs a real Chrome job). Recommendation: send
  Reviews through the listener's inbox (decision 098) like the other commands.
- **ok / refused is read from the reply's first words** (`👁 Added`, `👁 Already`, `⏳`). A
  reworded chat message silently turns a success red. Recommendation: `china.bot` returns
  `(ok, text)` to the server.
- **One thread per connection, no cap.** 200 idle sockets held 200 threads for 20 s in the test.
  The tunnel's proxy only opens a connection for a complete request header, so the internet
  cannot do this directly; a cap (a semaphore of about 32) costs ten lines.
- **`market/bot._mutate` holds the lock across the Google Sheet read and writes the Sheet after
  releasing it.** Two edits within a second or two can let a stale Sheet row undo the other. Not
  live while `watch_sheet_id` is unset. A lock file cannot close this (§14.3, SQLite).
- **PC clock.** If the PC's clock is more than 5 minutes slow, every fresh sign-in is "in the
  future" and refused for everyone. `selfcheck.py` could compare the clock with the `Date` header
  of Telegram's API.
- **The logon staleness audit does not cover this process yet** (§8 leftover, unchanged).
- **No front-end test.** The method used here (a test-signed initData in the URL hash against a
  server with a test token) makes a 30-line Playwright smoke test possible: Home, deep link,
  Details, an ok and a refused action, dark mode.
- **`Pick` does not jump to its card.**

### 14.3 Architecture — is this the right way?

For today, yes. For a household product, four things change, and all four belong to **Users and
roles (ROADMAP #4)**, not to now. Doing them earlier would be building for users who do not exist.

| Point | Risk now | Recommendation | Cost | When |
|---|---|---|---|---|
| **stdlib server → a small framework** (Starlette or FastAPI on uvicorn) | We own the HTTP details: two framing bugs in one day, body limits, timeouts, threads, routing by hand. Each new POST adds hand-written validation. | Keep stdlib while there are a handful of routes. Move when sessions and the People screen arrive: typed request models replace hand validation, and the framing is somebody else's tested code. `auth.py`, `people.py`, `china_view.py` are pure and move unchanged. | 1 session | Users and roles |
| **JSON files + lock file → SQLite** | Three lock defects found in one review (crash, unlocked writer, wrong release) plus the Sheet window in §14.2. Every new shared file needs the same care again. | Put people, sessions, the watch list and the action log (§15) in SQLite with the CLAUDE.md §3 helper (`BEGIN IMMEDIATE`, WAL, one connection per thread). The Sheet becomes a view written from the database, not a second master. | 1–2 sessions, with a migration and a restore drill | Users and roles (the list can move first) |
| **initData on every request → a session** | initData is a 24 h bearer string: whoever copies it has the person for a day, and removing a person does not take effect until it expires. Acceptable for two adults on their own phones. | Exchange initData once (accepted for about 1 h) for a random session id kept hashed in SQLite, 30 minutes sliding, deleted when the owner removes the person. The HMAC check stays as the way in. | half a session, after SQLite | Users and roles |
| **Tailscale Funnel → a named Cloudflare Tunnel on our own domain** | Works. But: the URL is this PC's name; PC off = Telegram's blank error page; no rate limiting before the PC; the hostname is in public certificate logs. | Stay on Funnel for the family. With the first outside family (or when the blank page annoys): own domain (about $10/year), a static "PC is off" page, edge rate limits. The same step later moves the backend off the PC without changing the URL. | 1–2 hours + the domain | first beta family, or on request |
| **React + Telegram UI → plain HTML?** | None worth acting on: 57 KB gzipped, native look, typed. The cost is upkeep of npm dependencies. | Keep. Versions are pinned; run `npm audit` monthly; add the smoke test from §14.2. Plain HTML would save little and lose the Telegram look. | — | — |

Two things in the current design are better than the usual alternatives and should survive any
move: **one origin** (no CORS, no public repo, a strict CSP) and **the app calls the chat's own
code** (same numbers, same validation). Decision 098's inbox — the app asks, the listener runs an
allow-listed command — is the right seed for §15.

### 14.4 The China screen — how it could be better

1. **Photos without breaking decision 090.** The model still never supplies a URL. The extraction
   keeps each site's image *id* next to the item id; code builds the CDN URL from the id (as it
   already builds links); the PC downloads a small thumbnail once into `.browser/` and serves it
   from our own origin. The CSP stays `img-src 'self'`, the phone never contacts a Chinese CDN,
   and a wrong id shows a placeholder, not somebody else's picture. A China-session change first.
2. **Sort without arithmetic on the page.** The server sends the orders ready-made —
   `orders: {"trust": [5,1,…], "delivered": […], "fastest": […]}` — and the page only re-orders
   cards. Same for filters: per-card flags (`site`, `reviews_read`, `has_warning`).
3. **Layout.** Ten cards are 5,954 px on a phone (measured), about seven screens. Proposal: a
   compact card (photo left; delivered total; trust as a coloured chip; two buttons) about 150 px
   high, opening to today's full card; the 🏆 pick pinned as the first card; the three site lines
   folded into one ("Pinduoduo 5 · Taobao link · 1688 5").
4. **Live state from the PC, not from the page's memory.** `watching: true` when the product is
   already on the list (the server can tell since this review); "reviews being read…" from the
   queue, and the card refreshes itself when they arrive.
5. **History.** Keep the last few searches (not only the last, 24 h), and "search again".

---

## 15. Where this can go — a proposal for the far goal (5–10 years)

The owner asked how far this can go, whether it can place and finish orders, and whether Telegram
should stay. This is a proposal to react to, not a plan.

**The goal in one sentence.** *A household agent that prepares, asks, and then carries out — the
family decides, the agent does the work, and nothing is ever spent or sent without a rule or a tap
that allowed it.*

### 15.1 The ladder — from "tells us" to "does it for us"

| Level | What it does | Example | Where we are |
|---|---|---|---|
| 0 Inform | reports, alerts | price dropped; tonight's menu | built |
| 1 Prepare | does everything up to the last step | the week's basket as a filled cart; a China order sheet for the forwarder | partly (basket links) |
| 2 Act on a tap | carries out one action after one explicit approval in the app | "Order this — 18,400 AMD — Approve" | not yet |
| 3 Standing rules | acts inside limits the family set | "re-order the weekly basket up to 40,000 AMD"; "book if the fare is under €90" | not yet |
| 4 Trusted routine | handles low-risk routine alone, reports after | restock, renewals, reminders | far |

Each level needs the one below it to have been boring for months.

### 15.2 What has to exist before the agent may act (levels 2–3)

- **An action ledger** (SQLite): every action as a row — who asked, who approved, exactly what
  was sent, the result, the cost — with an idempotency key so nothing runs twice, a dry-run mode
  and, where the store allows, an undo window. This is CLAUDE.md §5 ("every decision carries a
  reason") applied to deeds.
- **Limits in code, not in a prompt:** per person, per module, per month; a second adult's
  approval above a threshold. "Numbers are code, words are AI" becomes "**money is code plus a
  person; the AI proposes**".
- **Every capability is a named, validated command** — the inbox allow-list of decision 098 grown
  into a tool list. The model chooses from the list; it never drives a browser freely with a
  wallet attached.
- **Payment is never typed by the agent.** In order of preference: the store's own checkout
  opened with a filled cart (the person pays there); an official or partner API; a virtual card
  with its own limit when a bank offers one.

### 15.3 Honest limits

- None of today's stores (Yerevan City, Parma, Taobao, Pinduoduo, 1688, Amazon) offers private
  people an ordering API. Finishing a checkout by driving the owner's logged-in browser is
  possible for this household, breaks when a page changes, may be against the store's terms, and
  cannot be offered to other families. So: **level 1 everywhere within a year is realistic; level
  2 first where a partner exists** (a forwarder, one grocery chain, flights through an affiliate
  API); **level 3 for our own household where the store is stable**.
- One Windows PC is the single point of failure. Before anything acts with money: an always-on
  small machine or server for the core, the PC kept only for work that needs the owner's logins.
- Health and children's data never leave the family's database without a deliberate export.

### 15.4 Telegram — keep it or leave it?

**Keep it as the front door; stop it being the foundation.** Telegram gives identity, push
notifications, a chat, payments in Stars and no install, for free; a native app would spend a
year re-buying those. But the core should not know it is Telegram:

- our own user ids, with a Telegram id as one way to sign in (Users and roles is the moment);
- the backend API and the ledger behind every channel; the bot and the Mini App are two clients;
- the Mini App is already a web app — with its own sign-in (passkeys) it is also an installable
  web app outside Telegram, sharing every screen.

Add a second channel when one of these happens: a family member who is not on Telegram; Telegram
restricting bots or Mini Apps; a need Telegram cannot meet (home-screen widgets, background
location, voice at home, payments beyond Stars). A native app only if this becomes a product
with paying families.

### 15.5 A possible path

- **Next 6 months:** the remaining Mini App screens; Users and roles on SQLite; the action ledger
  with approvals (start with harmless actions: Watch, bought, add to basket); the "PC is off"
  page; backup and a restore drill of the database.
- **6–18 months:** level 1 in every module (filled carts, order sheets, booking links with the
  dates in); Celebrations; Health records; voice notes in; the core off the single PC.
- **2–3 years:** level 2 with limits where a partner API exists; 5–10 friendly families on an API
  key with a cost cap (VISION §6); the web app beside Telegram.
- **5–10 years:** standing rules (level 3) as the normal way a household runs its routine; our
  own identity and app with Telegram as one channel; partners (forwarders, grocers, travel)
  instead of scraping; the family's data in a database the family owns and can take away.

**How we would know it works:** hours and drams saved per month — with zero wrong numbers and
zero spending nobody approved.
