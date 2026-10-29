# Forwarders — data, not code

One row per forwarder (owner's accounts, 2026-10-29). Adding one later = a row here + its
tariff parser in market/tariffs.py + its price formula in market/shipping.py, tested against
its own calculator. The maths never changes for a new forwarder.

| forwarder | site | tariff source (weekly, Sunday) | price formula (oracle) | warehouses × modes | volume rule | days |
|---|---|---|---|---|---|---|
| Onex | onex.am | `GET /en/tariff` JSON | per 100 g, ≤1 kg "mini" band, rounded up to 100 g, minimum per band (`onex_calculator.json`, 90 answers) | USA air/sea · UK air · Germany air/truck · Italy truck · China air/sea/truck · Russia air · UAE air · Greece truck · Spain air/truck · Poland truck | sea only: L×W×H/5000 | working, from arrival at the warehouse |
| Globbing | am.globbing.com | `let shippingConditions` in the home page | its Calculator.calculate (`globbing_calculator.json`, 600 answers) | USA air/sea · UK air · Germany air/truck · Italy truck · China air/sea/truck · Russia air/truck · UAE air · Greece truck · Spain truck · Korea air | L×W×H/5000 when the route compares gross and volume (USA, UK, UAE, Russia, Korea air), on sea, and when over-dimensional; 100 g step with a 3 g or 7 g tolerance | working ("աշխ. օր"), sea in months |
| BuyForYou | buyforyou.am | `calculateShipping()` constants in the home page | its calculateShipping (`buyforyou_calculator.json`, 140 answers) | USA air/sea · China air (no China sea: the page hides it) | L×W×H/6000 only when a side > 60 cm | working (air), months (sea) |
| EasyTrans | easytrans.am | `GET api.easytrans.am/address/all-available-simple` | its calculate-price API (`easytrans_calculator.json`, 16 answers): rate × kg, minimum; no step, no volume | China truck · Poland air | none observed | working, **from the truck's departure** (owner: ~1.5 months in practice) |

Customs per forwarder (market/customs.py): Onex and EasyTrans the Onex FAQ rule (€200,
15% over, 31 kg); Globbing the larger of 15% over €200 and €2/kg over 30 kg, none from
Russia; BuyForYou 16.2% over €200 (its own calculator's factor).

Delivery-time units are kept exactly as each forwarder publishes them; Onex does not
publish times in its calculator but its /en/tariff JSON has `estimated_day_from/to`.
