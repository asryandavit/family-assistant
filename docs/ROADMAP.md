# ROADMAP.md — the order of work

Agreed 2026-11-09 (decision 089); direction in `docs/VISION.md`. Updated at the end of every
phase. One phase per session (CLAUDE.md §9); each phase has its own brief and decision entry.

## Now

| # | Work | State | Brief |
|---|---|---|---|
| 1 | 🇨🇳 China search P1 — `/china` text search, full answer: Pinduoduo + 1688 automatic, Taobao as a search link (its sign-in check blocks the bot) | built (decision 090); phone demo after a listener restart | `briefs/CHINA_SEARCH.md` §9 |
| 2 | 🇨🇳 China search P2 — photo search | next | `briefs/CHINA_SEARCH.md` |

## Waiting on the owner or small checks

- 🌍 Market watch go-live: run `scheduler/register-market.ps1` (elevated); the Watch list Google
  Sheet is optional (`config_market.json watch_sheet_id`).
- 🌍 Customs default: verify on petekamutner.am whether the EAEU e-commerce rule from 1 Jul 2026
  (5% duty, €1/kg floor, plus VAT) replaced "15% over €200 / 31 kg"; switch the default in
  `market/customs.md` if it is in force.
- Leftovers: `/auto` does not list the market (and China) tasks; the logon staleness audit does
  not cover them.
- AI usage: check Anthropic's "API credits for subscribers" page — if Max includes API credits,
  move the bot's `claude -p` calls to an API key with those credits.
- Exercise video library: waiting for `YOUTUBE_API_KEY`. Health records (card 4): waiting on the
  owner.

## Next big goal

| # | Work | Why first |
|---|---|---|
| 3 | 👥 Users and roles — invite links, roles (owner/adult/member/viewer), permissions per module, remove/change, change log, private items | everything after it (Celebrations privacy, Mini App login, a product) stands on it |

## Then

| # | Work |
|---|---|
| 4 | 🎉 Celebrations — calendar, early reminders, person notes, gift ideas priced and checked for arrival in time, tracking (VISION §5) |
| 5 | 📱 Mini App step 0 — GitHub Pages, Cloudflare Tunnel, Telegram init-data check, empty app with tabs |
| 6 | 📱 Mini App screens, one session each — China results first, then Market, Basket/checklist, Today/Meals/Training, Travel, Celebrations |
| 7 | Rich Messages for the older reports (Market report, Basket) where they read better as tables |

## Later — only if the owner decides on a product

Beta with 5–10 families on an API key with a cost cap → cloud backend (Postgres, queue,
containerised workers) → Telegram Stars payments → companion app for shopping logins
(VISION §6).
