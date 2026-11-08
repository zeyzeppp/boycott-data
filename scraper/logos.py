"""Logolar: kaynaktan indirilir, en fazla 256 px WebP'ye küçültülür, depoda logos/<id>.webp olarak tutulur.
Kaynak adresi değişmedikçe yeniden indirilmez (state/logolar.json)."""
import io
import os

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


def update_logos(brands, http, root, state, log=print, limit=None):
    """brands içindeki `_logo_src`'lere göre logos/ klasörünü günceller, logoURL'leri doldurur.
    state: {marka id: kaynak adres}. Döner: (yeni indirilen, hata) sayıları."""
    os.makedirs(os.path.join(root, "logos"), exist_ok=True)
    fetched = failed = 0
    for b in brands:
        src = b.get("_logo_src")
        path = os.path.join(root, "logos", f"{b['id']}.webp")
        have = os.path.exists(path)
        if src and (state.get(b["id"]) != src or not have) and (limit is None or fetched < limit):
            try:
                data = http.get(src, binary=True)
                if data:
                    with open(path, "wb") as f:
                        f.write(to_webp(data))
                    state[b["id"]] = src
                    have = True
                    fetched += 1
            except Exception as e:  # tek logo hatası taramayı durdurmaz
                failed += 1
                log(f"  logo alınamadı: {b['name']}: {e}")
        b["logoURL"] = CDN.format(id=b["id"]) if have else None
    # Artık katalogda olmayan markaların logoları silinir
    ids = {b["id"] for b in brands}
    for name in os.listdir(os.path.join(root, "logos")):
        if name.endswith(".webp") and name[:-5] not in ids:
            os.remove(os.path.join(root, "logos", name))
            state.pop(name[:-5], None)
    return fetched, failed
