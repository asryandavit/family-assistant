# Basket — how the shopping list is priced

`jobs/grocery_basket.py` (🧺 **Basket** in Telegram, Shopping section, or `/basket`) prices
every row below at Yerevan City and Parma, picks the cheaper shop per item, writes the
**Shopping list** Google Sheet (tick boxes on the phone) and sends the per-shop list to
both of us. This table is the only thing it reads — `shopping.md` stays the human plan;
the amounts here are how its free-text amounts were read (edit any row any time).

**Columns**
- **List** — `weekly` (Sunday fresh) or `monthly` (staples).
- **Search** — the words sent to both shops' search (one search per distinct text).
- **Match** — words the product name must contain, as in `/price` (the
  [word list](grocery-words.md) applies: `katnashor` also matches *curd* and *cottage
  cheese*). Alternatives are separated by `;` — a product may match either.
- **Qty / Unit** — `kg` or `l` (weight or volume: packages are rounded **up** to whole
  packages, items sold by weight respect the shop's minimum order), `pcs` (pieces, e.g.
  eggs — counted from "10pcs" in the name), `pack` (whole packs, bunches or cans; the
  cheapest pack is taken). `skip` = not priced (listed as skipped).
- **Exclude** — words that rule a product out (pomace oil, snacks, juices, seeds…).
- **Shop** — optional `yc` or `parma`: use that shop whenever it has a match.

A product counts when the item's type is among the first two words of its name
("Cucumber (russian) kg", "Canned mackerel…"), so "Cat food … trout" is never trout. A
package up to 10% under the amount is enough (950 g for 1 kg). Per shop the **cheapest
line cost** wins — sometimes that means a shop's minimum order (garlic by 0.3 kg) or a
bigger pack; the Buy column always says exactly what to put in the cart. An item with no
matching product is shown as **no match** and left out of the totals — a price is never
guessed.

## Monthly staples

| List | Item | Search | Match | Qty | Unit | Exclude | Shop | Note |
|---|---|---|---|---|---|---|---|---|
| monthly | Rolled oats (hercules) | oat flakes | oat flakes | 3.5 | kg | bran | | plan: 3–4 kg |
| monthly | Red lentils | lentils | red lentils | 2 | kg | pasta, chips, soup | | |
| monthly | Brown/green lentils | lentils | lentils | 1 | kg | red, pasta, chips, soup | | |
| monthly | White beans (cans) | beans | white beans | 6 | pack | tomato, sauce | | plan: 1–2 kg dry or 6–8 cans; dry white beans aren't named as such |
| monthly | Chickpeas (dry) | chickpeas | chickpeas | 1 | kg | salt, canned, flour, pasta, hummus, chips | | |
| monthly | Buckwheat | buckwheat | buckwheat | 2 | kg | bread, flakes, flour, noodles, porridge, honey | | |
| monthly | Bulgur | bulgur | bulgur | 2 | kg | | | |
| monthly | Rice (for dolma) | rice | rice | 1 | kg | noodles, paper, flour, vinegar, cakes, crackers, milk, porridge, pudding, chips | | |
| monthly | Olive oil | olive oil | olive oil | 2 | l | pomace, pomance, sansa, sunflower, sloboda, spray | | plan: 2 × 1 L; "Sloboda" is a sunflower–olive blend |
| monthly | Canned mackerel | mackerel | mackerel | 5 | pack | smoked, salted, kg | | plan: 4–6 cans (mackerel or sardines) |
| monthly | Walnuts (unsalted) | walnuts | walnuts | 0.5 | kg | wafer, waffle, preserve, salad, humus, sujukh, unpeeled, chocolate, cake, pastry, condensed | | |
| monthly | Tomato paste | tomato paste | tomato paste | 1 | kg | | | plan: 2 jars |
| monthly | Canned tomatoes | tomatoes | tomatoes own juice; tomatoes peeled | 4 | pack | | | |
| monthly | Spices | | | skip | | | | as needed |
| monthly | Lactose-free milk (UHT) | lactose free milk | lactose free milk | 7 | l | mortadella, chocolate, cocoa, baked, condensed | | plan: 6–8 L |
| monthly | Frozen broccoli | frozen broccoli | broccoli | 2 | pack | | | frozen veg plan: 4–6 bags |
| monthly | Frozen green beans | frozen green beans | green beans frozen | 1 | pack | | | |
| monthly | Frozen peas | frozen peas | peas frozen; green peas frozen | 1 | pack | canned | | |
| monthly | Frozen mixed vegetables | frozen vegetables | vegetable frozen | 1 | pack | | | |
| monthly | Lavash | lavash | lavash | 1.5 | kg | spinach, chips, khash | | plan: several packs, freeze |
| monthly | Honey (small) | honey | honey | 0.25 | kg | cake, bar, gingerbread, layers, artificial, royal, jelly, cookies, beeswax, pastry | | plan: 1 small jar |
| monthly | Coffee | | | skip | | | | as you drink it |

