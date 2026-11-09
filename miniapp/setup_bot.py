"""Set, check or remove the 🏠 Family chat menu button (docs/briefs/MINI_APP.md §1, §4).

    python -m miniapp.setup_bot            set it in every allowed person's chat
    python -m miniapp.setup_bot --check    show what each chat has now (changes nothing)
    python -m miniapp.setup_bot --remove   back to Telegram's default menu button

The button opens machine.json `miniapp_public_url` inside Telegram. Chats come from
miniapp.people (in a private chat the chat id equals the user id). Ids are printed masked;
the token is never printed (a requests error message would contain it, so only the error
type is shown).
"""
import argparse
import json
import sys

import requests

from miniapp import bot_token, load_config, people, public_url

API = "https://api.telegram.org/bot{}/{}"


def menu_button(text, url):
    return {"type": "web_app", "text": text, "web_app": {"url": url}}


def call(token, method, payload, post=None):
    """Bot API call -> (ok, result_or_description). Never raises, never echoes the token."""
    post = post or requests.post
    try:
        r = post(API.format(token, method), json=payload, timeout=20)
        d = r.json()
    except (requests.RequestException, ValueError) as e:
        return False, type(e).__name__
    if d.get("ok"):
        return True, d.get("result")
    return False, str(d.get("description") or "error")[:160]


def is_set(result, text, url):
    return (isinstance(result, dict) and result.get("type") == "web_app"
            and result.get("text") == text and (result.get("web_app") or {}).get("url") == url)


def check_all(cfg, token, url, post=None):
    """[(person, ok, detail)] for every allowed person's chat."""
    out = []
    for p in people.load(cfg).values():
        ok, res = call(token, "getChatMenuButton", {"chat_id": p.user_id}, post)
        if not ok:
            out.append((p, False, res))
        elif url and is_set(res, cfg["menu_button_text"], url):
            out.append((p, True, "set"))
        else:
            out.append((p, False, "is " + str((res or {}).get("type", "?"))))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--remove", action="store_true")
    g.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)

    cfg = load_config()
    token = bot_token()
    if not token:
        print("TELEGRAM_BOT_TOKEN is not set (docs/SECRETS.md #1).")
        return 2
    url = public_url()
    persons = list(people.load(cfg).values())
    if not persons:
        print("No people: TELEGRAM_CHAT_ID is not set.")
        return 2

    if args.check:
        bad = 0
        for p, ok, detail in check_all(cfg, token, url):
            print(f"{p.name:<8} {p.role:<6} {people.mask(p.user_id)}: {detail}")
            bad += not ok
        return 1 if bad else 0

    if not args.remove and not url:
        print("machine.json miniapp_public_url is missing or not https:// "
              "(docs/SECRETS.md, Mini App).")
        return 2
    button = {"type": "default"} if args.remove else menu_button(cfg["menu_button_text"], url)
    bad = 0
    for p in persons:
        ok, res = call(token, "setChatMenuButton",
                       {"chat_id": p.user_id, "menu_button": button})
        result = ("removed" if args.remove else "set") if ok else f"FAILED ({res})"
        print(f"{p.name:<8} {p.role:<6} {people.mask(p.user_id)}: {result}")
        bad += not ok
    if not args.remove:
        print("Button:", json.dumps(cfg["menu_button_text"], ensure_ascii=False))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
