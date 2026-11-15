# Dish library

Every meal in every week comes from this file, by **id**. The week menus are built from it
by a fixed set of rules (`coach/menu_gen.py`, rules in [principles.md](principles.md)) —
add a dish here and it starts appearing; change a column and the next weeks follow.

**Columns**
- **slot** — where the generator may use it: `breakfast-oats`, `breakfast-egg`,
  `breakfast-other`, `main` (a batch lunch, cooked once and eaten two days running),
  `soup` (a batch soup for two dinners), `fish`, `egg` (an egg dinner), `light` (a light
  dinner), `weekend` (Saturday or Sunday lunch), `side`, `project`. `—` = kept only
  because week 1 uses it.
- **protein** — `legume`, `chicken`, `turkey`, `fish`, `egg`, `dairy`, `veg`, `grain`.
  The weekly balance (fish 2×, legumes 4×, …) is counted from this column.
- **status** — `staple` = the family already cooks it; `new` = not cooked yet. New dishes
  come in **in the order of this file**, 1–2 a week, then join the rotation. Set a dish
  back to `new` if you don't actually cook it; move a row up to get it sooner.
- **side** — what the generator serves with it: `grain` (buckwheat, bulgur or barley,
  rotated), `salad` (green salad + lavash), `egg` (a boiled egg — for dishes without
  their own protein), `matsun`, or `—`.
- **group** — dishes of one group never appear in the same week (two kinds of dolma).
- **prep** — the evening before (soaking), shown as "Prep for tomorrow".
- **son** / **tip** — shown with the dish. The son's rules in short: whole nuts never
  (ground or finely chopped only), soft pieces, bones checked, his portion taken out
  before salt, no added sugar.
- **buy** — the shopping words for the dish (`coach.menu_gen.week_ingredients()`; names
  as in [basket.md](basket.md) where it has the item).
- **ref** — one free recipe page for technique. Only allowlisted sites
  (`docs/TELEGRAM_UX.md` §5c), and only after the page was opened and checked to be that
  dish (all refs below checked 15 Nov 2026). The dish, portions and family rules stay ours.

## Breakfasts

| id | dish | slot | protein | status | side | group | prep | son | tip | buy | ref |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `bf-hercules` | Oat porridge (hercules) cooked in water or lactose-free milk, topped with matsun | breakfast-oats | grain | staple | — | | | His porridge may use whole milk; walnuts ground | Top with ground walnuts and grated apple or pear | Rolled oats (hercules); Lactose-free milk (UHT); Matsun; Walnuts (unsalted); Apples | https://www.bbcgoodfood.com/recipes/perfect-porridge |
| `bf-eggs-boiled` | Boiled eggs with tomato, cucumber, greens and a little lavash | breakfast-egg | egg | staple | — | | | Egg quartered, cucumber in thin sticks | Boil 6 on Sunday, they keep 3 days | Eggs; Tomatoes; Cucumbers; Parsley; Lavash | |
| `bf-eggs-scrambled` | Scrambled eggs with greens and tomato, in olive oil | breakfast-egg | egg | staple | — | | | No salt on his part | | Eggs; Tomatoes; Dill; Olive oil | |
| `bf-katnashor` | Katnashor bowl with oats and fruit | breakfast-other | dairy | staple | — | | | A little honey on his only | | Katnashor (tvorog); Rolled oats (hercules); Bananas | |
| `bf-overnight-oats` | Overnight oats soaked in matsun, with grated apple | breakfast-oats | grain | new | — | | Soak the oats in matsun tonight | Walnuts ground, not whole | Make 2–3 jars at once | Rolled oats (hercules); Matsun; Apples; Walnuts (unsalted) | https://www.bbcgoodfood.com/recipes/overnight-oats |
| `bf-labneh` | Labneh (strained matsun) with cucumber, olive oil and lavash | breakfast-other | dairy | new | — | | Strain the matsun overnight | Lavash in small soft pieces | Strain a whole 1 kg tub; keeps 5 days | Matsun; Cucumbers; Olive oil; Lavash | https://www.themediterraneandish.com/homemade-labneh-recipe/ |

## Batch lunches (cooked once, eaten two days)

