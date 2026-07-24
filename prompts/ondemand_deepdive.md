# On-demand deep-dive (paste into claude.ai or Cowork — NOT part of the scheduled job)

Run this when a flight deal fires and you want to lock a trip. It uses the Booking
and Kiwi connectors (and Airbnb via browsing) with you present, so bot walls and
CAPTCHAs are handled by a human.

---

We're a family of 3 from Yerevan (EVN): 2 adults + 1 toddler (born 29 Dec 2024 —
lap infant on Wizz Air until 29 Dec 2026, needs own seat after; check each leg).
Analyze this trip: [DESTINATION(S) / DATE WINDOW], with ±3-day flexibility,
considering one-way, round-trip, AND open-jaw (fly into one city, back from a nearby
one). Prioritize Wizz Air; check Armenian long-weekend windows.

Flights: use the Kiwi.com connector (no multi-city in one call — do open-jaw as two
one-way searches and sum them). Cross-check any Wizz fare against wizzair.com.

Stays: use the Booking.com connector, and browse Airbnb for the same dates.
Must-haves: rating >= 7.5; elevator/lift unless ground floor; stroller-friendly;
safe, central or transit-connected; crib + high chair; quiet; pharmacy and park
nearby; sea view preferred if coastal. Read reviews/descriptions to verify the
things filters can't (elevator, quiet, sea view, crib).

Normalize every stay to TRUE NIGHTLY COST = nightly rate
+ estimated daily public transport for 2 adults if outside the centre
+ estimated breakfast for 3 if breakfast isn't included.

Output a ranked comparison table, recommend one flight plan and one stay, and give
the exact live prices to confirm before booking. Never guess a price.
