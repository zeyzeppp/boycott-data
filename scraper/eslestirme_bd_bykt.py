#!/usr/bin/env python3
"""bykt.org ↔ Boykot Dedektifi elle eşleştirme sayfası (tek HTML dosyası; logolar için internet gerekir).

Ön eşleştirme sırası:
  1) Eski listedeki (guncellenmis_liste.json) eşleşmeler — kanıt adresleri üzerinden
  2) Adı birebir aynı olanlar (Türkçe karakter / büyük-küçük harf / noktalama hariç)
  3) Yalnızca boşluk ya da parantez içi farkı olanlar ("Lay's" ↔ "Lays", "X (Eski adıyla Y)" ↔ "X")
Kalanlar için öneriler gösterilir. Sayfa sonucu `eslesme_kararlari.json` olarak indirir (tam eşleşme listesi).

Kullanım: python scraper/eslestirme_bd_bykt.py --bd boykot_dedektifi.json --bykt bykt_org.json --eski guncellenmis_liste.json --out eslestirme_bd_bykt.html
"""
import argparse
import json
import os
import re
import sys
import urllib.parse
from difflib import SequenceMatcher

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from common import compact, metin_temizle  # noqa: E402

GENERIC = {"grup", "group", "holding", "deterjan", "su", "com", "beauty", "gida", "tv", "ag", "inc", "sirketi",
           "company", "the", "and", "ve", "eski", "adiyla", "adi", "turkiye", "turkey", "co", "ltd", "corp"}


def url_key(u):
    return urllib.parse.unquote(u or "").strip().rstrip("/").lower()


def base_name(name):
    """Parantez içini atar: "20th Century Studios (Eski adıyla Fox)" → "20th century studios"."""
    return metin_temizle(re.sub(r"\([^)]*\)", " ", name)) or metin_temizle(name)


def suggestions(name, bd_keys, n=6):
    k = base_name(name)
    ck = compact(k)
    words = [w for w in k.split() if len(w) >= 3 and w not in GENERIC]
    scored = []
    for d in bd_keys:
        cd = compact(d)
        sm = SequenceMatcher(None, ck, cd)
        if sm.real_quick_ratio() < 0.45:
            bonus_possible = words and any(w in d.split() for w in words)
            if not bonus_possible and not (len(cd) >= 4 and (cd in ck or ck in cd)):
                continue
        r = sm.ratio()
        bonus = 0.0
        if words and any(w in d.split() for w in words):
            bonus = 0.35
        if len(cd) >= 4 and len(ck) >= 4 and (cd in ck or ck in cd):
            bonus = max(bonus, 0.3)
        s = r + bonus
        if s >= 0.62:
            scored.append((s, d))
    scored.sort(key=lambda x: -x[0])
    return [d for _, d in scored[:n]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bd", required=True)
    ap.add_argument("--bykt", required=True)
    ap.add_argument("--eski", required=True)
    ap.add_argument("--out", default="eslestirme_bd_bykt.html")
    a = ap.parse_args()
    bd = json.load(open(a.bd, encoding="utf-8"))["markalar"]
    by = json.load(open(a.bykt, encoding="utf-8"))["markalar"]
    old = json.load(open(a.eski, encoding="utf-8"))

    bd_by_url = {url_key(b["kanit_url"]): b for b in bd}
    by_by_url = {url_key(b["kanit_url"]): b for b in by}
    # BD anahtarı = kanıt adresi (kimliği içerir, tekil)
    bd_name, bd_compact, bd_base = {}, {}, {}
    for b in bd:
        k = metin_temizle(b["marka_adi"])
        bd_name.setdefault(k, b)
        bd_compact.setdefault(compact(k), b)
        bd_base.setdefault(compact(base_name(b["marka_adi"])), b)

    old_pairs = {}
    for r in old:
        x, y = r.get("boykot_dedektifi_kanit_url"), r.get("bykt_org_kanit_url")
        if x and y:
            A, B = bd_by_url.get(url_key(x)), by_by_url.get(url_key(y))
            if A and B:
                old_pairs[B["kanit_url"]] = A["kanit_url"]

    # Öneri araması için ad anahtarı → BD adresi
    name_to_url = {}
    for b in bd:
        name_to_url.setdefault(metin_temizle(b["marka_adi"]), b["kanit_url"])
    bd_keys = list(name_to_url)

    items = []
    for b in sorted(by, key=lambda x: metin_temizle(x["marka_adi"])):
        k = metin_temizle(b["marka_adi"])
        auto, how = None, None
        if b["kanit_url"] in old_pairs:
            auto, how = old_pairs[b["kanit_url"]], "eski"
        elif k in bd_name:
            auto, how = bd_name[k]["kanit_url"], "ad"
        elif compact(k) in bd_compact:
            auto, how = bd_compact[compact(k)]["kanit_url"], "benzer"
        elif compact(base_name(b["marka_adi"])) in bd_base:
            auto, how = bd_base[compact(base_name(b["marka_adi"]))]["kanit_url"], "benzer"
        same = bool(auto) and metin_temizle(bd_by_url[url_key(auto)]["marka_adi"]) == k
        items.append({
            "k": b["kanit_url"], "n": b["marka_adi"], "l": b.get("resim_url"), "c": b.get("kategori") or "",
            "s": b["boykot_durumu"], "auto": auto, "how": how, "same": same,
            "sug": [] if auto else [name_to_url[d] for d in suggestions(b["marka_adi"], bd_keys)],
        })

    # Aynı Dedektif markasına birden çok bykt markası bağlandıysa işaretle
    used = {}
    for i in items:
        if i["auto"]:
            used.setdefault(i["auto"], []).append(i["k"])
    for i in items:
        i["dup"] = bool(i["auto"]) and len(used[i["auto"]]) > 1

    bd_list = [{"k": b["kanit_url"], "n": b["marka_adi"], "l": b.get("resim_url"),
                "c": (b.get("kategoriler") or [b.get("kategori")])[:3], "s": b["boykot_durumu"]} for b in bd]
    data = {"bd": bd_list, "by": items}
    tpl = open(os.path.join(HERE, "eslestirme_bd_bykt.tpl.html"), encoding="utf-8").read()
    page = tpl.replace("/*DATA*/null", json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))
    with open(a.out, "w", encoding="utf-8") as f:
        f.write(page)
    from collections import Counter
    c = Counter(i["how"] for i in items)
    print(f"{a.out}: {len(items)} bykt markası — eski liste {c['eski']}, aynı ad {c['ad']}, benzer {c['benzer']}, "
          f"eşleşmeyen {c[None]} (önerili {sum(1 for i in items if not i['auto'] and i['sug'])}); "
          f"çakışan {sum(i['dup'] for i in items)}; farklı yazılmış {sum(1 for i in items if i['auto'] and not i['same'])}")


if __name__ == "__main__":
    main()
