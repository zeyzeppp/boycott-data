#!/usr/bin/env python3
"""Eski listeyi (guncellenmis_liste.json) esas alarak Boykot Dedektifi + bykt.org birleşik listesi.

Kurallar (Zeynep, 2026-11-09):
- Eski listedeki markalar ve eşleşmeleri korunur; yalnızca boykot durumları / kanıt adresleri / görseller güncellenir.
- Eski listede ayrı duran ama adı yazım farkıyla aynı olanlar birleştirilir (Coca-Cola, 7 Days–7Days, KitKat…).
- Elle kararlar: config/eslesme_kararlari_bd_bykt.json  {"birlestir": [[bykt adresi, dedektif adresi]], "ayri": [[bykt adresi, dedektif adresi]]}
- Yeni markalar: adı aynıysa (yazım farkı dahil) otomatik eşleşir; parantez farkı ya da benzerlik varsa kullanıcıya sorulur.

Kullanım:
  python scraper/eski_tabanli.py --veriler veriler --eski guncellenmis_liste.json --kararlar config/eslesme_kararlari_bd_bykt.json \
      --out birlesik_liste.json [--sorular sorular.html]
"""
import argparse
import json
import os
import re
import sys
import urllib.parse
import uuid
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import compact, metin_temizle  # noqa: E402

NS = uuid.UUID("6f1c2a52-6d1e-4b8e-9a52-0b5f7c1d3e21")
F = {"bd": ("boykot_dedektifi_boykot_durumu", "boykot_dedektifi_kanit_url"),
     "by": ("bykt_org_boykot_durumu", "bykt_org_kanit_url")}
STOP = {"the", "and", "ve", "co", "inc", "group", "grup", "holding", "company", "turkiye", "turkey", "global", "ltd"}


def uk(u):
    return urllib.parse.unquote(u or "").strip().rstrip("/").lower()


def slugkey(u):
    s = uk(u).rsplit("/", 1)[-1].replace("ı", "i")
    s = re.sub(r"-\d+$", "", s) if "boykotdedektifi" in uk(u) else s
    return re.sub(r"[^0-9a-zğüşöçâîû]+", "", s)


def bd_id(u):
    m = re.search(r"-(\d+)$", uk(u))
    return m.group(1) if m else None


def base_name(name):
    return metin_temizle(re.sub(r"\([^)]*\)", " ", name)) or metin_temizle(name)


def name_keys(name):
    k = metin_temizle(name)
    return k, compact(k), compact(base_name(name))


def plausible(a, b):
    """Benzer olma ihtimali olan iki ad (soru sormaya değer mi?)."""
    ka, kb = base_name(a), base_name(b)
    ca, cb = compact(ka), compact(kb)
    if min(len(ca), len(cb)) >= 4 and (ca in cb or cb in ca):
        return True
    wa = [w for w in ka.split() if w not in STOP]
    wb = [w for w in kb.split() if w not in STOP]
    if wa and wb and wa[0] == wb[0] and len(wa[0]) >= 3:
        return True
    from difflib import SequenceMatcher
    return min(len(ca), len(cb)) >= 5 and SequenceMatcher(None, ca, cb).ratio() >= 0.86


class Row:
    __slots__ = ("id", "name", "cat", "img", "bd", "by", "old", "old_bd", "old_by", "updated")

    def __init__(self, **k):
        for s in self.__slots__:
            setattr(self, s, k.get(s))