| id | dish | slot | protein | status | side | group | prep | son | tip | buy | ref |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `ln-chicken-tray` | Oven-tray chicken with potato, carrot, pepper and zucchini | main | chicken | staple | grain | | | Soft pieces, skin off | Skinless chicken for the adults | Chicken thighs; Potatoes; Carrots; Bell peppers; Zucchini | |
| `ln-lobi` | Bean stew (lobi) with herbs | main | legume | staple | salad | | Soak the beans tonight (or use canned, rinsed) | Mash his beans a little; walnuts ground | Cook beans fully soft — easier on the stomach | White beans (cans); Onions; Coriander; Walnuts (unsalted) | |
| `ln-chicken-plov` | Chicken and buckwheat plov | main | chicken | staple | salad | | | Soft pieces | | Chicken breast; Buckwheat; Carrots; Onions | |
| `ln-chickpea` | Chickpea and vegetable stew | main | legume | staple | grain | chickpea | Soak the chickpeas tonight (or use canned) | Mash his chickpeas — whole ones are a choking risk | | Chickpeas (dry); Carrots; Zucchini; Canned tomatoes | |
| `ln-mujaddara` | Mujaddara — lentils and rice with soft onions | main | legume | new | salad | | | | Soften the onions in olive oil rather than frying them crisp | Brown/green lentils; Rice (for dolma); Onions; Olive oil | https://www.themediterraneandish.com/mujadara-lentils-and-rice-with-crispy-onions/ |
| `ln-turkey-meatballs` | Turkey meatballs in a mild tomato sauce | main | turkey | new | grain | | | Halve his meatballs | Use canned tomatoes cooked long, no chilli | Turkey mince; Onions; Canned tomatoes; Parsley | https://www.themediterraneandish.com/turkey-meatballs-recipe/ |
| `ln-gigantes` | Greek baked white beans (gigantes plaki) | main | legume | new | salad | | Soak the beans tonight (or use canned) | Mash his beans a little | Bake until the sauce is thick and mild | White beans (cans); Canned tomatoes; Onions; Dill; Olive oil | https://www.themediterraneandish.com/gigantes-plaki-greek-giant-beans/ |
| `ln-vospov-kufteh` | Vospov kufteh — red lentil and bulgur patties | main | legume | new | salad | | | | | Red lentils; Bulgur; Onions; Parsley | https://thearmeniankitchen.com/vospov-kufteh-red-lentils-with-bulgur/ |

## Weekend lunches

| id | dish | slot | protein | status | side | group | prep | son | tip | buy | ref |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `ln-dolma-lean` | Lean dolma with turkey mince, rice and herbs | weekend | turkey | staple | matsun | dolma | | | | Turkey mince; Rice (for dolma); Parsley; Dill | |
| `ln-veg-stew` | Ajapsandal — baked vegetable stew | weekend | veg | staple | egg | | | | Baked, not fried | Eggplant; Zucchini; Bell peppers; Tomatoes; Potatoes | https://www.armenianinstitute.org.uk/food/ajabsandal |
| `wk-harissa` | Harissa — chicken and wheat porridge | weekend | chicken | staple | salad | | Start it in the morning (it simmers about 4 hours) | | | Chicken thighs; Wheat (shelled); Onions | https://thearmeniankitchen.com/harissa-herriseh-keshkeg-it-all-means/ |
| `wk-cabbage-tolma` | Cabbage tolma with turkey mince and rice | weekend | turkey | staple | matsun | dolma | | | | Cabbage; Turkey mince; Rice (for dolma) | |
| `wk-souvlaki` | Chicken souvlaki from the oven, with lavash and tzatziki | weekend | chicken | new | — | | Marinate the chicken tonight | Soft pieces, cut small | Lemon in the marinade: leave it out of Davit's portion | Chicken breast; Lavash; Matsun; Cucumbers; Garlic | https://www.themediterraneandish.com/greek-chicken-souvlaki-recipe-tzatziki/ |
| `wk-stuffed-peppers` | Stuffed peppers with turkey mince and rice | weekend | turkey | new | matsun | dolma | | | Use turkey mince | Bell peppers; Turkey mince; Rice (for dolma); Canned tomatoes | https://www.themediterraneandish.com/stuffed-peppers-recipe/ |
| `wk-briam` | Briam — Greek roasted vegetables with feta | weekend | veg | new | egg | | | | | Potatoes; Zucchini; Tomatoes; Onions; Feta; Olive oil | https://www.themediterraneandish.com/briam-greek-roasted-vegetables/ |

## Soups (cooked once, two dinners)

