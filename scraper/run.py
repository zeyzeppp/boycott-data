#!/usr/bin/env python3
"""Gece taraması: Boykot Dedektifi + boykot.co → catalog.json, meta.json, logos/.

Kullanım:  python scraper/run.py [--root .] [--no-logos]
Çıkış kodu: 0 = yayınlanabilir, 2 = güvenlik kontrolü durdurdu (yayınlanmaz; Issue açılır).
Her durumda `report.md` yazılır (Actions bunu Issue/özet olarak kullanır).
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from common import Http  # noqa: E402
from logos import update_logos  # noqa: E402
from merge import SOURCES, build, carry_over, load_products  # noqa: E402
from sources import bc_crawl, bd_crawl  # noqa: E402

MIN_FIRST_RUN = {"boykotdedektifi": 1000, "boykotco": 300}
MAX_DROP = 0.10   # bir kaynaktan ya da toplamda %10'dan fazla düşüş → yayınlama


def read(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write(path, data, indent=1):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent, sort_keys=True)
        f.write("\n")


def safety(fresh_counts, prev_counts, total, prev_total):
    problems = []
    for s in SOURCES:
        n, p = fresh_counts.get(s, 0), prev_counts.get(s)
        if n == 0:
            problems.append(f"{s}: hiç marka okunamadı (site yapısı değişmiş olabilir)")
        elif p is None and n < MIN_FIRST_RUN[s]:
            problems.append(f"{s}: ilk taramada beklenenden az marka ({n} < {MIN_FIRST_RUN[s]})")
        elif p and n < p * (1 - MAX_DROP):
            problems.append(f"{s}: marka sayısı {p} → {n} (%{round(100 * (p - n) / p)} düşüş)")
    if prev_total and total < prev_total * (1 - MAX_DROP):
        problems.append(f"toplam marka sayısı {prev_total} → {total}")
    return problems


def pending_report(pending, bd, bc):
    lines = ["## Onay bekleyen eşleşmeler", "",
             "Aşağıdaki markalar iki sitede **benzer adla** geçiyor. Aynı marka mı?",
             "Cevabınız `config/eslesmeler.json`'a işlenir (aynı marka → `birlestir`, farklı → `ayri`).", "",
             "| # | boykot.co | Boykot Dedektifi | Benzerlik |", "|---|---|---|---|"]
    for i, p in enumerate(pending, 1):
        a, b = bc[p["boykotco"]], bd[p["dedektif"]]

        def cell(e):
            img = f'<img src="{e["logo"]}" width="48"><br>' if e.get("logo") else ""
            cats = ", ".join(e.get("categories") or []) or "—"
            desc = (e.get("desc") or "")[:120]
            return f'{img}**[{e["name"]}]({e["url"]})**<br>{cats}<br><sub>{desc}</sub>'
        lines.append(f"| {i} | {cell(a)} | {cell(b)} | {p['benzerlik']} |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.dirname(HERE))
    ap.add_argument("--no-logos", action="store_true")
    ap.add_argument("--delay", type=float, default=1.0)
    a = ap.parse_args()
    root = a.root
    p = lambda *x: os.path.join(root, *x)  # noqa: E731

    http = Http(delay=a.delay)
    report = [f"# Tarama raporu — {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC", ""]

    def log(msg):
        print(msg, flush=True)

    # 1) Tarama
    errors = []
    fresh = {}
    bd_cats = []
    try:
        fresh["boykotdedektifi"], bd_cats = bd_crawl(http, log)
    except Exception as e:
        errors.append(f"Boykot Dedektifi taranamadı: {e}")
        fresh["boykotdedektifi"] = {}
    try:
        fresh["boykotco"], _ = bc_crawl(http, log)
    except Exception as e:
        errors.append(f"boykot.co taranamadı: {e}")
        fresh["boykotco"] = {}

    # 2) Kaldırma kuralı (2 tarama)
    seen_state = read(p("state", "gorulme.json"), {})
    used = {}
    new_seen = {}
    for s in SOURCES:
        used[s], new_seen[s] = carry_over(fresh[s], seen_state.get(s), s)

    # 3) Birleştirme
    decisions = read(p("config", "eslesmeler.json"), {"birlestir": {}, "ayri": []})
    cat_table = {k: v for k, v in read(p("config", "kategori_esleme.json"), {}).items() if not k.startswith("_")}
    ids = read(p("state", "ids.json"), {})
    products = load_products(read(p("config", "alt_markalar.json"), {}))
    brands, pending = build(used["boykotdedektifi"], used["boykotco"], decisions, cat_table, ids, products)

    unmapped = sorted({c for e in used["boykotco"].values() for c in e["categories"] if c not in cat_table})
    bad_targets = sorted({v for v in cat_table.values() if bd_cats and v not in bd_cats})

    # 4) Güvenlik kontrolü
    meta_prev = read(p("meta.json"), {})
    counts = {s: len(fresh[s]) for s in SOURCES}
    problems = errors + safety(counts, meta_prev.get("sourceCounts", {}), len(brands), meta_prev.get("brandCount"))

    report += [f"- Boykot Dedektifi: {counts['boykotdedektifi']} marka", f"- boykot.co: {counts['boykotco']} marka",
               f"- Birleşik katalog: {len(brands)} marka", f"- İstek sayısı: {http.requests}", ""]
    if unmapped:
        report += ["**Kategori eşlemesi olmayan boykot.co kategorileri** (config/kategori_esleme.json'a eklenmeli): "
                   + ", ".join(unmapped), ""]
    if bad_targets:
        report += ["**Boykot Dedektifi'nde artık olmayan hedef kategoriler** (config/kategori_esleme.json): "
                   + ", ".join(bad_targets), ""]
    if problems:
        report += ["## ⚠️ Yayınlanmadı", ""] + [f"- {x}" for x in problems] + [""]
    if pending:
        report += [pending_report(pending, used["boykotdedektifi"], used["boykotco"]), ""]
    write(p("state", "bekleyen.json"), pending)

    if problems:
        open(p("report.md"), "w", encoding="utf-8").write("\n".join(report))
        print("\n".join(report))
        return 2

    # 5) Logolar
    logo_state = read(p("state", "logolar.json"), {})
    if not a.no_logos:
        # Süre sınırı: ilk taramada ~3500 logo var; yetişmeyenler sonraki gecelere kalır (Actions süre sınırı)
        fetched, failed = update_logos(brands, http, root, logo_state, log, budget_s=45 * 60)
        report.append(f"- Logolar: {fetched} yeni/güncellenen, {failed} alınamadı")
    else:
        for b in brands:
            b["logoURL"] = None

    # 6) updatedAt: içerik değişmediyse önceki tarih kalır
    prev_catalog = read(p("catalog.json"), {"brands": []})
    prev_by_id = {b["id"]: b for b in prev_catalog.get("brands", [])}
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for b in brands:
        logo_src = b.pop("_logo_src", None)  # noqa: F841
        b.pop("_key", None)
        old = prev_by_id.get(b["id"])
        same = old and {k: v for k, v in old.items() if k != "updatedAt"} == {k: v for k, v in b.items() if k != "updatedAt"}
        b["updatedAt"] = old["updatedAt"] if same else now

    body = json.dumps(brands, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(body.encode()).hexdigest()
    changed = digest != meta_prev.get("contentSha256")
    version = int(dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H")) if changed else meta_prev.get("version", 1)
    catalog = {"version": version, "generatedAt": now if changed else prev_catalog.get("generatedAt", now), "brands": brands}
    write(p("catalog.json"), catalog, indent=None)
    cat_sha = hashlib.sha256(open(p("catalog.json"), "rb").read()).hexdigest()
    write(p("meta.json"), {
        "version": version,
        "generatedAt": catalog["generatedAt"],
        "brandCount": len(brands),
        "sourceCounts": counts,
        "catalog": "catalog.json",
        "catalogSha256": cat_sha,
        "contentSha256": digest,
    })
    write(p("state", "gorulme.json"), new_seen, indent=None)
    write(p("state", "ids.json"), ids, indent=0)
    write(p("state", "logolar.json"), logo_state, indent=0)
    report.append(f"- Sürüm: {version} ({'değişti' if changed else 'değişiklik yok'})")
    open(p("report.md"), "w", encoding="utf-8").write("\n".join(report))
    print("\n".join(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
