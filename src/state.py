"""Görülen içeriklerin kaydı (dedup).

Aynı haberi her taramada tekrar göndermemek için link hash'lerini
data/seen.json'da tutuyoruz. GitHub Actions her çalışmadan sonra bu
dosyayı repo'ya geri commit'liyor — böylece state bedavaya kalıcı oluyor.
"""

import hashlib
import json
from pathlib import Path

STATE_FILE = Path("data/seen.json")
MAX_ENTRIES = 5000  # dosya sonsuza kadar büyümesin


def item_id(item: dict) -> str:
    return hashlib.sha256(item["link"].encode()).hexdigest()[:16]


def load() -> set[str]:
    if STATE_FILE.exists():
        return set(json.loads(STATE_FILE.read_text()))
    return set()


def save(seen: set[str]) -> None:
    trimmed = list(seen)[-MAX_ENTRIES:]
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(trimmed, indent=0))


def filter_new(items: list[dict], seen: set[str]) -> list[dict]:
    new_items = [it for it in items if item_id(it) not in seen]
    print(f"[DEDUP] {len(items)} -> {len(new_items)} yeni item")
    return new_items
