A family member in Yerevan wants to buy something on Amazon UK, Amazon Germany and Amazon Italy
(it will be shipped to a forwarder's warehouse). Turn their description into a search plan.
Do not browse. Do not invent prices, sizes in numbers you are not sure of, or any other number.

Answer with ONE JSON object and nothing else:
{"query_en": "<short English search words, 2–7 words>",
 "queries": {"uk": "<English words as a UK shopper types them>",
             "de": "<the same search in German, the way Germans type it into Amazon.de>",
             "it": "<the same search in Italian, the way Italians type it into Amazon.it>"},
 "category": "electronics|clothes|baby|home|beauty|toys|other",
 "vague": true|false,
 "questions": [{"q": "<short English question>", "options": ["<2–4 short answers>"]}]}

Rules for the queries: 2–7 words, no brand unless the person named one, keep numbers exactly as
the person typed them (65W stays 65W; do not convert or calculate anything). Keep the unit
words the stores use ("usb c ladegerät 65w", "caricatore usb c 65w").

Clothing for babies and children: Amazon sizes differ by country. When the person gave an age,
use these fixed equivalents in the German and Italian queries (do not compute others):
  0-3 months: DE "Größe 56 62", IT "0-3 mesi"      3-6 months: DE "Größe 62 68", IT "3-6 mesi"
  6-9 months: DE "Größe 68 74", IT "6-9 mesi"      6-12 months: DE "Größe 74 80", IT "6-12 mesi"
  9-12 months: DE "Größe 74 80", IT "9-12 mesi"    12-18 months: DE "Größe 80 86", IT "12-18 mesi"
  18-24 months: DE "Größe 86 92", IT "18-24 mesi"
UK keeps the age in English ("6-12 months").

"vague" is true only when ONE important choice is missing that changes what to search - for
clothing the child's age or size, for a charger the power or device. Then give exactly ONE
question with 2–4 short options (for baby clothes: the age bands above, "0-3 months",
"3-6 months", "6-12 months", "12-24 months"). Otherwise vague=false and questions=[].

Description: {description}
