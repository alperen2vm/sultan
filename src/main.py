"""Münih Radar — ana akış.

Akış: kaynakları tara -> dedup -> keyword prefilter -> LLM puanla -> Telegram'a gönder

Çalıştırma:
    python -m src.main                  # normal tarama (haber + duyuru)
    python -m src.main --concerts       # sanatçı listesinden konser taraması
    python -m src.main --test-sources   # sadece kaynakları test et (LLM/Telegram yok)
    python -m src.main --dry-run        # her şeyi yap ama Telegram'a gönderme
    python -m src.main --ping           # sadece Telegram bağlantısını test et
"""

import sys
from pathlib import Path

import yaml

from src import classifier, concerts, fetchers, notifier, prefilter, state

MIN_SCORE = 4  # bu puanın altındakiler Telegram'a düşmez (başlangıç: bol aday)


def load_config():
    sources = yaml.safe_load(Path("config/sources.yml").read_text())["sources"]
    # keywords.yml artık gruplu: {"default": [...], "turkey_major": [...]}
    keyword_groups = yaml.safe_load(Path("config/keywords.yml").read_text())
    return sources, keyword_groups


def main():
    test_only = "--test-sources" in sys.argv
    dry_run = "--dry-run" in sys.argv
    concerts_mode = "--concerts" in sys.argv

    if "--ping" in sys.argv:
        ok = notifier.send_text("✅ Radar bağlantı testi — bu mesajı görüyorsan Telegram tarafı sağlam.")
        print("[PING]", "OK" if ok else "BAŞARISIZ")
        sys.exit(0 if ok else 1)

    sources, keyword_groups = load_config()

    # 1. Tara
    if concerts_mode:
        artists = yaml.safe_load(Path("config/artists.yml").read_text())["artists"]
        items = concerts.fetch_all(artists)
    else:
        items = fetchers.fetch_all(sources)
    if test_only:
        print(f"\n[TEST] Toplam {len(items)} item çekildi. Kaynak testi bitti.")
        return

    # 1.5 Tarama içi dedup: aynı link iki feed'den gelirse teke indir
    unique, seen_links = [], set()
    for it in items:
        if it["link"] not in seen_links:
            unique.append(it)
            seen_links.add(it["link"])
    items = unique

    # 2. Dedup
    seen = state.load()
    items = state.filter_new(items, seen)

    # 3. Prefilter
    candidates = prefilter.apply(items, keyword_groups)

    # 4. LLM sınıflandırma (toplu)
    winners, evaluated, hard_failed, quota_hit = classifier.classify_all(
        candidates, min_score=MIN_SCORE)
    deferred = [c for c in candidates if c not in evaluated]
    print(f"[SONUÇ] {len(winners)} item eşiği geçti "
          f"({len(evaluated)} değerlendirildi, {hard_failed} hata, "
          f"{len(deferred)} ertelendi)")

    # 5. Telegram + state güncelle
    # Not: sadece LLM'e giden adayları değil, TÜM yeni item'ları seen'e
    # yazıyoruz — düşük puanlılar bir daha değerlendirilmesin diye.
    sent_ok = 0
    send_attempts = 0
    for it in winners:
        if dry_run:
            print(f"[DRY-RUN] Gönderilecekti: {it['title'][:70]}")
        else:
            send_attempts += 1
            if notifier.send(it):
                sent_ok += 1

    deferred_links = {c["link"] for c in deferred}
    to_remember = [it for it in items if it["link"] not in deferred_links]
    state.mark_seen(seen, to_remember)
    state.save(seen)

    # Günlük kalp atışı: konser taraması günde bir çalıştığı için oraya
    # bağlı — her gün EN AZ bir mesaj garantisi. Gelmiyorsa sistem
    # bozuktur ve run kırmızı yanar; "sessiz ölüm" artık imkansız.
    if concerts_mode and not dry_run:
        heartbeat = ("📡 Günlük radar raporu: sistem çalışıyor.\n"
                     f"Konser taraması: {len(items)} yeni bulgu, "
                     f"{sent_ok} bildirim gönderildi.")
        if not notifier.send_text(heartbeat):
            print("[HATA] Kalp atışı gönderilemedi — TELEGRAM_BOT_TOKEN / "
                  "TELEGRAM_CHAT_ID kontrol edilmeli")
            sys.exit(1)

    # Sessiz ölüm koruması: toplu hata varsa run KIRMIZI yansın ki
    # Actions listesinde anında görülsün.
    if quota_hit:
        print("[UYARI] Günlük LLM kotası doldu — sistem sağlıklı, "
              "ertelenen adaylar kota yenilenince işlenecek")
    if len(evaluated) > 0 and hard_failed == len(evaluated):
        print("[HATA] Tüm LLM çağrıları kota dışı nedenle başarısız — "
              "GEMINI_API_KEY geçersiz olabilir")
        sys.exit(1)
    if send_attempts > 0 and sent_ok == 0:
        print("[HATA] Hiçbir Telegram mesajı iletilemedi — bot'a Start'a "
              "bastığından ve token/chat_id doğruluğundan emin ol")
        sys.exit(1)
    print("[BİTTİ]")


if __name__ == "__main__":
    main()
