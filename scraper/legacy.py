#!/usr/bin/env python3
"""(boykot-ios/pipeline/legacy_to_catalog.py kopyası) Eski `guncellenmis_liste.json` (Supabase dökümü) → yeni normalize katalog (catalog.json).

Kullanım:
    python3 pipeline/legacy_to_catalog.py ../guncellenmis_liste.json app/Boykot/Resources/catalog.json --version 1

Durum tablosu BoykotCore/StatusNormalizer.swift ile AYNI olmalı.
"""
import argparse
import datetime as dt
import json
import re
import unicodedata

TR_MAP = str.maketrans("IİĞÜŞÖÇığüşöç", "iigusocigusoc")


def metin_temizle(metin: str) -> str:  # main.py ile aynı (+ idempotent olması için son .lower())
    metin = str(metin).strip().translate(TR_MAP).lower()
    metin = unicodedata.normalize("NFKD", metin).encode("ascii", "ignore").decode("ascii")
    metin = re.sub(r"[^\w\s]", " ", metin).lower()  # NFKD büyük harf üretebilir ("™"→"TM")
    return re.sub(r"\s+", " ", metin).strip()


KNOWN = {
    "boykot listesinde": "boycott",
    "boykotlu degil": "safe",
    "kismen boykot": "partial",
    "supheli": "caution",
    "ahlaken boykot": "caution",
    "kesin boykot": "boycott",
    "alinabilir": "safe",
    "insafa bagli": "caution",
}


def verdict(label):
    if not label or not str(label).strip():
        return "unknown"
    key = metin_temizle(label)
    if key in KNOWN:
        return KNOWN[key]
    if any(w in key for w in ("degil", "alinabilir", "uygun")):
        return "safe"
    if any(w in key for w in ("supheli", "ahlaken", "insaf")):
        return "caution"
    if "kismen" in key:
        return "partial"
    if "boykot" in key:
        return "boycott"
    return "unknown"


# Kaynak sitelerden kategori adları Türkçe karaktersiz geliyor; düzgün yazımları:
CATEGORY_TR = {
    "Arac Lastigi": "Araç Lastiği", "Arama Motoru": "Arama Motoru", "Ayakkabi": "Ayakkabı",
    "Bebek Urunleri": "Bebek Ürünleri", "Beyaz Esya": "Beyaz Eşya", "Bilgisayar Bilesenleri": "Bilgisayar Bileşenleri",
    "Biskuvi": "Bisküvi", "Camasir Yumusaticilari": "Çamaşır Yumuşatıcıları", "Cay": "Çay", "Cikolata": "Çikolata",
    "Cilt Bakimi": "Cilt Bakımı", "Cips": "Cips", "Deterjan": "Deterjan", "Dis Bakimi": "Diş Bakımı",
    "Dondurma": "Dondurma", "E Ticaret": "E-Ticaret", "Eglence": "Eğlence", "Elektrikli Ev Aletleri": "Elektrikli Ev Aletleri",
    "Et Ve Urunleri": "Et ve Ürünleri", "Ev Urunleri": "Ev Ürünleri", "Evcil Hayvan": "Evcil Hayvan", "Finans": "Finans",
    "Gazli Icecekler": "Gazlı İçecekler", "Giyim Tekstil": "Giyim ve Tekstil", "Gofret": "Gofret", "Hasere Ilaci": "Haşere İlacı",
    "Hurma": "Hurma", "Icecek": "İçecek", "Insaat Tesisat": "İnşaat ve Tesisat", "Isletme": "İşletme",
    "Kahvaltilik": "Kahvaltılık", "Kahve": "Kahve", "Kek": "Kek", "Kirtasiye": "Kırtasiye",
    "Kisisel Bakim Diger": "Kişisel Bakım (Diğer)", "Koku Spreyleri": "Koku Spreyleri", "Kozmetik": "Kozmetik", "Medya": "Medya",
    "Mobilya": "Mobilya", "Mutfak Esyalari": "Mutfak Eşyaları", "Otomotiv": "Otomotiv", "Otomotiv Urunleri": "Otomotiv Ürünleri",
    "Oyun": "Oyun", "Oyuncak": "Oyuncak", "Pecete": "Peçete", "Pil Batarya": "Pil ve Batarya", "Sabun": "Sabun",
    "Sac Bakimi": "Saç Bakımı", "Saglik": "Sağlık", "Sakiz Sekerleme": "Sakız ve Şekerleme", "Seyahat Konaklama": "Seyahat ve Konaklama",
    "Sigara": "Sigara", "Sigorta": "Sigorta", "Sirket": "Şirket", "Su": "Su", "Supermarket": "Süpermarket",
    "Sut Urunleri": "Süt Ürünleri", "Tarim Ziraat": "Tarım ve Ziraat", "Teknolojik Cihaz Aksesuarlari": "Teknolojik Cihaz Aksesuarları",
    "Teknolojik Cihazlar": "Teknolojik Cihazlar", "Temel Gida": "Temel Gıda", "Temizlik Diger": "Temizlik (Diğer)", "Termos": "Termos",
    "Yakit": "Yakıt", "Yazilim": "Yazılım", "Yemis Cekirdek": "Yemiş ve Çekirdek", "Yuzey Temizligi": "Yüzey Temizliği",
}