def resolve_source(rows, entries, src):
    """Eski satırları yeni kayıtlara bağlar (adres → Dedektif kimliği → adres harfleri → ad)."""
    by_url = {uk(e["kanit_url"]): e for e in entries}
    by_slug, by_name, by_id, by_base = {}, {}, {}, {}
    for e in entries:
        by_slug.setdefault(slugkey(e["kanit_url"]), e)
        by_name.setdefault(metin_temizle(e["marka_adi"]), e)
        by_base.setdefault(compact(base_name(e["marka_adi"])), e)
        if src == "bd":
            by_id.setdefault(bd_id(e["kanit_url"]), e)
    claimed = {}
    attr = "old_" + src
    for r in rows:
        old = getattr(r, attr)
        if not old:
            continue
        u = old["url"]
        e = (by_url.get(uk(u)) or (src == "bd" and by_id.get(bd_id(u))) or by_slug.get(slugkey(u))
             or by_name.get(metin_temizle(old["name"])) or by_base.get(compact(base_name(old["name"]))))
        if e:
            claimed.setdefault(e["kanit_url"], []).append(r)
            setattr(r, src, e)
    return claimed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--veriler", required=True)
    ap.add_argument("--eski", required=True)
    ap.add_argument("--kararlar")
    ap.add_argument("--out", required=True)
    ap.add_argument("--sorular")
    ap.add_argument("--rapor")
    a = ap.parse_args()
    bd = json.load(open(os.path.join(a.veriler, "boykot_dedektifi.json"), encoding="utf-8"))["markalar"]
    by = json.load(open(os.path.join(a.veriler, "bykt_org.json"), encoding="utf-8"))["markalar"]
    old = json.load(open(a.eski, encoding="utf-8"))
    dec = json.load(open(a.kararlar, encoding="utf-8")) if a.kararlar and os.path.exists(a.kararlar) else {}
    out, questions, rep, _ = birlestir(bd, by, old, dec)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    both = sum(1 for x in out if x["boykot_dedektifi_kanit_url"] and x["bykt_org_kanit_url"])
    print(f"{a.out}: {len(out)} marka — ikisinde de {both}, yalnız Dedektif "
          f"{sum(1 for x in out if not x['bykt_org_kanit_url'])}, yalnız bykt {sum(1 for x in out if not x['boykot_dedektifi_kanit_url'])}; "
          f"soru {len(questions)}")
    if a.rapor:
        with open(a.rapor, "w", encoding="utf-8") as f:
            f.write("\n".join(rep) + "\n")
    if a.sorular:
        write_questions(a.sorular, questions, bd)


