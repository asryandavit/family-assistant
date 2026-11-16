# Food principles

The rules every meal plan follows. Change a rule here and the next week's plan follows
it. Not medical advice — Davit's cholesterol and gastritis are being managed by a doctor.

## The base

**Mediterranean-leaning everyday Armenian food:** legumes, bulgur, buckwheat, oats,
chicken and fish, lots of cooked vegetables, matsun and katnashor, olive oil, fruit.
This one pattern serves weight loss, cholesterol and a gentle stomach at the same time.

**Portions instead of calorie counting** (decision 073): adults use the plate rule —
**½ vegetables · ¼ protein (palm-size) · ¼ grains or legumes (fist-size)** — plus one
small piece of bread/lavash. The son eats the same dish, as much as he wants.

## Rules by need

| Need | Do | Limit |
|---|---|---|
| **Weight loss** (both adults) | Protein + vegetables at every meal; legumes for fullness; lighter dinners; water as the main drink | Sweet drinks, pastries as daily food, eating while standing/snacking from the toddler's plate |
| **LDL cholesterol** (Davit) | Oats/hercules at least 3 mornings; legumes 4 meals/week; oily fish 2×/week (trout, mackerel, sardines, salmon when affordable); olive oil; walnuts in small amounts | Saturated fat: butter, fatty meat, sausages/salami/mortadella, lots of full-fat cheese for the adults; fried food |
| **Mild gastritis** (Davit) | Regular meals, no long fasting; boil / bake / stew / steam; finish dinner 3–4 h before bed; gentle walk after meals | Very spicy, deep-fried, very acidic, alcohol; large late meals; hard exercise soon after eating |
| **Lactose — fresh milk only** (Davit) | Lactose-free milk in oats/coffee; matsun (live cultures help); katnashor and aged cheese in normal portions | A big glass of fresh milk |
| **Citrus** (Davit) | Herbs, garlic, olive oil, mild vinegar if tolerated, pomegranate seeds in small amounts | Lemon/orange dressings and juices for him |
| **Son** | Full-fat dairy, iron daily, soft safe cuts, no added salt/sugar | See [../family/son.md](../family/son.md) |

## Meal shape

- **Breakfast** — the family anchors, kept as they are: eggs (scrambled or boiled),
  hercules (oat porridge), katnashor. Rotate them. Fast, filling, good for cholesterol.
- **Lunch** — the main cooked meal, usually from a batch.
- **Dinner** — lighter and by 19:00: soup, salad + protein, omelette.
- **Snack** — one, with coffee #2 at ~15:30: fruit or matsun.
- **Coffee** — twice a day, kept. After food if the stomach complains; last by ~16:00.

## Saving Karine's time (the main design driver)

- **Two batch sessions a week:** Sunday ≈ 90 min, Wednesday ≈ 45 min.
- **Cook once, eat twice:** every batch dish covers at least two meals.
- **Dinners are assembled, not cooked:** soup from the pot, salad + boiled egg, omelette.
- **A growing rotation** ([dishes.md](dishes.md)) — the family's staples plus 1–2 new
  dishes a week (see the weekly rules below), each with a checked recipe link.

## The weekly rules (how every week's menu is built)

Weeks are built from [dishes.md](dishes.md) by `coach/menu_gen.py` (decision 107) — the same
library and the same earlier weeks always give the same week, so nobody writes a week by hand
and no week is ever missing. Weeks 5–8 are written out as `week-05.md` … `week-08.md`; later
weeks are built the same way when they are shown (or written ahead with
`python -m coach.menu_gen --write 9 12`). A week file edited by hand always wins, and the weeks
after it are built around what it says.

| Day | Breakfast | Lunch | Dinner (by 19:00) |
|---|---|---|---|
| Mon, Tue | the pattern below | **batch lunch A** (Sunday batch) | **batch soup** (Sunday batch) |
| Wed, Thu | | **batch lunch B** — always a legume (Wednesday batch) | Wed **fish**, Thu **egg dinner** |
| Fri | | **fish** | **light dinner** |
| Sat | | **weekend lunch** — always with a protein | Scoolinary project (the planned treat) |
| Sun | | **weekend lunch** | its leftovers, small portion, with a green salad (Sunday evening is the batch session) |

- **Mediterranean base:** olive oil, legumes, whole grains (buckwheat, bulgur, pearl barley
  rotated as sides), vegetables and herbs, matsun and katnashor, very little red meat (none
  scheduled), with the Armenian staples (lobi, ajapsandal, dolma, spas, eetch, harissa, lavash).
- **Fish 2×** a week (Wednesday dinner, Friday lunch).
- **Legumes 4 meals**, never two in one day: lunch B is a legume, and exactly one of lunch A
  and the soup is — gentle on the stomach, filling for weight loss, good for LDL.
- **Chicken or turkey at least 2 meals**; eggs most days (breakfast or Thursday dinner).
- **Breakfasts** follow oats · eggs · other · oats · eggs · oats · other, never the same two
  days running; oat porridge is cooked in water or lactose-free milk and topped with matsun.
  Monday's breakfast never needs an evening prep (Sunday evening is the batch session).
- **Variety:** a lunch or dinner dish never comes back the week after (at least 8 days apart)
  and the generator first tries dishes not eaten for two weeks; no two dolma-type dishes in
  a week; two weeks running never share a day.
- **Something new every week:** 1–2 dishes new to the family (3 when a list is still short),
  taken in the order of [dishes.md](dishes.md); after their first week they join the rotation.
  When fewer than 5 new dishes are left in the queue the owner is told to add some — add a
  dish with a checked recipe link and `status` `new`.
- **The son** eats the same dishes: his portion before salt, soft pieces, bones checked,
  nuts only ground or finely chopped (the 👶 line under each day).
- If a week can't be built (for example the fish list is empty), the message says so plainly
  and the owner is told — another week's menu is never shown instead.

## Treats

Planned, not forbidden: the weekend Scoolinary project (pizza, croissants, chocolate…)
is the treat. A proper portion, shared, enjoyed. Alcohol occasional.
