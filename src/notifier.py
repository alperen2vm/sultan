"""Telegram'a bildirim gönderme."""

import html
import os

import requests

EMOJI = {
    "konser": "\U0001F3A4",     # mikrofon
    "etkinlik": "\U0001F389",   # konfeti
    "resmi": "\U0001F3DB",      # resmi bina
    "haber": "\U0001F4F0",      # gazete
    "diger": "\U0001F4CC",      # raptiye
}


def send(item: dict) -> bool:
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    emoji = EMOJI.get(item.get("kategori", "diger"), EMOJI["diger"])
    title = html.escape(item["title"])
    ozet = html.escape(item.get("ozet", ""))
    source = html.escape(item["source"])

    text = (
        f"{emoji} <b>{title}</b>\n\n"
        f"{ozet}\n\n"
        f"Puan: {item.get('puan', '?')}/10 | Kaynak: {source}\n"
        f"{item['link']}"
    )

    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
        timeout=20,
    )
    ok = resp.ok and resp.json().get("ok", False)
    if not ok:
        print(f"[TELEGRAM HATA] {resp.status_code}: {resp.text[:200]}")
    return ok
