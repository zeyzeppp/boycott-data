#!/usr/bin/env python3
"""Soru sayfasının çıktısını (eslesme_kararlari.json) config/eslesme_kararlari_bd_bykt.json'a ekler.

Kullanım: python scraper/kararlari_isle.py --sayfa sorular.html --cikti eslesme_kararlari.json --config config/eslesme_kararlari_bd_bykt.json
- Eşleştirilenler → "birlestir"
- "Dedektif'te yok" / "Yanlış eşleşme" / karar verilmeyenler → sayfada gösterilen adaylarla "ayri" (bir daha sorulmaz)
"""
import argparse
import json
import re


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sayfa", required=True)
    ap.add_argument("--cikti", required=True)
    ap.add_argument("--config", required=True)
    a = ap.parse_args()
    html = open(a.sayfa, encoding="utf-8").read()
    data = json.loads(re.search(r"const DATA = (.*);\n", html).group(1).replace("<\\/", "</"))
    items = {i["k"]: i for i in data["by"]}
    out = json.load(open(a.cikti, encoding="utf-8"))
    cfg = json.load(open(a.config, encoding="utf-8"))
    birlestir = {tuple(p) for p in cfg.get("birlestir", [])}
    ayri = {tuple(p) for p in cfg.get("ayri", [])}
    matched = set()
    for p in out.get("eslesmeler", []):
        if p["bykt"] in items:
            birlestir.add((p["bykt"], p["dedektif"]))
            matched.add(p["bykt"])
    for k, i in items.items():
        if k in matched:
            continue
        for d in (i.get("sug") or []) + ([i["auto"]] if i.get("auto") else []):
            ayri.add((k, d))
    cfg["birlestir"] = sorted(map(list, birlestir))
    cfg["ayri"] = sorted(map(list, ayri))
    with open(a.config, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"{a.config}: birlestir {len(cfg['birlestir'])}, ayri {len(cfg['ayri'])}")


if __name__ == "__main__":
    main()
