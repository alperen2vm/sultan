"""Ucuz keyword prefilter — LLM'e giden hacmi küçültür.

trusted=True kaynaklardan gelen her şey filtreyi otomatik geçer
(ör. konsolosluk duyuruları).
"""


def passes(item: dict, keywords: list[str]) -> bool:
    if item.get("trusted"):
        return True
    text = f"{item['title']} {item['summary']}".lower()
    return any(kw.lower() in text for kw in keywords)


def apply(items: list[dict], keywords: list[str]) -> list[dict]:
    kept = [it for it in items if passes(it, keywords)]
    print(f"[PREFILTER] {len(items)} -> {len(kept)} item")
    return kept