| id | dish | slot | protein | status | side | group | prep | son | tip | buy | ref |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `ln-lentil-soup` | Red lentil soup with carrot and onion | soup | legume | staple | — | | | Blend half the pot for him | Cumin mild, no chilli | Red lentils; Carrots; Onions | https://www.bbcgoodfood.com/recipes/spiced-carrot-lentil-soup |
| `sp-spas` | Spas — warm matsun soup with grains | soup | dairy | staple | — | | | | Very gentle on the stomach | Matsun; Bulgur; Eggs; Onions | https://thearmeniankitchen.com/spas-madzoon-yogurt-soup-with-grains/ |
| `sp-white-bean` | White bean soup with vegetables | soup | legume | new | — | | | Blend half the pot for him | | White beans (cans); Carrots; Onions; Olive oil | https://www.themediterraneandish.com/white-bean-soup/ |
| `sp-pumpkin` | Pumpkin soup | soup | veg | new | egg | | | | In season now | Pumpkin; Onions; Carrots; Olive oil | https://www.themediterraneandish.com/pumpkin-soup/ |
| `sp-greek-lentil` | Greek lentil soup (fakes) | soup | legume | new | — | | | Blend half the pot for him | Leave out the vinegar for Davit | Brown/green lentils; Carrots; Onions; Canned tomatoes | https://www.themediterraneandish.com/greek-lentil-soup-fakes/ |
| `sp-chickpea` | Greek chickpea soup | soup | legume | new | — | chickpea | Soak the chickpeas tonight (or use canned) | Blend half the pot for him | No lemon on Davit's bowl | Chickpeas (dry); Onions; Carrots; Olive oil | https://www.themediterraneandish.com/greek-chickpea-soup-revithosoupa/ |
| `sp-lentil-potato` | Lentil and potato soup | soup | legume | new | — | | | Blend half the pot for him | | Brown/green lentils; Potatoes; Carrots; Onions | https://www.themediterraneandish.com/lentil-potato-soup/ |
| `sp-turkish-lentil` | Turkish red lentil soup (mercimek) | soup | legume | new | — | | | Blend it smooth for him | Mild paprika only; skip the lemon for Davit | Red lentils; Carrots; Onions; Potatoes | https://www.themediterraneandish.com/turkish-lentil-soup/ |
| `sp-apricot-lentil` | Armenian red lentil soup with apricot | soup | legume | new | — | | | Blend it smooth for him | Dried apricots, no lemon for Davit | Red lentils; Dried apricots; Onions; Carrots | https://www.themediterraneandish.com/armenian-apricot-red-lentil-soup/ |

## Fish (twice a week)

| id | dish | slot | protein | status | side | group | prep | son | tip | buy | ref |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `ln-fish-bake` | Baked trout with vegetables | fish | fish | staple | grain | | | Check every bone | Lemon and paprika only on Karine's portion | Trout; Zucchini; Carrots; Olive oil | https://www.themediterraneandish.com/easy-baked-trout-recipe/ |
| `fs-mackerel-potato` | Canned mackerel with warm potatoes and herbs | fish | fish | staple | — | | | Mash it, check for bones | | Canned mackerel; Potatoes; Dill; Olive oil | |
| `fs-salmon-sheetpan` | Sheet-pan salmon with vegetables | fish | fish | new | grain | | | Check every bone | Salmon when it's affordable — trout works the same | Salmon; Zucchini; Bell peppers; Olive oil | https://www.themediterraneandish.com/sheet-pan-salmon-and-vegetables/ |
| `fs-trout-papillote` | Trout baked in parchment with herbs | fish | fish | new | grain | | | Check every bone | | Trout; Dill; Parsley; Olive oil | https://www.bbcgoodfood.com/recipes/trout-en-papillote |
| `fs-mackerel-roast` | Oven-roasted mackerel in foil | fish | fish | new | grain | | | Check every bone | No lemon on Davit's portion | Mackerel (fresh); Onions; Parsley; Olive oil | https://www.themediterraneandish.com/oven-roasted-spanish-mackerel/ |
| `fs-sardines` | Sardines on toast with tomato and herbs | fish | fish | new | — | | | Mash the sardines | Ten minutes — canned sardines | Canned sardines; Bread; Tomatoes; Parsley | https://www.bbcgoodfood.com/recipes/sardines-on-toast |
| `fs-baked-fish` | Baked white fish with garlic and herbs | fish | fish | new | grain | | | Check every bone | | White fish; Garlic; Parsley; Olive oil | https://www.themediterraneandish.com/baked-fish-recipe/ |

