"""Konser tarayıcı — biletçiyi değil, sanatçıyı izler.

Mantık: config/artists.yml'deki her sanatçı için Bandsintown'un halka
açık endpoint'inden yaklaşan konserler çekilir; Münih/Bavyera'dakiler
(GERMANY_WIDE=True yapılırsa tüm Almanya) item olarak döner.

Opsiyonel ikinci kaynak: GitHub Secrets'a TICKETMASTER_API_KEY eklersen
(bedava anahtar: developer.ticketmaster.com) Ticketmaster'ın resmi
Discovery API'sinden Münih'teki müzik etkinlikleri de taranır ve
sanatçı listemizle eşleşenler alınır. Anahtar yoksa bu adım sessizce
atlanır.

Not: Bandsintown kapsamı mükemmel değil — özellikle sadece Eventim'de
satılan konserler görünmeyebilir. Bu tarayıcı "hiçbir şeyi elle takip
etmeden çoğu konseri yakala" katmanıdır; venue sayfaları ve topluluk
ihbarları onun üstüne gelir.
"""

import os
import time
from urllib.parse import quote

import requests

HEADERS = {"User-Agent": "MuenchenRadar/0.1 (kisisel proje)"}
CITY_WORDS = ("münchen", "munich", "muenchen")
REGION_WORDS = ("bavaria", "bayern")
GERMANY_WIDE = False  # True yaparsan tüm Almanya'daki konserler gelir


def _is_local(city: str, region: str, country: str) -> bool:
    c = (city or "").lower()
    r = (region or "").lower()
    co = (country or "").lower()
    if co not in ("germany", "deutschland", "de"):
        return False
    if GERMANY_WIDE:
        return True
    return any(w in c for w in CITY_WORDS) or any(w in r for w in REGION_WORDS)


def fetch_bandsintown(artists: list[str]) -> list[dict]:
    items = []
    for artist in artists:
        try:
            resp = requests.get(
                f"https://rest.bandsintown.com/artists/{quote(artist)}/events",
                params={"app_id": "muenchen_radar", "date": "upcoming"},
                headers=HEADERS,
                timeout=20,
            )
            if resp.status_code != 200:
                continue  # sanatçı Bandsintown'da yoksa sessizce geç
            data = resp.json()
            if not isinstance(data, list):
                continue
            for ev in data:
                venue = ev.get("venue", {})
                if not _is_local(venue.get("city"), venue.get("region"),
                                 venue.get("country")):
                    continue
                date = (ev.get("datetime") or "")[:10]
                link = ev.get("url") or f"bandsintown://{artist}/{date}"
                items.append({
                    "source": "Bandsintown",
                    "title": f"KONSER: {artist} — {venue.get('name', '?')} ({date})",
                    "summary": f"{artist} konseri, {venue.get('city', '')}, {date}",
                    "link": link,
                    "trusted": True,  # kendi listemizin konseri = her zaman ilgili
                    "keyword_list": "default",
                })
        except Exception as e:
            print(f"[KONSER HATA] {artist}: {e}")
        time.sleep(0.5)  # API'ye nazik davran
    return items


def fetch_ticketmaster(artists: list[str]) -> list[dict]:
    key = os.environ.get("TICKETMASTER_API_KEY")
    if not key:
        return []  # anahtar yoksa bu kaynak devre dışı
    items = []
    try:
        resp = requests.get(
            "https://app.ticketmaster.com/discovery/v2/events.json",
            params={
                "apikey": key,
                "city": "München",
                "countryCode": "DE",
                "classificationName": "music",
                "size": 199,
            },
            headers=HEADERS,
            timeout=30,
        )
        resp.raise_for_status()
        events = resp.json().get("_embedded", {}).get("events", [])
        artist_lows = [a.lower() for a in artists]
        mega_venues = ("olympiastadion", "olympiahalle", "sap garden",
                       "königsplatz", "olympiapark")
        for ev in events:
            name = ev.get("name", "")
            venue_name = (
                ev.get("_embedded", {}).get("venues", [{}])[0].get("name", "")
            )
            artist_hit = any(a in name.lower() for a in artist_lows)
            mega_hit = any(v in venue_name.lower() for v in mega_venues)
            if not (artist_hit or mega_hit):
                continue
            date = ev.get("dates", {}).get("start", {}).get("localDate", "")
            items.append({
                "source": "Ticketmaster",
                "title": f"KONSER: {name} — {venue_name} ({date})",
                "summary": f"Münih konseri: {name}, {venue_name}, {date}",
                "link": ev.get("url", f"ticketmaster://{name}/{date}"),
                # Sanatçı listemizden olanlar filtresiz geçer; mega mekan
                # yakalamaları LLM'e "gerçekten mega mı" diye sorulur.
                "trusted": artist_hit,
                "keyword_list": "default",
            })
    except Exception as e:
        print(f"[KONSER HATA] Ticketmaster: {e}")
    return items


def fetch_all(artists: list[str]) -> list[dict]:
    bt = fetch_bandsintown(artists)
    print(f"[KONSER] Bandsintown: {len(bt)} konser bulundu")
    tm = fetch_ticketmaster(artists)
    if tm or os.environ.get("TICKETMASTER_API_KEY"):
        print(f"[KONSER] Ticketmaster: {len(tm)} konser bulundu")
    return bt + tm
