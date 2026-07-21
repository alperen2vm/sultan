"""LLM sınıflandırması.

Tüm LLM mantığı bu dosyada izole — ileride model değiştirmek istersen
sadece classify_item() içini değiştir, sistemin geri kalanına dokunma.

Şu an: Google Gemini Flash (AI Studio free tier), düz REST çağrısı.
API key: https://aistudio.google.com -> Get API key (kart gerekmez).
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

PROMPT_TEMPLATE = """Sen Münih'te yaşayan Türk toplumu için çalışan bir içerik filtresisin.
Sana bir haber/etkinlik başlığı ve özeti vereceğim.

Görevin: Bu içeriğin Münih ve çevresindeki Türkler için ne kadar ilgili ve
paylaşmaya değer olduğunu puanla.

Puanlama rehberi:
- 9-10: Doğrudan ve önemli (Türk sanatçının Münih konseri, konsolosluk duyurusu,
  vatandaşlık/oturum mevzuatında değişiklik, Türk toplumunu etkileyen yerel olay)
- 6-8: İlgili ve paylaşılabilir (Türk derneği etkinliği, Almanya genelinde
  Türkleri etkileyen gelişme, ramazan/bayram etkinlikleri)
- 3-5: Dolaylı ilgi (Türkiye gündemi ama Almanya'daki Türklere pratik etkisi yok)
- 1-2: İlgisiz (keyword tesadüfen geçmiş)

Özel kural — şehir çapında MEGA olaylar:
Sayfa Münih'te yaşayanlara hitap ettiği için, Türk bağlantısı OLMASA
bile şehri saran devasa olaylar paylaşmaya değerdir: stadyum/arena
seviyesinde dünya turnesi konserleri (uluslararası bir megastarın
Olympiastadion veya Olympiahalle konseri gibi), Oktoberfest çapında dev
şehir etkinlikleri, tarihi finaller, şehir hayatını etkileyen büyük
olaylar. Bunlara 6-8 ver. Ancak rutin Bundesliga maçları, orta boy
konserler, sıradan festival ve mekan haberleri bu kapsama GİRMEZ (1-4).

Özel kural — Münih günlük yaşamı:
Şehirde yaşayan HERKESİ pratik olarak etkileyen gelişmeler (toplu taşıma
grevi/arızası, S-Bahn kesintisi, havalimanı kaosu, fırtına/unwetter
uyarısı) Türk bağlantısı olmasa da 5-7 puan almalı — takipçiler Münih'te
yaşıyor ve bu bilgiler günlük story malzemesidir. Sıradan trafik ve
küçük yerel olaylar girmez (1-4).

Özel kural — Türkiye ulusal medyası (TRT, NTV, Hürriyet gibi kaynaklar):
Münih'teki Türkler Türkiye gündemini zaten başka yerlerden takip ediyor.
Bu kaynaklardan gelen içerik SADECE şu durumlarda 6+ almalı:
(a) tarihi çapta olay (büyük deprem, darbe girişimi, seçim sonucu,
milli takımın büyük başarısı) veya (b) Almanya'daki Türkleri doğrudan
etkileyen gelişme (vize, gurbetçi düzenlemeleri, çifte vatandaşlık,
Türkiye-Almanya ilişkileri). Rutin iç siyaset, magazin ve
üçüncü ülke haberleri düşük puan almalı.

İçerik:
Kaynak: {source}
Başlık: {title}
Özet: {summary}

SADECE şu JSON formatında cevap ver, başka hiçbir şey yazma:
{{"puan": <1-10 arası tam sayı>, "kategori": "<konser|etkinlik|resmi|haber|diger>", "ozet": "<Türkçe tek cümle özet>"}}"""


def classify_item(item: dict) -> dict | None:
    """Tek bir item'ı sınıflandırır. Hata olursa None döner (item atlanır)."""
    api_key = os.environ["GEMINI_API_KEY"]
    prompt = PROMPT_TEMPLATE.format(
        source=item["source"],
        title=item["title"],
        summary=item["summary"][:600],
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "response_mime_type": "application/json",
        },
    }
    try:
        resp = requests.post(
            GEMINI_URL,
            params={"key": api_key},
            json=body,
            timeout=30,
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        result = json.loads(text)
        return {
            "puan": int(result.get("puan", 0)),
            "kategori": str(result.get("kategori", "diger")),
            "ozet": str(result.get("ozet", "")).strip(),
        }
    except Exception as e:
        print(f"[LLM HATA] {item['title'][:60]}: {e}")
        return None


def classify_all(items: list[dict], min_score: int = 6):
    """Tüm adayları sınıflandırır.

    Döner: (eşiği geçenler, denenen sayısı, başarısız LLM çağrısı sayısı)
    Başarısızlık sayısı main tarafından "sessiz ölüm" tespiti için kullanılır.
    """
    winners = []
    attempted = 0
    failed = 0
    for it in items:
        attempted += 1
        result = classify_item(it)
        time.sleep(2)  # free tier rate limit'ine nazik davran
        if not result:
            failed += 1
            continue
        print(f"[LLM] puan={result['puan']} | {it['title'][:70]}")
        if result["puan"] >= min_score:
            winners.append({**it, **result})
    return winners, attempted, failed
