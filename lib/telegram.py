"""Telegram transport: HTML messages, auto-split, silent mode.

HTML parse mode on purpose -- MarkdownV2 requires escaping . - ( ) ! and our
data is nothing but prices and dates, so one missed escape kills a message.
notify() stays plain-text for errors/system lines (backward compatible).
"""
import html
import json
import os
import re

import requests

LIMIT = 3900  # headroom under Telegram's 4096


def esc(s):
    return html.escape(str(s), quote=False)


# Set by the listener for a job it launches on someone's behalf (/price, /flights,
# /stays), so the job's own messages go back to the person who asked. Unset for
# scheduled jobs, which keep sending to the owner's chat exactly as before.
REPLY_CHAT_ENV = "TELEGRAM_REPLY_CHAT_ID"


def _creds(cfg, reply=True):
    """(token, chat). reply=False always means the owner's chat (system messages)."""
    tok = os.environ.get(cfg["telegram"]["bot_token_env"])
    owner = os.environ.get(cfg["telegram"]["chat_id_env"])
    chat = (os.environ.get(REPLY_CHAT_ENV) or owner) if reply else owner
    return tok, chat


def allowed_chats(cfg):
    """Chats the bot answers: the owner's, plus the second family member's when
    its environment variable is set (decision 082). Owner first, no duplicates."""
    tg = cfg["telegram"]
    out = []
    for env in (tg["chat_id_env"], tg.get("chat_id_2_env", "TELEGRAM_CHAT_ID_2")):
        v = str(os.environ.get(env) or "").strip()
        if v and v not in out:
            out.append(v)
    return out


def _post(tok, payload):
    try:
        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                      data=payload, timeout=20)
    except requests.RequestException as e:
        print("Telegram send failed:", e)


def _split(text):
    """Split at line breaks under LIMIT. A folded <blockquote> that straddles a
    split is closed at the end of one chunk and reopened at the start of the
    next, so each chunk stays valid HTML (Telegram rejects unbalanced tags)."""
    if len(text) <= LIMIT:
        return [text]
    parts, cur, open_tag = [], "", None
    for line in text.split("\n"):
        if cur and len(cur) + len(line) + 1 > LIMIT - 40:   # room for a closing tag
            if open_tag:
                cur += "</blockquote>"
            parts.append(cur)
            cur = (open_tag + line) if open_tag else line
        else:
            cur = f"{cur}\n{line}" if cur else line
        for tag in re.findall(r"<blockquote[^>]*>|</blockquote>", line):
            open_tag = None if tag == "</blockquote>" else tag
    if cur:
        parts.append(cur)
    return parts


def _button(label, data):
    """Inline button: a URL opens a link, {"web_app": url} opens the Mini App at
    that https URL inside Telegram, anything else is callback_data."""
    if isinstance(data, dict) and "web_app" in data:
        return {"text": label, "web_app": {"url": str(data["web_app"])}}
    if str(data).startswith(("https://", "http://")):
        return {"text": label, "url": data}
    return {"text": label, "callback_data": data}


def reply_markup(buttons=None, reply_keyboard=None, force_reply=None):
    """reply_markup JSON for a message, or None.

    buttons:        inline rows [(label, callback_data_or_url_or_{"web_app": url}), ...]
    reply_keyboard: persistent bottom keyboard rows [label, ...]
    force_reply:    placeholder text; opens a reply prompt for the next message
    A message carries one kind; inline buttons win, then keyboard, then prompt.
    """
    if buttons:
        return json.dumps({"inline_keyboard": [[_button(lab, data) for lab, data in row]
                                               for row in buttons]})
    if reply_keyboard:
        return json.dumps({"keyboard": [[{"text": lab} for lab in row] for row in reply_keyboard],
                           "is_persistent": True, "resize_keyboard": True})
    if force_reply is not None:
        return json.dumps({"force_reply": True, "input_field_placeholder": str(force_reply)[:64]})
    return None


def send_html(cfg, text, silent=False, buttons=None, reply_keyboard=None, force_reply=None,
              chat_id=None):
    """buttons: list of rows, each a list of (label, callback_data) pairs; a
    https:// value makes a link button. reply_keyboard / force_reply: see
    reply_markup(). chat_id: send to this chat instead of the default."""
    tok, chat = _creds(cfg)
    chat = chat_id or chat
    if not tok or not chat:
        print("Telegram env not set; skipping:", text[:80])
        return
    chunks = _split(text)
    for i, chunk in enumerate(chunks):
        payload = {"chat_id": chat, "text": chunk, "parse_mode": "HTML",
                   "disable_web_page_preview": True,
                   "disable_notification": silent}
        # keyboard rides on the final chunk so it sits under the whole message
        if i == len(chunks) - 1:
            markup = reply_markup(buttons, reply_keyboard, force_reply)
            if markup:
                payload["reply_markup"] = markup
        _post(tok, payload)


