# ROADMAP.md — the order of work

Agreed 2026-11-09 (decision 089); direction in `docs/VISION.md`. Updated at the end of every
phase. One phase per session (CLAUDE.md §9); each phase has its own brief and decision entry.

## Now

| # | Work | State | Brief |
|---|---|---|---|
| 1 | 🇨🇳 China search P1 — `/china` text search, full answer: Pinduoduo + 1688 automatic, Taobao as a search link (its sign-in check blocks the bot) | built (decision 090); phone demo after a listener restart | `briefs/CHINA_SEARCH.md` §9 |
| 2 | 🇨🇳 China search P2 — photo search: a photo with a `/china` caption (or "Search China?" yes) → 1688 by photo, Pinduoduo by the words read from the photo (its photo search is app-only), Taobao link + app tip → the same full answer | built (decision 095); phone demo after a listener restart | `briefs/CHINA_SEARCH.md` §10 |
| 3 | 📱 Mini App step 0 — our own app (React + Vite + Telegram UI), served from the PC through a tunnel, Telegram signature checked on every request, empty sections | **done** (decisions 094, 096): owner demo 2026-11-10 passed — owner and adult (Karine), dark mode, Home list, back button, PC-not-reachable and recovery | `briefs/MINI_APP.md` |

## Waiting on the owner or small checks

- 🌍 Market watch go-live: run `scheduler/register-market.ps1` (elevated); the Watch list Google
  Sheet is optional (`config_market.json watch_sheet_id`).
- 🌍 Customs default: verify on petekamutner.am whether the EAEU e-commerce rule from 1 Jul 2026
  (5% duty, €1/kg floor, plus VAT) replaced "15% over €200 / 31 kg"; switch the default in
  `market/customs.md` if it is in force.
- 🇨🇳 China P3 — keep logged in (logon tabs, 09:00 login check, 🔑 message): the brief's old
  P2, moved after photo search by the owner (2026-11-10).
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
