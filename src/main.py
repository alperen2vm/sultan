"""Münih Radar — ana akış.

Akış: kaynakları tara -> dedup -> keyword prefilter -> LLM puanla -> Telegram'a gönder

Çalıştırma:
    python -m src.main                  # normal tarama
    python -m src.main --test-sources   # sadece kaynakları test et (LLM/Telegram yok)
    python -m src.main --dry-run        # her şeyi yap ama Telegram'a gönderme
"""

import sys
from pathlib import Path

import yaml

from src import classifier, fetchers, notifier, prefilter, state

MIN_SCORE = 6  # bu puanın altındakiler Telegram'a düşmez


def load_config():
    sources = yaml.safe_load(Path("config/sources.yml").read_text())["sources"]
    keywords = yaml.safe_load(Path("config/keywords.yml").read_text())["keywords"]
    return sources, keywords


def main():
    test_only = "--test-sources" in sys.argv
    dry_run = "--dry-run" in sys.argv

    sources, keywords = load_config()

    # 1. Tara
    items = fetchers.fetch_all(sources)
    if test_only:
        print(f"\n[TEST] Toplam {len(items)} item çekildi. Kaynak testi bitti.")
        return

    # 2. Dedup
    seen = state.load()
    items = state.filter_new(items, seen)

    # 3. Prefilter
    candidates = prefilter.apply(items, keywords)

    # 4. LLM sınıflandırma
    winners = classifier.classify_all(candidates, min_score=MIN_SCORE)
    print(f"[SONUÇ] {len(winners)} item eşiği geçti")

    # 5. Telegram + state güncelle
    # Not: sadece LLM'e giden adayları değil, TÜM yeni item'ları seen'e
    # yazıyoruz — düşük puanlılar bir daha değerlendirilmesin diye.
    for it in winners:
        if dry_run:
            print(f"[DRY-RUN] Gönderilecekti: {it['title'][:70]}")
        else:
            notifier.send(it)

    for it in items:
        seen.add(state.item_id(it))
    state.save(seen)
    print("[BİTTİ]")


if __name__ == "__main__":
    main()
