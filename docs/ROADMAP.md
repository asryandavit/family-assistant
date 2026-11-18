# ROADMAP.md — the order of work

Agreed 2026-11-09 (decision 089); direction in `docs/VISION.md`. Updated at the end of every
phase. One phase per session (CLAUDE.md §9); each phase has its own brief and decision entry.

## Now

| # | Work | State | Brief |
|---|---|---|---|
| 1 | 🇨🇳 China search P1 — `/china` text search, full answer: Pinduoduo + 1688 automatic, Taobao as a search link (its sign-in check blocks the bot) | built (decision 090); phone demo after a listener restart | `briefs/CHINA_SEARCH.md` §9 |
| 2 | 🇨🇳 China search P2 — photo search: a photo with a `/china` caption (or "Search China?" yes) → 1688 by photo, Pinduoduo by the words read from the photo (its photo search is app-only), Taobao link + app tip → the same full answer | built (decision 095); phone demo after a listener restart | `briefs/CHINA_SEARCH.md` §10 |
| 3 | 📱 Mini App step 0 — our own app (React + Vite + Telegram UI), served from the PC through a tunnel, Telegram signature checked on every request, empty sections | **done** (decisions 094, 096): owner demo 2026-11-10 passed — owner and adult (Karine), dark mode, Home list, back button, PC-not-reachable and recovery | `briefs/MINI_APP.md` |
| 3a | 🛒 `/amazon` search — Amazon UK/DE/IT/US read by the bot's browser and a Python parser (no model reads pages), priced to Yerevan, seller trust; then a shared engine (rule of two), Armenian shops, Russia, and one merged `/find` | **P0 done** (decision 100); **P1 built** (decision 101): `/amazon` on UK/DE/IT — seller trust, priced to Yerevan, measured on the PC (≈ 2 min, ≈ $0.19 per run); phone demo after a listener restart (brief §11.3); then P1b (extract the engine); US is P2 | `briefs/AMAZON_SEARCH.md` |
| 3b | 🛒 Groceries — ✅ tick list shared by both of us (`/list`, both chats update on every tap, the Sheet follows) and basket picks judged by quality rules (avoid / require / prefer / min fat % / max price in `plan/meals/basket.md`, a reason on every non-cheapest pick, Parma's 100 g prices no longer read as per kg) | **built** (decision 106); phone demo after a listener restart; the Mini App shows the same list (decision 108); next: the owner refines the rules table, the list follows the generated menus once meals-variety publishes an ingredient function | `plan/meals/basket.md` |
| 3c | 🍽 Weekly menus with real variety — a dish library (staples + sourced Mediterranean and Armenian dishes, every recipe link checked) and a deterministic week generator: fish 2×, legumes 4× (never twice a day), poultry ≥ 2×, oats ≥ 3 breakfasts, no dish the week after, 1–2 new dishes a week; weeks 5–8 written; the Sunday menu as a Rich Message with 📱 Today / 🧺 Basket buttons | built (decision 107); owner review of the week-5 message; the new-dish queue lasts to about week 15 (warning from about week 13) — the owner is told when fewer than 5 are left. Open for groceries: the basket could read `coach.menu_gen.week_ingredients()` | `plan/meals/principles.md` (weekly rules) |
| 3d | 🛍 Where to buy — a "How to buy" section on every `/china` and `/amazon` result (buy on the site, which forwarder warehouse, which forwarder × mode and why, customs, restrictions) and a cheapest / fastest / most trusted block; Dubai parked | planned (decision 113); **X0 done** (decision 114: `market/buying.md`); X1 next | `briefs/CROSS_BORDER.md` |

## Waiting on the owner or small checks

- 🌍 Market watch go-live: run `scheduler/register-market.ps1` (elevated); the Watch list Google
  Sheet is optional (`config_market.json watch_sheet_id`).
- 🌍 Customs default: checked 2026-11-18 (decision 114) — Onex and Globbing still state €200 / 31 kg /
  15 % over €200; the EAEU 5 % rule is reported for 1 Jan 2027. `market/customs.md` stays on `default`;
  re-check in January 2027 (petekamutner.am or the forwarders' FAQs).
- 🇨🇳 China P3 — keep logged in (logon tabs, 09:00 login check, 🔑 message): the brief's old
  P2, moved after photo search by the owner (2026-11-10).
- 🧹 Housekeeping go-live (decision 103): run `scheduler/register-housekeeping.ps1` (elevated).
  Leftovers: `/auto` and the logon staleness audit do not list `FamilyAssistant-Housekeeping`
  (`selfcheck.py` does: disk free + last run); the listener's log is capped nightly, not at the
  source (`listener.py` keeps its own open handle, untouched); a stale Chrome `lockfile` after a
  crash is treated as free only on Windows (macOS/Linux use `SingletonLock` + pid).
- Leftovers: `/auto` does not list the market (and China) tasks; the logon staleness audit does
  not cover them, nor the Mini App server (`FamilyAssistant-MiniApp`) — `selfcheck.py` does.
- AI usage: check Anthropic's "API credits for subscribers" page — if Max includes API credits,
  move the bot's `claude -p` calls to an API key with those credits.
- Exercise video library: waiting for `YOUTUBE_API_KEY`. Health records (card 4): waiting on the
  owner.

## Next big goal

| # | Work | Why first |
|---|---|---|
| 4 | 👥 Users and roles — invite links, roles (owner/adult/member/viewer), permissions per module, remove/change, change log, private items | everything after it (Celebrations privacy, Mini App login, a product) stands on it |

**Parked by the owner 2026-11-10** ("omit this for now, concentrate on improving"). Already agreed for when it starts: permission levels per module **None / View / Use / Manage**; managed in the Mini App (People screen) plus short chat commands (`/invite`, `/people`); **no custom roles** (the four built-in ones only); first people to add: not decided. Known gaps it must close: the chat side has no roles (any allowed chat runs every command), the Mini App's `/api/run` is one coarse `run` permission, and who is allowed is still two env chat ids (`lib/telegram.allowed_chats`, `config_miniapp.json`).

## Then

| # | Work |
|---|---|
| 5 | 🎉 Celebrations — calendar, early reminders, person notes, gift ideas priced and checked for arrival in time, tracking (VISION §5) |
| 6 | 📱 Mini App screens, one session each (after step 0) — **built: China results and search form (decisions 097, 098), Today, Market, Basket, Travel (098) — phone demo next**; Celebrations when built. Open: China photos (the pipeline must keep image ids — China-session follow-up), photo search from the app (not possible), editing watched items |
| 7 | Rich Messages for the older reports (Market report, Basket) where they read better as tables |

## Later — only if the owner decides on a product

Beta with 5–10 families on an API key with a cost cap → cloud backend (Postgres, queue,
containerised workers) → Telegram Stars payments → companion app for shopping logins
(VISION §6).
