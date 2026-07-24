"""Telegram transport: HTML messages, auto-split, silent mode.

HTML parse mode on purpose -- MarkdownV2 requires escaping . - ( ) ! and our
data is nothing but prices and dates, so one missed escape kills a message.
notify() stays plain-text for errors/system lines (backward compatible).
"""
import html
import json
import os

import requests

LIMIT = 3900  # headroom under Telegram's 4096


def esc(s):
    return html.escape(str(s), quote=False)


def _creds(cfg):
    tok = os.environ.get(cfg["telegram"]["bot_token_env"])
    chat = os.environ.get(cfg["telegram"]["chat_id_env"])
    return tok, chat


def _post(tok, payload):
    try:
        requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                      data=payload, timeout=20)
    except requests.RequestException as e:
        print("Telegram send failed:", e)


def _split(text):
    if len(text) <= LIMIT:
        return [text]
    parts, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > LIMIT:
            parts.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        parts.append(cur)
    return parts


def send_html(cfg, text, silent=False, buttons=None):
    """buttons: list of rows, each a list of (label, callback_data) pairs."""
    tok, chat = _creds(cfg)
    if not tok or not chat:
        print("Telegram env not set; skipping:", text[:80])
        return
    chunks = _split(text)
    for i, chunk in enumerate(chunks):
        payload = {"chat_id": chat, "text": chunk, "parse_mode": "HTML",
                   "disable_web_page_preview": True,
                   "disable_notification": silent}
        # keyboard rides on the final chunk so it sits under the whole message
        if buttons and i == len(chunks) - 1:
            payload["reply_markup"] = json.dumps({"inline_keyboard": [
                [{"text": lab, "callback_data": data} for lab, data in row]
                for row in buttons]})
        _post(tok, payload)


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
    """Plain-text send, kept for system/error messages and old callers."""
    tok, chat = _creds(cfg)
    if not tok or not chat:
        print("Telegram env not set; skipping notify:", text[:80])
        return
    for chunk in _split(text):
        _post(tok, {"chat_id": chat, "text": chunk,
                    "disable_web_page_preview": True})


def _markup(buttons):
    return json.dumps({"inline_keyboard": [
        [{"text": lab, "callback_data": data} for lab, data in row]
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