## Weekly fresh

| List | Item | Search | Match | Qty | Unit | Exclude | Shop | Note |
|---|---|---|---|---|---|---|---|---|
| weekly | Eggs | eggs | eggs | 20 | pcs | noodle, noodles, separator, quail, chocolate, holder, boiler, cooker, easter, decorative | | plan: ~20 |
| weekly | Katnashor (tvorog) | katnashor | katnashor | 0.8 | kg | dessert, glazed, chocolate, cheesecake, bar, syrniki, vanilla, raisins, cream, snack | | plan: 2–3 packs |
| weekly | Matsun | matsun | matsun | 1 | kg | drink, tan, dried | | plan: 2 |
| weekly | Whole milk (son) | milk | milk 3.2% | 2.5 | l | lactose, shake, jelly, face, condensed, powder, coconut, almond, soy, oat, baked, chocolate, cocoa, goat, banana, strawberry, cream, body, cleansing | | plan: 2–3 L |
| weekly | Chicken thighs | chicken | chicken thigh | 1 | kg | smoked, grilled, boiled, cooked | | plan: chicken 1.5–2 kg in all |
| weekly | Chicken breast | chicken breast | chicken breast | 0.75 | kg | pilaf, smoked, salad, sausage, ham, nuggets | | |
| weekly | Trout | trout | trout | 0.6 | kg | liver, caviar, smoked, oil, salted, pate, dried | | plan: trout or mackerel ~0.6 kg |
| weekly | Tomatoes | tomatoes | tomatoes | 1 | kg | paste, peeled, juice, own, sauce, ketchup, dried, sun, canned, pickled, marinated | | plan: tomatoes + cucumbers 2 kg |
| weekly | Cucumbers | cucumbers | cucumbers | 1 | kg | marinade, pickled, salted, marinated, canned | | |
| weekly | Onions | onions | onions | 1 | kg | shallot, porey, leek, medicinal, salad, green, fried, chips, rings | | plan: onions + carrots + potatoes 3–4 kg |
| weekly | Carrots | carrots | carrots | 1 | kg | cake, juice, salad, mini, korean | | |
| weekly | Potatoes | potatoes | potatoes | 2 | kg | starch, dumplings, gnocchi, sweet, chips, fries, puree, frozen, beets, mashed | | |
| weekly | Zucchini | zucchini | zucchini | 1 | kg | fried, puree, salad, risotto, caviar | | plan: zucchini / peppers / cabbage 2 kg |
| weekly | Bell peppers | pepper | sweet pepper | 0.5 | kg | marinated, stuffed, chilli, caviar, sauce | | |
| weekly | Cabbage | cabbage | cabbage | 0.5 | kg | red, chinese, brussels, iceberg, decor, sauerkraut, salad, pickled, marinated, sea | | a shop's minimum order may be a whole head |
| weekly | Parsley | parsley | parsley | 1 | pack | seeds, ground, dried, spice, salad, sauce, frozen | | greens: 4–5 bunches |
| weekly | Coriander | coriander | coriander | 1 | pack | seeds, ground, dried, spice, pesto, pumperniickel, sauce | | |
| weekly | Dill | dill | dill | 1 | pack | seeds, dried, kefir, salad, cutlets, cheese, potatoes, crispbreads, sauce | | |
| weekly | Spinach | spinach | spinach | 1 | pack | frozen, lavash, salad, quinoa | | |
| weekly | Apples | apples | apples | 1.5 | kg | vinegar, juice, chips, dried, puree, nectar, jam, cake, pie, strudel, sauce | | fruit: 3–4 kg |
| weekly | Bananas | bananas | bananas | 1 | kg | chocolate, mini, juice, nectar, chips, puree | | |
| weekly | Pears | pears | pears | 1 | kg | juice, nectar, puree, dried, jam | | |
| weekly | Garlic | garlic | garlic | 0.1 | kg | powder, granules, dried, sauce, bread, pickled, marinated, salt, chips | | plan: 1 head |
| weekly | Scoolinary project ingredients | | | skip | | | | per recipe |