def birlestir(bd, by, old, dec, yeni=True, yalniz_durum=False, now=None):
    """old: eski/ana liste satırları. bd/by: taze kayıtlar (veriler/ biçimi).
    yeni=False → sitelere yeni eklenen markalar listeye eklenmez (yalnız raporlanır).
    yalniz_durum=True → mevcut markaların adı/kategorisi/görseli değişmez; yalnız durumlar ve kanıt adresleri.
    Döner: (satırlar, sorular, rapor satırları, durum değişiklikleri [(ad, kaynak, eski, yeni)])."""
    rep = []
    rows = []
    for r in old:
        rows.append(Row(
            id=r["id"], name=r["marka_adi"], cat=r.get("kategori"), img=r.get("marka_gorselinin_dosya_yolu"),
            old=r, updated=r.get("updated_at"),
            old_bd={"url": r["boykot_dedektifi_kanit_url"], "name": r["marka_adi"]} if r.get("boykot_dedektifi_kanit_url") else None,
            old_by={"url": r["bykt_org_kanit_url"], "name": r["marka_adi"]} if r.get("bykt_org_kanit_url") else None))

    # 1) Eski satırları yeni verilere bağla
    for src, entries in (("bd", bd), ("by", by)):
        claimed = resolve_source(rows, entries, src)
        # Aynı kayda bağlanan eski satırlar (eski listede tekrar edenler) tek satırda toplanır
        for url, rs in claimed.items():
            if len(rs) < 2:
                continue
            keep = rs[0]
            for r in rs[1:]:
                other = "by" if src == "bd" else "bd"
                ko, ro = getattr(keep, "old_" + other), getattr(r, "old_" + other)
                if ro and ko and getattr(keep, other) is not getattr(r, other):
                    rep.append(f"çakışma (ayrı bırakıldı): {keep.name} / {r.name} aynı {src} kaydına bağlı")
                    setattr(r, src, None)
                    continue
                if ro and not ko:
                    setattr(keep, "old_" + other, ro)
                    setattr(keep, other, getattr(r, other))
                rep.append(f"tekrar eden satır birleştirildi: {r.name} → {keep.name}")
                rows.remove(r)

    def merge_rows(rd, ry, why):
        """rd: Dedektif satırı, ry: yalnız bykt satırı → tek satır (Dedektif satırı kalır)."""
        rd.by, rd.old_by = ry.by, ry.old_by
        rows.remove(ry)
        rep.append(f"birleştirildi ({why}): {ry.name} (bykt) + {rd.name} (Dedektif)")

    def find_row(src, url):
        for r in rows:
            e = getattr(r, src)
            if e and uk(e["kanit_url"]) == uk(url):
                return r
        return None

    def new_row(src, e):
        r = Row(id=None, name=e["marka_adi"], cat=e.get("kategori"), img=e.get("resim_url"))
        setattr(r, src, e)
        rows.append(r)
        return r

    # 2) Eski listede olmayan yeni kayıtlar için satır aç
    have = {s: {uk(getattr(r, s)["kanit_url"]) for r in rows if getattr(r, s)} for s in ("bd", "by")}
    new_entries = []
    for src, entries in (("bd", bd), ("by", by)):
        for e in entries:
            if uk(e["kanit_url"]) not in have[src]:
                have[src].add(uk(e["kanit_url"]))   # sitede aynı adres iki kez geçebiliyor (bykt: Morfose)
                if yeni:
                    new_row(src, e)
                else:
                    new_entries.append((src, e))
    for src, e in new_entries:
        rep.append(f"yeni marka (haftalık eşleştirmede eklenecek): {e['marka_adi']} ({'Dedektif' if src == 'bd' else 'bykt.org'})")

    # 3) Elle kararlar
    separate = {(uk(y), uk(d)) for y, d in dec.get("ayri", [])}
    # Önceden (otomatik) birleşmiş ama sonradan "ayrı" denen satırlar ikiye ayrılır
    for r in list(rows):
        if r.bd and r.by and (uk(r.by["kanit_url"]), uk(r.bd["kanit_url"])) in separate:
            nr = Row(id=None, name=r.by["marka_adi"], cat=r.by.get("kategori"), img=r.by.get("resim_url"))
            nr.by = r.by
            r.by, r.old_by = None, None
            if r.old is not None:
                r.old = dict(r.old, **{F["by"][0]: None, F["by"][1]: None})
            rows.append(nr)
            rep.append(f"ayrıldı (sizin kararınız): {nr.name} (bykt) ↔ {r.name} (Dedektif)")
    for y, d in dec.get("birlestir", []):
        ry, rd = find_row("by", y), find_row("bd", d)
        if not ry or not rd:
            rep.append(f"karar uygulanamadı (adres bulunamadı): {y} ↔ {d}")
            continue
        if ry is rd:
            continue
        if rd.by or ry.bd:
            rep.append(f"karar uygulanamadı (zaten başka markayla eşli): {ry.name} ↔ {rd.name}")
            continue
        merge_rows(rd, ry, "sizin kararınız")

    # 4) Otomatik: yazım farkıyla aynı ad → birleşir; parantez farkı / benzer → sorulur
    questions = []
    free_bd = [r for r in rows if r.bd and not r.by]
    idx = [{}, {}, {}]
    for r in free_bd:
        for i, k in enumerate(name_keys(r.bd["marka_adi"])):
            idx[i].setdefault(k, []).append(r)
    for ry in [r for r in rows if r.by and not r.bd]:
        ks = name_keys(ry.by["marka_adi"])
        cands = [c for c in (idx[0].get(ks[0], []) + idx[1].get(ks[1], [])) if not c.by]
        cands = [c for c in cands if (uk(ry.by["kanit_url"]), uk(c.bd["kanit_url"])) not in separate]
        if len({id(c) for c in cands}) == 1:
            merge_rows(cands[0], ry, "aynı ad")
            continue
        base = [c for c in idx[2].get(ks[2], []) if not c.by
                and (uk(ry.by["kanit_url"]), uk(c.bd["kanit_url"])) not in separate]
        sims = []
        if base:
            sims = base
        elif ry.old is None:     # yeni bykt markası: benzerleri sor
            sims = [c for c in free_bd if not c.by and plausible(ry.by["marka_adi"], c.bd["marka_adi"])
                    and (uk(ry.by["kanit_url"]), uk(c.bd["kanit_url"])) not in separate]
        else:                    # eski bykt markası: yalnız yeni Dedektif markalarıyla karşılaştır
            sims = [c for c in free_bd if not c.by and c.old is None and plausible(ry.by["marka_adi"], c.bd["marka_adi"])
                    and (uk(ry.by["kanit_url"]), uk(c.bd["kanit_url"])) not in separate]
        if sims:
            sims.sort(key=lambda c: -len(set(metin_temizle(c.bd["marka_adi"]).split()) & set(ks[0].split())))
            pre = base[0].bd["kanit_url"] if len(base) == 1 and "(" not in base[0].bd["marka_adi"] else None
            questions.append({"y": ry.by, "c": [c.bd for c in sims[:6]], "pre": pre})

    # 5) Satırları yaz
    now = now or datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    changes = []
    used = set()
    out = []
    for r in rows:
        D, Y = r.bd, r.by
        rid = r.id if r.id and r.id not in used else str(uuid.uuid5(NS, (D or Y or {"kanit_url": r.name})["kanit_url"]))
        used.add(rid)
        o = r.old or {}
        keep = yalniz_durum and r.old is not None
        row = {
            "id": rid,
            "marka_adi": r.name if keep else (D["marka_adi"] if D else (Y["marka_adi"] if Y else r.name)),
            "kategori": r.cat if keep else (D["kategori"] if D else (Y["kategori"] if Y else r.cat)),
            "marka_gorselinin_dosya_yolu": r.img if keep else ((D and D.get("resim_url")) or (Y and Y.get("resim_url")) or r.img),
            "boykot_dedektifi_boykot_durumu": D["boykot_durumu"] if D else o.get(F["bd"][0]),
            "boykot_dedektifi_kanit_url": D["kanit_url"] if D else o.get(F["bd"][1]),
            "bykt_org_boykot_durumu": Y["boykot_durumu"] if Y else o.get(F["by"][0]),
            "bykt_org_kanit_url": Y["kanit_url"] if Y else o.get(F["by"][1]),
            "updated_at": now,
        }
        if keep:
            # bykt satırı Dedektif satırına yeni birleştiyse görsel boşsa doldur
            row["marka_gorselinin_dosya_yolu"] = row["marka_gorselinin_dosya_yolu"] or (D and D.get("resim_url")) or (Y and Y.get("resim_url"))
        changed = False
        for src in ("bd", "by"):
            before, after = o.get(F[src][0]), row[F[src][0]]
            if r.old is not None and before != after:
                changes.append((row["marka_adi"], "Boykot Dedektifi" if src == "bd" else "bykt.org", before, after))
                changed = True
        if r.old is not None and not changed and all(o.get(F[s][1]) == row[F[s][1]] for s in ("bd", "by")):
            row["updated_at"] = o.get("updated_at") or now
        if r.old and not D and r.old_bd:
            rep.append(f"Dedektif'te artık yok (eski durum korundu): {r.name}")
        if r.old and not Y and r.old_by:
            rep.append(f"bykt.org'da artık yok (eski durum korundu): {r.name}")
        out.append(row)
    out.sort(key=lambda x: metin_temizle(x["marka_adi"]))
    if not yeni:
        questions = [q for q in questions if False]   # yeni marka eklenmiyorsa soru da yok
    return out, questions, rep, changes


def write_questions(path, questions, bd):
    items = [{"k": q["y"]["kanit_url"], "n": q["y"]["marka_adi"], "l": q["y"].get("resim_url"), "c": q["y"].get("kategori") or "",
              "s": q["y"]["boykot_durumu"], "auto": q["pre"], "how": "benzer" if q["pre"] else None, "same": False, "dup": False,
              "sug": [] if q["pre"] else [c["kanit_url"] for c in q["c"]]} for q in questions]
    items.sort(key=lambda i: metin_temizle(i["n"]))
    bd_list = [{"k": b["kanit_url"], "n": b["marka_adi"], "l": b.get("resim_url"),
                "c": (b.get("kategoriler") or [b.get("kategori")])[:3], "s": b["boykot_durumu"]} for b in bd]
    tpl = open(os.path.join(HERE, "eslestirme_bd_bykt.tpl.html"), encoding="utf-8").read()
    page = tpl.replace("/*DATA*/null", json.dumps({"bd": bd_list, "by": items}, ensure_ascii=False).replace("</", "<\\/"))
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)


if __name__ == "__main__":
    main()
