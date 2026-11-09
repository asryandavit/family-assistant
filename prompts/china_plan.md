A family member in Yerevan wants to buy something in China (Pinduoduo, Taobao, 1688). Turn their
description into a search plan. Do not browse. Do not invent prices or numbers.

Answer with ONE JSON object and nothing else:
{"query_cn": "<a short Chinese search query, 2–6 words, the way Chinese shoppers search>",
 "query_en": "<a short English restatement of what they want>",
 "category": "electronics|clothes|shoes|home|beauty|kids|other",
 "vague": true|false,
 "questions": [{"q": "<short English question>", "options": ["<2–4 short answers>"]}]}

"vague" is true only when an important choice is missing that changes what to search
(e.g. clothes without a size or gender, "a charger" without the power or device, "a phone"
without a budget). Then give 1–2 questions with 2–4 short options each (for example budget
bands, size, colour, "brand only?"). Otherwise vague=false and questions=[].

Description: {description}
