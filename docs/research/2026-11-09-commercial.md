# Research — commercial product feasibility (2026-11-09)

Summary of a deep-research report the owner ran on 2026-11-09 (prompt in decision 089's
discussion). **TRUE** = the report cites a primary source; **unverified** = secondary or missing —
re-check against primary sources before acting. Nothing here is built; it informs
`docs/VISION.md` §6.

## 1. Anthropic (AI)

- **TRUE** — Claude Code legal page: subscription OAuth is "intended exclusively for purchasers of
  Claude Free, Pro, Max… plans and is designed to support ordinary use"; "Developers building
  products or services… should use API key authentication"; "Customers may not pay for, resell,
  or intermediate Claude usage on their end users' behalf." Enforcement against third-party
  clients started 9 Jan 2026; third-party harnesses (e.g. OpenClaw) cut off 4 Apr 2026
  (secondary). → A product must use the **API under commercial terms**.
- **Unverified** — "API credits for subscribers": Max plans may include monthly API credits
  usable with an API key. Check platform.claude.com before relying on it.
- **TRUE** — Armenia is a supported region (API and claude.ai). Re-read the Usage Policy and
  Supported Regions Policy taking effect 12 Nov 2026.
- Official API prices read 9 Nov 2026 (USD per million tokens, input/output): Haiku 5.5
  0.10/0.50; Haiku 4.5 1/5; Sonnet 5.5 2/10; Opus 5.5 4/20; batch −50%; models 4.7+ use ~30% more
  tokens for the same text.
- **Estimate** — AI for wording only (≈180 short calls + 4 weekly plans per family per month):
  ≈ $0.04 (Haiku 5.5) to ≈ $0.72 (Sonnet 5.5) per family per month.
- **Judgement** — users bringing their own key (BYOK): low value for families, key-custody risk;
  skip.

## 2. Telegram

- **TRUE** — digital goods and subscriptions in bots/Mini Apps must use **Telegram Stars**;
  otherwise the bot may be hidden from mobile users. Physical goods/services may use a provider.
- Developer receives **$0.013 per Star**, available after up to 21 days, withdrawn as TON via
  Fragment (min 1,000 Stars). Example: a 250-Star/month plan ≈ $5 to an iPhone buyer ≈ $3.25 net.
- **TRUE** — Star subscriptions exist (monthly period).
- Linking out of the bot to pay for its own digital features: unverified, treat as risky.
- Bot API 10.3 (24 Aug 2026) current; Rich Messages 10.1 (11 Jun 2026). Limits: ~1 msg/s per
  chat, ~30 msg/s broadcast.
- Receiving TON in Armenia: Law on Crypto-Assets in force 4 Jul 2025, CBA regulations from
  31 Jan 2026, licensing deadline 31 Jan 2027; licensed-platform status unverified.

## 3. Store and travel APIs

- **TRUE** — Amazon Associates: "your Site must not have price tracking and/or price alerting
  functionality" unless Amazon agrees; PA-API 5 replaced by the Creators API (needs 10 sales in
  30 days). → No Amazon price alerts in a product without written agreement.
- AliExpress Portals: up to 9% commission, affiliate API; Armenia acceptance unverified.
- Taobao/Alimama, Pinduoduo (Duoduo Jinbao), 1688 Open API: likely need Chinese ID/entity —
  unverified.
- Travel: Kiwi Tequila invitation-only; Travelpayouts (Aviasales 1.1–1.3%, Kiwi 3%, Booking ~4%;
  API needs 50k MAU); Skyscanner partner-only.

## 4. Legal

- Armenia's personal data law: health data is special-category; processing it requires notifying
  the PDPA; cross-border transfer rules; a reform (independent commission, DPIA/DPO) was in
  consultation Aug 2026.
- GDPR for EU users: Art. 9 explicit consent for health data, Art. 27 EU representative, Art. 35
  DPIA likely. Treat allergies, medical diets and body metrics as health data.
- Keep to general wellness with "not medical advice"; avoid diagnosis/treatment claims.
- Armenian tax (unverified details): IE registration online; turnover-tax rates 1% for listed
  high-tech activities (conditions disputed), 10% default; whether a bot subscription counts as
  high-tech is open.

## 5. Customs (affects Market watch now)

- €200 and 31 kg per personal parcel; one source states the threshold as AMD 200,000.
- **Conflict** — above the threshold: "15% of the excess, min €2/kg" vs a new EAEU e-commerce
  regime from 1 Jul 2026 "5% duty, €1/kg floor, plus VAT". → Verify on petekamutner.am
  (ROADMAP, waiting items).

## 6. Market, pricing, costs

- Competitors, pricing benchmarks and conversion rates: **not researched** (budget ran out).
- Forwarders already own calculators (Globbing, Onex); a "find product + exact price to Yerevan +
  order through forwarder X" flow sold as revenue share/lead fee is more plausible than a SaaS
  licence — validate with 3–5 forwarders first.
- Infrastructure estimates (unverified): self-managed VPS $20–80/month; managed PaaS
  $50–200/month.

## 7. Report's recommendation (judgement)

First paid offer: a ~250-Star/month subscription bundling a weekly meal plan + shopping list,
AliExpress/China price watch with landed cost to Yerevan, and travel deals via Travelpayouts; a
free tier with one watch item and one plan a month. Leave out at launch: Amazon alerts, BYOK,
Chinese domestic marketplaces until eligibility is confirmed.
Top risks: platform terms (Amazon, Telegram, Anthropic); Stars payout friction (TON, Armenian
crypto licensing); health-data compliance.
