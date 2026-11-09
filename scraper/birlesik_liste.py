#!/usr/bin/env python3
"""Boykot Dedektifi + bykt.org → tek liste (guncellenmis_liste.json biçiminde).

Eşleşmeler eslesme_kararlari.json'dan (eslestirme_bd_bykt.html çıktısı) gelir.
- Ad, kategori, görsel: Boykot Dedektifi esas; markası yalnız bykt.org'da olanlar için bykt.org.
- id: eski listedeki satır (kanıt adresi ya da ad üzerinden) bulunursa onun id'si korunur.
"""
import argparse
import json
import os
import sys
import urllib.parse
import uuid
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import metin_temizle  # noqa: E402

NS = uuid.UUID("6f1c2a52-6d1e-4b8e-9a52-0b5f7c1d3e21")


def uk(u):
    return urllib.parse.unquote(u or "").strip().rstrip("/").lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bd", required=True)
    ap.add_argument("--bykt", required=True)
    ap.add_argument("--eski", required=True)
    ap.add_argument("--kararlar", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    bd = json.load(open(a.bd, encoding="utf-8"))
    by = json.load(open(a.bykt, encoding="utf-8"))
    old = json.load(open(a.eski, encoding="utf-8"))
    dec = json.load(open(a.kararlar, encoding="utf-8"))

    bd_url = {uk(b["kanit_url"]): b for b in bd["markalar"]}
    by_url = {uk(b["kanit_url"]): b for b in by["markalar"]}
    pair = {}                                     # bd adresi → bykt kaydı
    for p in dec["eslesmeler"]:
        B, D = by_url.get(uk(p["bykt"])), bd_url.get(uk(p["dedektif"]))
        if not B or not D:
            sys.exit(f"Bilinmeyen adres: {p}")
        if uk(p["dedektif"]) in pair:
            print(f"uyarı: {D['marka_adi']} birden çok bykt markasına bağlı; ilki kullanılıyor "
                  f"({pair[uk(p['dedektif'])]['marka_adi']}, atlanan {B['marka_adi']})")
            continue
        pair[uk(p["dedektif"])] = B
    paired_by = {uk(b["kanit_url"]) for b in pair.values()}

    old_by_bd = {uk(r["boykot_dedektifi_kanit_url"]): r for r in old if r.get("boykot_dedektifi_kanit_url")}
    old_by_by = {uk(r["bykt_org_kanit_url"]): r for r in old if r.get("bykt_org_kanit_url")}
    old_by_name = {}
    for r in old:
        old_by_name.setdefault(metin_temizle(r["marka_adi"]), r)
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    used_ids = set()

    def pick_id(*cands, seed):
        for r in cands:
            if r and r.get("id") and r["id"] not in used_ids:
                used_ids.add(r["id"])
                return r["id"]
        i = str(uuid.uuid5(NS, seed))
        used_ids.add(i)
        return i

    rows = []
    for D in bd["markalar"]:
        B = pair.get(uk(D["kanit_url"]))
        rid = pick_id(old_by_bd.get(uk(D["kanit_url"])), B and old_by_by.get(uk(B["kanit_url"])),
                      old_by_name.get(metin_temizle(D["marka_adi"])), seed="bd:" + D["kanit_url"])
        rows.append({
            "id": rid, "marka_adi": D["marka_adi"], "kategori": D["kategori"],
            "marka_gorselinin_dosya_yolu": D.get("resim_url") or (B and B.get("resim_url")),
            "boykot_dedektifi_boykot_durumu": D["boykot_durumu"], "boykot_dedektifi_kanit_url": D["kanit_url"],
            "bykt_org_boykot_durumu": B["boykot_durumu"] if B else None, "bykt_org_kanit_url": B["kanit_url"] if B else None,
            "updated_at": now,
        })
    for B in by["markalar"]:
        if uk(B["kanit_url"]) in paired_by:
            continue
        rid = pick_id(old_by_by.get(uk(B["kanit_url"])), old_by_name.get(metin_temizle(B["marka_adi"])),
                      seed="bykt:" + B["kanit_url"])
        rows.append({
            "id": rid, "marka_adi": B["marka_adi"], "kategori": B["kategori"],
            "marka_gorselinin_dosya_yolu": B.get("resim_url"),
            "boykot_dedektifi_boykot_durumu": None, "boykot_dedektifi_kanit_url": None,
            "bykt_org_boykot_durumu": B["boykot_durumu"], "bykt_org_kanit_url": B["kanit_url"],
            "updated_at": now,
        })
    rows.sort(key=lambda r: metin_temizle(r["marka_adi"]))
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    both = sum(1 for r in rows if r["boykot_dedektifi_kanit_url"] and r["bykt_org_kanit_url"])
    print(f"{a.out}: {len(rows)} marka — ikisinde de {both}, yalnız Dedektif "
          f"{sum(1 for r in rows if not r['bykt_org_kanit_url'])}, yalnız bykt {sum(1 for r in rows if not r['boykot_dedektifi_kanit_url'])}")


if __name__ == "__main__":
    main()
