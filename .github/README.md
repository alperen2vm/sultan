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


def classify_all(items: list[dict], min_score: int = 6) -> list[dict]:
    """Tüm adayları sınıflandırır, eşiği geçenleri döner."""
    winners = []
    for it in items:
        result = classify_item(it)
        time.sleep(2)  # free tier rate limit'ine nazik davran
        if not result:
            continue
        print(f"[LLM] puan={result['puan']} | {it['title'][:70]}")
        if result["puan"] >= min_score:
            winners.append({**it, **result})
    return winners