def logo_url(item):
    # Flutter uygulamasındaki kural: Boykot Dedektifi slug'ı → boykotservisi.com logosu
    bd = item.get("boykot_dedektifi_kanit_url") or ""
    if "/b/" in bd:
        slug = bd.split("/b/")[-1].split("?")[0].split("/")[0].strip()
        if slug:
            return f"https://boykotservisi.com/uploads/brands/{slug}.webp"
    return item.get("marka_gorselinin_dosya_yolu") or None


def convert(items):
    brands, seen = [], set()
    for it in items:
        bid, name = (it.get("id") or "").strip(), (it.get("marka_adi") or "").strip()
        if not bid or not name or bid in seen:
            continue
        seen.add(bid)
        sources = []
        for sid, lk, uk in (
            ("boykotdedektifi", "boykot_dedektifi_boykot_durumu", "boykot_dedektifi_kanit_url"),
            ("bykt", "bykt_org_boykot_durumu", "bykt_org_kanit_url"),
        ):
            label = (it.get(lk) or "").strip()
            if label:
                sources.append({"source": sid, "label": label, "verdict": verdict(label), "url": it.get(uk) or None})
        brands.append({
            "id": bid,
            "name": name,
            "category": CATEGORY_TR.get((it.get("kategori") or "").strip(), (it.get("kategori") or "").strip()) or None,
            "logoURL": logo_url(it),
            "sources": sources,
            "updatedAt": it.get("updated_at"),
        })
    return attach_products(merge_duplicates(brands))


def attach_products(brands, path=None):
    """pipeline/alt_markalar.json: ürün/alt marka adlarını ana markaya ekler ("products")."""
    import os
    path = path or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "alt_markalar.json")
    if not os.path.exists(path):
        return brands
    with open(path, encoding="utf-8") as f:
        mapping = json.load(f)
    by_key = {}
    for b in brands:
        by_key.setdefault(metin_temizle(b["name"]), b)
    for parent, v in mapping.items():
        if parent.startswith("_"):
            continue
        b = by_key.get(metin_temizle(parent))
        if b is None:
            raise SystemExit(f"alt_markalar.json: '{parent}' katalogda yok")
        b["products"] = list(v["urunler"])
    return brands


def merge_duplicates(brands):
    """Aynı markanın iki kaydı varsa (ör. "Lego" ve "LEGO", biri Boykot Dedektifi'nden biri bykt.org'dan)
    tek kayıtta birleştirir: kaynaklar birleşir, eksik kategori/logo tamamlanır."""
    groups, order = {}, []
    for b in brands:
        k = metin_temizle(b["name"])
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(b)
    out = []
    for k in order:
        g = groups[k]
        if len(g) == 1:
            out.append(g[0])
            continue
        g = sorted(g, key=lambda b: (-len(b["sources"]), b["category"] is None))
        primary = dict(g[0])
        have = {s["source"] for s in primary["sources"]}
        sources = list(primary["sources"])
        for other in g[1:]:
            for src in other["sources"]:
                if src["source"] not in have:
                    sources.append(src)
                    have.add(src["source"])
            primary["category"] = primary["category"] or other["category"]
            primary["logoURL"] = primary["logoURL"] or other["logoURL"]
            if (other.get("updatedAt") or "") > (primary.get("updatedAt") or ""):
                primary["updatedAt"] = other["updatedAt"]
        order_rank = {"boykotdedektifi": 0, "bykt": 1}
        primary["sources"] = sorted(sources, key=lambda s: order_rank.get(s["source"], 9))
        out.append(primary)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--version", type=int, default=1)
    a = ap.parse_args()
    with open(a.src, encoding="utf-8") as f:
        brands = convert(json.load(f))
    catalog = {
        "version": a.version,
        "generatedAt": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "brands": brands,
    }
    with open(a.dst, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, separators=(",", ":"))
    print(f"{len(brands)} marka yazıldı → {a.dst}")
