"""İki kaynağı tek kataloğa birleştirme (saf fonksiyonlar, testli).

Kurallar (docs/VERI_HATTI.md):
- Aynı anahtar (metin_temizle) ya da yalnızca boşluk/noktalama farkı ("lay s" / "lays") → tek marka.
- config/eslesmeler.json: kullanıcının onayladığı birleştirmeler ("birlestir") ve ayrı kalacaklar ("ayri").
- Benzer ama emin olunamayanlar → "bekleyen" listesi (kullanıcıya sorulur); karar verilene kadar ayrı markalar.
- Kategori: Dedektif'in kategorileri (birden çok; ilki ana). Yalnız boykot.co'da olanlar: config/kategori_esleme.json.
- Kaldırma: bir kaynakta 2 tarama üst üste görünmeyen markanın o kaynaktaki hükmü kalkar.
"""
import uuid
from difflib import SequenceMatcher

from common import compact, metin_temizle, verdict

SOURCES = ("boykotdedektifi", "boykotco")
MISSING_LIMIT = 2            # bu kadar tarama üst üste görünmezse kaldırılır
SIMILAR_RATIO = 0.85         # şüpheli eşleşme eşiği (boşluksuz anahtarlar)
SEPARATE_PREFIX = "boykotco:"   # aynı adlı ama kullanıcının "farklı" dediği boykot.co markası için anahtar
ID_NAMESPACE = uuid.UUID("6f1c2a52-6d1e-4b8e-9a52-0b5f7c1d3e21")


def carry_over(fresh, prev_state, source):
    """Kaldırma kuralı. fresh: bu taramada görülenler. prev_state: {anahtar: {"entry":…, "missing":n}}.
    Döner: (kullanılacak kayıtlar, yeni durum)."""
    state, out = {}, {}
    for key, entry in fresh.items():
        state[key] = {"entry": entry, "missing": 0}
        out[key] = entry
    for key, st in (prev_state or {}).items():
        if key in fresh:
            continue
        missing = st.get("missing", 0) + 1
        if missing < MISSING_LIMIT:
            state[key] = {"entry": st["entry"], "missing": missing}
            out[key] = st["entry"]
    return out, state


def resolve_keys(bd, bc, decisions):
    """boykot.co anahtarlarını Dedektif anahtarlarına bağlar. Döner: ({bc anahtarı: birleşik anahtar}, bekleyenler)."""
    merge_map = {metin_temizle(k): metin_temizle(v) for k, v in (decisions.get("birlestir") or {}).items()}
    separate = {frozenset((metin_temizle(a), metin_temizle(b))) for a, b in (decisions.get("ayri") or [])}
    bd_compact = {}
    for k in bd:
        bd_compact.setdefault(compact(k), k)

    mapping = {}
    for k in bc:
        if k in merge_map and merge_map[k] in bd:
            mapping[k] = merge_map[k]
            continue
        auto = k if k in bd else bd_compact.get(compact(k))
        if auto is not None and frozenset((k, auto)) not in separate:
            mapping[k] = auto
        elif auto is not None:
            # Kullanıcı "aynı ad ama farklı marka" dedi: boykot.co kaydı ayrı marka olarak kalır
            mapping[k] = SEPARATE_PREFIX + k
        else:
            mapping[k] = k

    matched_bd = set(mapping.values()) & set(bd)
    only_bd = [k for k in bd if k not in matched_bd]
    pending = []
    for k in bc:
        if mapping[k] in bd or mapping[k].startswith(SEPARATE_PREFIX):
            continue
        ck = compact(k)
        best = None
        for d in only_bd:
            if frozenset((k, d)) in separate:
                continue
            cd = compact(d)
            if abs(len(cd) - len(ck)) > 4:
                continue
            r = SequenceMatcher(None, ck, cd).ratio()
            prefix = min(len(ck), len(cd)) >= 4 and (ck.startswith(cd) or cd.startswith(ck))
            if (r >= SIMILAR_RATIO or prefix) and (best is None or r > best[1]):
                best = (d, r)
        if best:
            pending.append({"boykotco": k, "dedektif": best[0], "benzerlik": round(best[1], 2)})
    return mapping, pending


def map_categories(bc_categories, mapping_table):
    out = []
    for c in bc_categories:
        m = mapping_table.get(c)
        if m and m not in out:
            out.append(m)
    return out


def build(bd, bc, decisions, cat_table, ids, products):
    """Birleşik marka listesi (uygulamaların okuduğu catalog.json biçiminde)."""
    mapping, pending = resolve_keys(bd, bc, decisions)
    merged = {}
    for key, e in bd.items():
        merged[key] = {"name": e["name"], "categories": list(e["categories"]), "logo_src": e.get("logo"),
                       "sources": [_source("boykotdedektifi", e)]}
    for k, e in bc.items():
        key = mapping[k]
        m = merged.get(key)
        if m is None:
            m = merged[key] = {"name": e["name"], "categories": map_categories(e["categories"], cat_table),
                               "logo_src": e.get("logo"), "sources": []}
        elif not m["logo_src"]:
            m["logo_src"] = e.get("logo")
        if not any(s["source"] == "boykotco" for s in m["sources"]):
            m["sources"].append(_source("boykotco", e))

    brands = []
    for key in sorted(merged, key=lambda k: metin_temizle(merged[k]["name"])):
        m = merged[key]
        bid = ids.get(key) or str(uuid.uuid5(ID_NAMESPACE, key))
        ids[key] = bid
        b = {
            "id": bid,
            "name": m["name"],
            "category": m["categories"][0] if m["categories"] else None,
            "categories": m["categories"],
            "logoURL": None,          # logolar indirildikten sonra doldurulur
            "sources": m["sources"],
            "updatedAt": None,
            "_key": key,
            "_logo_src": m["logo_src"],
        }
        if key in products:
            b["products"] = products[key]
        brands.append(b)
    return brands, pending


def _source(sid, e):
    return {"source": sid, "label": e["label"], "verdict": verdict(e["label"]), "url": e["url"]}


def load_products(alt_markalar):
    """config/alt_markalar.json → {marka anahtarı: [ürün adları]}"""
    return {metin_temizle(k): list(v["urunler"]) for k, v in alt_markalar.items() if not k.startswith("_")}
