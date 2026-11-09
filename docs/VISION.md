# VISION.md — where this project is going

Status: agreed direction, 2026-11-09 (decision 089). Not a build plan: the order of work is in
`docs/ROADMAP.md`, each phase still gets its own brief in `docs/briefs/`.

The owner's rule: **build every feature in our own environment first and make it as close to
perfect as we can; change the platform step by step.** Even if this never becomes a commercial
product, it should be an excellent family assistant. The direction may change as we learn.

---

## 1. Today

A personal family system: one Windows PC, one Telegram bot (`listener.py` + scheduled jobs), two
chats (Davit, Karine), data in Git files and Google Sheets, the owner's Chrome logins (China
search), the owner's Claude Max subscription through the official `claude` CLI. It works because
everything is shaped around one household.

## 2. The product idea (the big goal)

**One Telegram assistant for the whole household: what we eat, how we train, what we buy and at
what price, where we travel, and what we celebrate.** Modules, switchable per household:

| Module | Status (2026-11-09) |
|---|---|
| 🍽 Meals and groceries — plan, basket, price compare | built |
| 🏃 Training — plans, videos, safety | built |
| ✈️ Travel — flights, stays, deals | built |
| 🌍 Market watch — watch list priced to Yerevan | P1 built, go-live pending |
| 🇨🇳 China search — `/china`, photo search later | P1 in progress |
| 🏥 Health records | in discovery |
| 🎉 Celebrations — see §5 | idea, after users and roles |
| Later ideas: kids (school, activities), home (bills, repairs), money (budgets) | ideas |

## 3. Users, roles and permissions (the foundation)

- **Household**: one owner (pays, invites, removes), plus members.
- **Roles**: owner · adult (all modules, can add items) · member/teen (sees the plan, no
  settings) · viewer (e.g. a grandparent who only sees the menu).
- **Permissions per module** (e.g. Karine edits Meals, not Travel alerts).
- **Invites** by an expiring Telegram link (`t.me/<bot>?start=invite_…`); the owner approves.
- **Remove / change** people from a "People" screen; every change is logged with who and when.
- **Private items**: an item can be visible only to the person who created it (gift surprises).

**Household-ready rule (from now on).** Every new feature is written for households, not for two
hard-coded chats: user ids and roles instead of chat ids, settings per household, a permission
check per module, private items possible. It costs little now and avoids a rewrite later.

## 4. Architecture direction

```
Today:   PC → listener.py + scheduled jobs + files/Sheets + owner's Chrome + claude -p (Max)

Later:   Telegram bot ─┐
         Mini App     ─┼─► Backend API (users, households, roles, billing)
         (web later)  ─┘      ├─ Database (Postgres)
                              ├─ Scheduler + job queue (plans, scans, alerts)
                              ├─ Workers (headless browsers / official APIs) in Linux containers
                              └─ AI layer (Anthropic API, cached, cost-capped per household)
         Optional companion app on a user's own PC — only for sites that need THEIR logins
         (Taobao, Pinduoduo): signed, read-only, sends results to the backend.
```

- **No Windows machine per user.** Shared containerised workers with an isolated browser profile
  per household; scale by adding workers.
- **Numbers are code, words are AI** stays: it is also what keeps the AI cost per family low.
- **Telegram stays the front door** for alerts and summaries; the **Mini App** is the full screen
  (tables, photos, filters, editing). A Mini App cannot run jobs or send messages itself — the
  daily jobs keep running on the PC (later the backend) and every message gets an "Open" button.
- **Mini App connection (when built)**: web files and data both served from the PC through a
  tunnel (one origin, no public repo; changed 2026-11-09, `briefs/MINI_APP.md` §3), every request checked against Telegram's signed init data. Family data is
  never published on a public page. Store pages cannot usefully be embedded (iframe): logins don't
  carry, the app can't read them, and the stores' apps are better — results use "Open in app"
  deep links instead.

## 5. Celebrations (agreed idea, 2026-11-09)

- Read **Google Calendar** read-only (shared with the bot's service account) plus Armenian and
  common holidays and anniversaries the owner adds.
- Remind early: default **2 months, 1 month, 2 weeks, 1 week** before (adjustable).
- Per-person notes told once and added to over time (likes, sizes, devices, "no perfumes"),
  past gifts (no repeats), budget per person.
- Suggest 3–5 gift ideas with a reason, then search real offers through China search, Amazon,
  vega.am and Market watch, priced in ֏ and USD with shipping, and check **"will it arrive in
  time?"** with the working-day arrival maths against the event date.
- On confirmation the gift becomes a Market watch item **with a deadline** ("order by …"), then a
  one-tap status: idea → ordered → shipped → arrived → wrapped → given; a short note afterwards.
- **Private per creator** (a gift for Karine is invisible to Karine) — needs users and roles first.
- Open questions for its brief: which calendar(s); default reminder steps; gifts only or also
  event planning (guests, menu, venue, budget).

## 6. If it becomes a commercial product (only if the owner decides)

Findings from the 2026-11-09 research (`docs/research/2026-11-09-commercial.md`):

- **AI**: a Claude Pro/Max subscription may not serve other people or a paid product; a product
  uses the **Anthropic API under commercial terms** (Armenia is a supported region). With AI used
  only for wording, the estimated cost is cents to under $1 per family per month.
- **Payments**: digital subscriptions inside Telegram must use **Telegram Stars** (≈ $0.013 per
  Star to the developer, paid in TON after up to 21 days). Physical services (e.g. a forwarder
  order) may use a payment provider.
- **Stores**: Amazon's Associates policy forbids price tracking/alerts without Amazon's
  agreement; scraping stores at scale breaks their terms. A product uses official/affiliate APIs
  (AliExpress Portals, Travelpayouts for flights/hotels), which also pay commission.
- **Revenue ideas**: Stars subscription (freemium: free basic, paid family plan), affiliate
  commissions, forwarder revenue share / lead fees (validate with 3–5 forwarder conversations
  first), local partners later.
- **Legal**: health and diet data are special-category data (Armenia's PDPA notification; GDPR
  Art. 9 and 27 for EU diaspora users); "not medical advice" wording; subscription consumer rules.
- **Language**: a product for Armenia and the diaspora needs Armenian and Russian; today the bot
  is English only by design (CLAUDE.md §7), and the single template layer keeps that change cheap.
- **Path**: (1) household-ready features now → (2) users and roles on the PC → (3) beta with
  5–10 friendly families on an API key with a cost cap → (4) cloud backend, Mini App, Stars,
  companion app → (5) change direction freely on what the beta shows.
