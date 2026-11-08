#!/usr/bin/env python3
"""Geçici mod: katalog, eski birleşik listeden (kaynak/guncellenmis_liste.json — Boykot Dedektifi + bykt.org,
markalar önceden eşleştirilmiş) üretilir; canlı tarama kapalı.

Kullanım:  python scraper/eski_liste.py [--root .]
- Kimlikler eski listedeki id'ler (uygulamalara gömülü katalogla aynı).
- Logo: depoda logos/<id>.webp varsa o (jsDelivr), yoksa eski listedeki adres.
- Kategori: eski listedeki tek kategori (categories = [category]).
- Ürün/alt marka adları: config/alt_markalar.json.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import legacy  # noqa: E402
from logos import CDN  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.dirname(HERE))
    ap.add_argument("--logo-list", help="logos/ yerine kimlik listesi (test için)")
    a = ap.parse_args()
    p = lambda *x: os.path.join(a.root, *x)  # noqa: E731

    items = json.load(open(p("kaynak", "guncellenmis_liste.json"), encoding="utf-8"))
    brands = legacy.convert(items)  # birleştirme + kategori adları + ürünler (alt_markalar.json)
    if a.logo_list:
        have = set(open(a.logo_list, encoding="utf-8").read().split())
    else:
        have = {f[:-5] for f in os.listdir(p("logos")) if f.endswith(".webp")} if os.path.isdir(p("logos")) else set()
    for b in brands:
        b["categories"] = [b["category"]] if b.get("category") else []
        if b["id"] in have:
            b["logoURL"] = CDN.format(id=b["id"])

    prev = json.load(open(p("meta.json"))) if os.path.exists(p("meta.json")) else {}
    body = json.dumps(brands, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(body.encode()).hexdigest()
    now = dt.datetime.now(dt.timezone.utc)
    # Sürüm daima öncekinden büyük olmalı (telefonlar daha yüksek sürümü indirir)
    version = max(int(now.strftime("%Y%m%d%H")), prev.get("version", 0) + (0 if digest == prev.get("contentSha256") else 1))
    if digest == prev.get("contentSha256"):
        version = prev["version"]
    catalog = {"version": version, "generatedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "brands": brands}
    with open(p("catalog.json"), "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, sort_keys=True)
        f.write("\n")
    sha = hashlib.sha256(open(p("catalog.json"), "rb").read()).hexdigest()
    counts = {}
    for b in brands:
        for s in b["sources"]:
            counts[s["source"]] = counts.get(s["source"], 0) + 1
    with open(p("meta.json"), "w", encoding="utf-8") as f:
        json.dump({"version": version, "generatedAt": catalog["generatedAt"], "brandCount": len(brands),
                   "sourceCounts": counts, "catalog": "catalog.json", "catalogSha256": sha, "contentSha256": digest,
                   "mode": "eski-liste"}, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    with_logo = sum(1 for b in brands if (b.get("logoURL") or "").startswith("https://cdn.jsdelivr"))
    print(f"{len(brands)} marka, sürüm {version}, depodaki logo: {with_logo}, kaynaklar: {counts}")


if __name__ == "__main__":
    sys.exit(main())