RICH_URL = "https://api.telegram.org/bot%s/sendRichMessage"


def send_rich(cfg, rich_html, fallback_html=None, silent=True, buttons=None, chat_id=None,
              post=None):
    """Send a Telegram Rich Message (Bot API 10.1+, `rich_message.html`) and return
    ("rich", message_id). If Telegram refuses it (an error, a limit, a tag it doesn't know),
    send fallback_html with send_html() and return ("plain", None); with no fallback,
    ("failed", None). A rich message carries its buttons inside the HTML (<tg-button>);
    `buttons` is only for the plain fallback. Additive: send_html() is unchanged.
    Format notes (seen 2026-11-09): a newline is a space -> use <br>; buttons use data=."""
    tok, chat = _creds(cfg)
    chat = chat_id or chat
    if not tok or not chat:
        print("Telegram env not set; skipping rich:", rich_html[:80])
        return "failed", None
    post = post or requests.post
    why = ""
    try:
        r = post(RICH_URL % tok, json={"chat_id": chat, "rich_message": {"html": rich_html},
                                        "disable_notification": silent}, timeout=30)
        d = r.json()
        if d.get("ok"):
            return "rich", (d.get("result") or {}).get("message_id")
        why = str(d.get("description") or d)[:160]
    except (requests.RequestException, ValueError) as e:
        why = str(e)[:160]
    print("Telegram rich send failed:", why)
    if fallback_html:
        send_html(cfg, fallback_html, silent=silent, buttons=buttons, chat_id=chat)
        return "plain", None
    return "failed", None


def send_family(cfg, text, **kw):
    """Send to every allowed chat (family content: daily plan, shopping list)."""
    for chat in allowed_chats(cfg):
        send_html(cfg, text, chat_id=chat, **kw)


def chat_action(cfg, action="typing", chat_id=None):
    """Show "typing…" (lasts ~5 s or until the next message)."""
    tok, chat = _creds(cfg)
    chat = chat_id or chat
    if not tok or not chat:
        return
    try:
        requests.post("https://api.telegram.org/bot%s/sendChatAction" % tok,
                      data={"chat_id": chat, "action": action}, timeout=10)
    except requests.RequestException:
        pass


def answer_callback(cfg, callback_id, text=""):
    """Stop the spinner on a tapped button."""
    tok, _ = _creds(cfg)
    if not tok:
        return
    try:
        requests.post("https://api.telegram.org/bot%s/answerCallbackQuery" % tok,
                      data={"callback_query_id": callback_id, "text": text[:200]},
                      timeout=15)
    except requests.RequestException:
        pass


def notify(cfg, text):
    """Plain-text send, kept for system/error messages and old callers.
    Always the owner's chat: system problems are for the owner only."""
    tok, chat = _creds(cfg, reply=False)
    if not tok or not chat:
        print("Telegram env not set; skipping notify:", text[:80])
        return
    for chunk in _split(text):
        _post(tok, {"chat_id": chat, "text": chunk,
                    "disable_web_page_preview": True})


def _markup(buttons):
    return json.dumps({"inline_keyboard": [[_button(lab, data) for lab, data in row]
                                           for row in buttons]})


def edit_markup(cfg, chat_id, message_id, buttons):
    """Swap a message's keyboard without resending it."""
    tok, _ = _creds(cfg)
    if not tok:
        return
    try:
        requests.post("https://api.telegram.org/bot%s/editMessageReplyMarkup" % tok,
                      data={"chat_id": chat_id, "message_id": message_id,
                            "reply_markup": _markup(buttons)}, timeout=15)
    except requests.RequestException:
        pass


def edit_html(cfg, chat_id, message_id, text, buttons=None):
    tok, _ = _creds(cfg)
    if not tok:
        return
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text,
               "parse_mode": "HTML", "disable_web_page_preview": True}
    if buttons is not None:
        payload["reply_markup"] = _markup(buttons)
    try:
        requests.post("https://api.telegram.org/bot%s/editMessageText" % tok,
                      data=payload, timeout=15)
    except requests.RequestException:
        pass
