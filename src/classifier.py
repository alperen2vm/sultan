"""LLM sınıflandırması — TOPLU (batch) mimari.

Neden batch: Ücretsiz Gemini kotası günlük istek SAYISINA göre çalışır.
Eski mimari her adayı ayrı çağrıyla puanlıyordu (günde ~2.000 istek =
kota patlaması ve 429 hataları). Yeni mimari bir taramanın tüm
adaylarını TEK istekte puanlatır (günde ~75 istek = her kotaya sığar).

429 (kota) davranışı: 20 sn bekle, bir kez daha dene; hâlâ 429 ise
kalan adayları "ertelendi" olarak bildir — main bunları seen'e YAZMAZ,
böylece kota yenilenince (her sabah) kaldıkları yerden işlenirler.

Tüm LLM mantığı bu dosyada izole — model değiştirmek istersen sadece
_call_gemini() fonksiyonunu değiştir.
"""

import json
import os
import time

import requests

GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)
BATCH_SIZE = 12       # tek istekte en fazla bu kadar aday puanlanır
RETRY_WAIT_S = 20     # 429 sonrası bekleme

PROMPT_HEADER = """Sen Münih'te yaşayan Türk toplumu için çalışan bir içerik filtresisin.
Aşağıda numaralandırılmış içerikler var. HER BİRİNİ ayrı ayrı puanla.

Puanlama rehberi:
- 9-10: Doğrudan ve önemli (Türk sanatçının Münih konseri, konsolosluk duyurusu,
  vatandaşlık/oturum mevzuatında değişiklik, Türk toplumunu etkileyen yerel olay)
- 6-8: İlgili ve paylaşılabilir (Türk derneği etkinliği, Almanya genelinde
  Türkleri etkileyen gelişme, ramazan/bayram etkinlikleri)
- 3-5: Dolaylı ilgi (Türkiye gündemi ama Almanya'daki Türklere pratik etkisi yok)
- 1-2: İlgisiz (keyword tesadüfen geçmiş)

Özel kural — şehir çapında MEGA olaylar:
Sayfa Münih'te yaşayanlara hitap ettiği için, Türk bağlantısı OLMASA bile
şehri saran devasa olaylar paylaşmaya değerdir: stadyum/arena seviyesinde
dünya turnesi konserleri, Oktoberfest çapında dev şehir etkinlikleri,
tarihi finaller. Bunlara 6-8 ver. Rutin Bundesliga maçları ve orta boy
konserler girmez (1-4).

Özel kural — Münih günlük yaşamı:
Şehirde yaşayan HERKESİ pratik olarak etkileyen gelişmeler (toplu taşıma
grevi/arızası, S-Bahn kesintisi, havalimanı kaosu, fırtına uyarısı) Türk
bağlantısı olmasa da 5-7 puan almalı — günlük story malzemesidir.
Sıradan trafik ve küçük yerel olaylar girmez (1-4).

Özel kural — Türkiye ulusal medyası (TRT, NTV, Hürriyet gibi kaynaklar):
Münih'teki Türkler Türkiye gündemini zaten başka yerlerden takip ediyor.
Bu kaynaklardan gelenler SADECE şu durumlarda 6+ almalı: (a) tarihi çapta
olay (büyük deprem, darbe girişimi, seçim sonucu, milli takımın büyük
başarısı) veya (b) Almanya'daki Türkleri doğrudan etkileyen gelişme
(vize, gurbetçi düzenlemeleri, çifte vatandaşlık, Türkiye-Almanya
ilişkileri). Rutin iç siyaset ve magazin düşük puan almalı.

İçerikler:
"""

PROMPT_FOOTER = """
SADECE geçerli bir JSON dizisi döndür, başka hiçbir şey yazma.
Her içerik için bir eleman, şu formatta:
[{"nr": 1, "puan": 7, "kategori": "konser", "ozet": "Türkçe tek cümle özet"}, ...]
kategori şunlardan biri olmalı: konser, etkinlik, resmi, haber, diger.
Dizi tam olarak içerik sayısı kadar eleman içermeli."""


