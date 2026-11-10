Family: Davit (EN) + wife (RU) + son born 29 Dec 2024. Yerevan, Armenia (Asia/Yerevan,
UTC+4). Davit is a senior full-stack developer (14 yrs, React/NestJS) and a heavy Claude
Code user.

Two systems live in this project:
1. family-assistant — LIVE. Wizz Air fare monitoring + Booking/Airbnb accommodation search,
   controlled from Telegram, stored in Google Sheets. Repo D:\Claude\family-assistant on an
   always-on Windows 11 PC.
2. Family Coach Bot — IN DESIGN. Daily training and meals for the two adults, with the
   toddler appearing only as play ideas and inline meal modifications. Separate build that
   reuses family-assistant's proven patterns.

Full architecture, conventions and known limitations live in the Google Doc
"Family Assistant — Current Architecture (shared context)". Read it before proposing
anything technical for either system.

Non-negotiable conventions (rationale in the doc):
- Host is the always-on Windows PC, not the Mac. Scheduling via Windows Task Scheduler.
- LLM calls go through `claude -p` as a subprocess with the prompt piped via STDIN — free
  on the Max plan. Never the Anthropic HTTP API or Agent SDK.
- Jobs are standalone scripts that run, send their own Telegram message, and exit. The
  listener only receives commands and launches them.
- Python does all arithmetic; the model only judges and phrases. Model output never carries
  unvalidated numbers into storage.
- Telegram: HTML parse mode, not MarkdownV2.
- Never bypass a CAPTCHA or bot wall. Stop, log it, hand me a prefilled link.
- Secrets in Windows environment variables and gitignored files, never in the repo.

Processes on the PC (each its own scheduled task):
- `FamilyAssistant-Listener` — `listener.py`, the one Telegram poller; launches jobs.
- Scheduled jobs (travel scan, coach plan messages, market watch) — run, send, exit.
- `FamilyAssistant-MiniApp` — `python -m miniapp.server` (since 2026-11-10, decision 094):
  stdlib HTTP server on 127.0.0.1:8790 only, serving the built Mini App
  (`miniapp/web/dist`, React + Vite + Telegram UI, built on the PC with Windows Node) and a
  JSON API (GET; since step 1 one POST, `/api/china/action`, JSON ≤ 1 KB, decision 097).
  Every API request carries Telegram's signed initData
  (`Authorization: tma …`), checked with the bot token (HMAC, `miniapp/auth.py`); access by
  Telegram user id + role (`miniapp/people.py`), 60 requests/min per user. Not inside the
  listener and no shared memory with it; the only shared files are below (step 1). Reached from Telegram only through **Tailscale
  Funnel** (`https://<pc>.<tailnet>.ts.net/` → 127.0.0.1:8790, no open router port; the
  hostname lives in gitignored `machine.json`). PC off → the app is unreachable.
  Step 1 (China screen) reads the asking person's own `/china` result and runs 👁 Watch /
  💬 Reviews through the same `china.bot.callback` as the chat buttons, so the Mini App server
  is a second writer of Market watch's `items.json` / `owner_prices.json` next to the
  listener: those read-modify-writes run under `market/state.write_lock` (a cross-process
  lock file). Reviews still run as a queued China job; the answer arrives in the chat.

Shared platform (`lib/`, frozen rule in CLAUDE.md §1) — additive changes log:
- `lib/telegram.py` inline buttons take three kinds: callback data (any string), a link
  (`https://…`), and `{"web_app": url}`, which opens the Mini App at that https URL inside
  Telegram (2026-11-10, Mini App step 0, for step 1's "📱 Open" buttons). Existing buttons
  are unchanged.
- `listener.py` reads photos (2026-11-10, China photo search, decision 095): a message with
  a photo or a file and no text, from an allowed chat, goes to `china/bot.photo` (through
  the same fault-catching `_china` wrapper). Before this, every message without text was
  dropped, so no feature saw photos. A `/china` caption starts a photo search; any other
  photo gets one "Search China?" yes/no question, never a search on its own. The log line is
  "photo -> china" only (no file id, no chat id). Text messages and buttons are unchanged.
  When Health records lands it reads photos only inside an open `/health` conversation and
  must be checked before this route.

Working style: be honest and push back on weak ideas rather than agreeing; recommendation
first with a short reason; small verifiable steps; no validation filler.