## Egg dinners

| id | dish | slot | protein | status | side | group | prep | son | tip | buy | ref |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `dn-omelette` | Omelette with spinach and greens, with salad | egg | egg | staple | — | | | No salt on his part | | Eggs; Spinach; Cucumbers; Tomatoes | |
| `dn-salad-egg` | Big salad with boiled eggs | egg | egg | staple | — | | | Egg quartered, soft vegetables | Olive oil and herbs, no lemon for Davit | Eggs; Cucumbers; Tomatoes; Parsley; Olive oil | |
| `dn-frittata` | Vegetable frittata from the oven | egg | egg | new | — | | | | | Eggs; Zucchini; Bell peppers; Spinach | https://www.themediterraneandish.com/vegetable-frittata/ |
| `dn-tortilla` | Spanish potato omelette (tortilla) | egg | egg | new | — | | | | Little oil; bake it if you prefer | Eggs; Potatoes; Onions; Olive oil | https://www.bbcgoodfood.com/recipes/spanish-tortilla |
| `dn-zucchini-fritters` | Zucchini fritters with a matsun dip | egg | egg | new | — | | | | Bake them instead of frying for Davit | Zucchini; Eggs; Dill; Matsun | https://www.themediterraneandish.com/zucchini-fritters/ |

## Light dinners

| id | dish | slot | protein | status | side | group | prep | son | tip | buy | ref |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `dn-matsun-bowl` | Matsun with cucumber and herbs, with boiled potato | light | dairy | staple | — | | | Cucumber grated | | Matsun; Cucumbers; Dill; Potatoes | |
| `dn-eetch` | Eetch — Armenian bulgur salad | light | grain | staple | egg | | | | Go easy on the tomato paste for Davit | Bulgur; Tomato paste; Parsley; Onions | https://www.armenianinstitute.org.uk/food/eetch |
| `dn-tabbouleh` | Tabbouleh — bulgur and herb salad | light | grain | new | egg | | | Herbs chopped very fine | Olive oil only — no lemon for Davit | Bulgur; Parsley; Cucumbers; Tomatoes; Olive oil | https://www.themediterraneandish.com/tabouli-salad/ |
| `dn-greek-salad` | Greek salad with a little feta | light | dairy | new | egg | | | Soft vegetables, cut small | Feta small for Davit | Tomatoes; Cucumbers; Bell peppers; Feta; Olive oil | https://www.themediterraneandish.com/traditional-greek-salad-recipe/ |
| `dn-potato-tzatziki` | Baked potato with tzatziki | light | dairy | new | egg | | | | Tzatziki made with matsun | Potatoes; Matsun; Cucumbers; Garlic | https://www.bbcgoodfood.com/recipes/tzatziki |

## Sides

Names are written in lower case: they follow a dish ("… + buckwheat").

| id | dish | slot | protein | status | side | group | prep | son | tip | buy | ref |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `sd-buckwheat` | buckwheat | side | grain | staple | — | | | | | Buckwheat | |
| `sd-bulgur` | bulgur pilaf | side | grain | staple | — | | | | | Bulgur | |
| `sd-barley` | pearl barley | side | grain | staple | — | | | | | Pearl barley | |
| `sd-salad` | green salad and a little lavash | side | veg | staple | — | | | | | Cucumbers; Tomatoes; Parsley; Lavash | |
| `sd-egg` | a boiled egg | side | egg | staple | — | | | | | Eggs | |
| `sd-matsun` | matsun | side | dairy | staple | — | | | | | Matsun | |

## Weekend project

| id | dish | slot | protein | status | side | group | prep | son | tip | buy | ref |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `wk-scoolinary` | Scoolinary project — the planned treat | project | — | staple | — | | | His own small portion | Davit's queue: pizza → croissants → chocolate | | |

## Used only by week 1

| id | dish | slot | protein | status | side | group | prep | son | tip | buy | ref |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `ln-buckwheat` | buckwheat | — | grain | staple | — | | | | | Buckwheat | |
| `ln-bulgur` | bulgur pilaf with vegetables | — | grain | staple | — | | | | | Bulgur | https://thearmeniankitchen.com/bulgur-pilaf-with-onions-and-tomato/ |
| `dn-soup-blend` | Blended soup from the batch pot | — | veg | staple | — | | | | | | |
| `dn-leftover` | Leftover lunch, small portion, with salad | — | — | staple | — | | | | | | |