class QuotaExhausted(Exception):
    pass


def _call_gemini(prompt: str) -> str:
    """Tek API çağrısı. 429'da bir kez bekleyip dener; yine 429 ise
    QuotaExhausted fırlatır. Diğer hatalar olduğu gibi yükselir."""
    api_key = os.environ["GEMINI_API_KEY"]
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "response_mime_type": "application/json",
        },
    }
    for attempt in (1, 2):
        resp = requests.post(GEMINI_URL, params={"key": api_key},
                             json=body, timeout=60)
        if resp.status_code == 429:
            if attempt == 1:
                print(f"[LLM] 429 kota sinyali — {RETRY_WAIT_S} sn bekleyip "
                      "bir kez daha deniyorum")
                time.sleep(RETRY_WAIT_S)
                continue
            raise QuotaExhausted()
        resp.raise_for_status()
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    raise QuotaExhausted()  # buraya normalde düşülmez


def _batch_prompt(batch: list[dict]) -> str:
    lines = []
    for i, it in enumerate(batch, 1):
        summary = it["summary"][:400]
        lines.append(f"{i}. [Kaynak: {it['source']}] {it['title']} — {summary}")
    return PROMPT_HEADER + "\n".join(lines) + PROMPT_FOOTER


def _parse_batch(text: str, batch: list[dict]) -> dict[int, dict]:
    """LLM cevabını {nr: sonuç} sözlüğüne çevirir; bozuk elemanları atlar."""
    results = {}
    data = json.loads(text)
    if isinstance(data, dict):  # model diziyi sarmalamış olabilir
        data = data.get("sonuclar") or data.get("results") or [data]
    for entry in data:
        try:
            nr = int(entry["nr"])
            if not (1 <= nr <= len(batch)):
                continue
            results[nr] = {
                "puan": int(entry.get("puan", 0)),
                "kategori": str(entry.get("kategori", "diger")),
                "ozet": str(entry.get("ozet", "")).strip(),
            }
        except (KeyError, TypeError, ValueError):
            continue
    return results


def classify_all(items: list[dict], min_score: int = 6):
    """Adayları toplu puanlar.

    Döner: (winners, evaluated, hard_failed, quota_hit)
      winners    : eşiği geçen item'lar (puan/kategori/ozet eklenmiş)
      evaluated  : gerçekten değerlendirilen item'lar (seen'e yazılacaklar)
      hard_failed: kota DIŞI nedenle başarısız kalan item sayısı
      quota_hit  : True ise kota bitti, kalan adaylar ertelendi
    """
    winners: list[dict] = []
    evaluated: list[dict] = []
    hard_failed = 0
    quota_hit = False

    for start in range(0, len(items), BATCH_SIZE):
        batch = items[start:start + BATCH_SIZE]
        try:
            text = _call_gemini(_batch_prompt(batch))
            results = _parse_batch(text, batch)
        except QuotaExhausted:
            quota_hit = True
            print(f"[LLM] Kota doldu — {len(items) - start} aday sonraki "
                  "taramaya ertelendi")
            break
        except Exception as e:
            # Kota dışı hata (geçersiz key, parse bozukluğu vs.)
            print(f"[LLM HATA] batch {start // BATCH_SIZE + 1}: {e}")
            hard_failed += len(batch)
            evaluated.extend(batch)  # sonsuz döngüye girmesinler
            continue

        for i, it in enumerate(batch, 1):
            evaluated.append(it)
            result = results.get(i)
            if result is None:
                hard_failed += 1
                continue
            print(f"[LLM] puan={result['puan']} | {it['title'][:70]}")
            if result["puan"] >= min_score:
                winners.append({**it, **result})

        time.sleep(2)  # batch'ler arası kısa nezaket molası

    return winners, evaluated, hard_failed, quota_hit
