Read the buyer reviews of ONE listing and summarise them. Same hard rules as always: read
only, never type, never log in, never solve a check (answer status "check" or "login").

SETUP: list_connected_browsers, select_browser with the Windows browser's deviceId, create your
own tab (tabs_context_mcp createIfEmpty), close it at the end.

{site_steps}

Answer with ONE JSON object and nothing else:
{"id": "{item_id}", "status": "ok|login|check|error", "review_count_text": "<as shown>",
 "liked": ["<2–3 short English points>"], "complaints": ["<2–3 short English points>"],
 "size_advice": null}
Do not copy reviewer names. size_advice only for clothes/shoes (runs small / large, from the
reviews).
