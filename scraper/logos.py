"""Logolar: kaynaktan indirilir, en fazla 256 px WebP'ye küçültülür, depoda logos/<id>.webp olarak tutulur.
Kaynak adresi değişmedikçe yeniden indirilmez (state/logolar.json)."""
import io
import os
import time

from PIL import Image

MAX_SIDE = 256
CDN = "https://cdn.jsdelivr.net/gh/zeyzeppp/boycott-data@main/logos/{id}.webp"


def to_webp(data: bytes) -> bytes:
    im = Image.open(io.BytesIO(data))
    im.load()
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA")
    im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "WEBP", quality=82, method=6)
    return out.getvalue()


def update_logos(brands, http, root, state, log=print, limit=None, budget_s=None):
    """brands içindeki `_logo_src`'lere göre logos/ klasörünü günceller, logoURL'leri doldurur.
    state: {marka id: kaynak adres}. budget_s: süre sınırı (saniye) — dolunca kalanlar sonraki taramaya kalır.
    Başarısız adresler state'te "!" önekiyle tutulur ve 7 gün boyunca tekrar denenmez.
    Döner: (yeni indirilen, hata) sayıları."""
    deadline = time.time() + budget_s if budget_s else None
    today = int(time.time() // 86400)
    os.makedirs(os.path.join(root, "logos"), exist_ok=True)
    fetched = failed = 0
    for b in brands:
        src = b.get("_logo_src")
        path = os.path.join(root, "logos", f"{b['id']}.webp")
        have = os.path.exists(path) and os.path.getsize(path) > 0   # boş dosya = logo yok
        prev = state.get(b["id"]) or ""
        failed_recently = prev.startswith("!") and prev.split("!", 2)[-1] == src and today - int(prev.split("!")[1]) < 7
        if (src and (prev != src or not have) and not failed_recently and (limit is None or fetched < limit)
                and (deadline is None or time.time() < deadline)):
            try:
                data = http.get(src, binary=True, polite=_is_source_host(src))
                if data:
                    with open(path, "wb") as f:
                        f.write(to_webp(data))
                    state[b["id"]] = src
                    have = True
                    fetched += 1
                else:
                    state[b["id"]] = f"!{today}!{src}"   # bulunamadı (404): bir hafta tekrar denenmez
            except Exception as e:  # tek logo hatası taramayı durdurmaz
                failed += 1
                state[b["id"]] = f"!{today}!{src}"
                log(f"  logo alınamadı: {b['name']}: {str(e)[:120]}")
        b["logoURL"] = CDN.format(id=b["id"]) if have else None
    # Artık katalogda olmayan markaların logoları silinir
    ids = {b["id"] for b in brands}
    for name in os.listdir(os.path.join(root, "logos")):
        if name.endswith(".webp") and name[:-5] not in ids:
            os.remove(os.path.join(root, "logos", name))
            state.pop(name[:-5], None)
    return fetched, failed


def _is_source_host(url):
    """Kaynak sitelere (Dedektif / boykot.co) nazik bekleme; diğer logo sunucularına (Wikipedia vb.) kısa bekleme."""
    return any(h in url for h in ("boykotdedektifi.com", "boykotservisi.com", "boykot.co"))
