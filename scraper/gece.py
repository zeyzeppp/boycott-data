#!/usr/bin/env python3
"""Gece güncellemesi: ana listedeki (kaynak/birlesik_liste.json) markaların YALNIZCA boykot durumlarını
Boykot Dedektifi + bykt.org'dan günceller; catalog.json / meta.json / logos/ üretir.

Kurallar (Zeynep, 2026-11-09):
- Markalar, adları, kategorileri, görselleri ve eşleşmeleri değişmez; yalnız durumlar (ve değişirse kanıt adresi).
- Sitede artık bulunmayan markanın eski durumu korunur.
- Yeni markalar gece eklenmez. Haftalık modda (--haftalik ya da sorular/eslesme_kararlari.json yüklenmişse)
  yeni markalar eklenir; emin olunamayan eşleşmeler sorular/eslestirme_sorular.html sayfasında sorulur.
- Güvenlik: bir siteden gelen marka sayısı düşerse ya da bir gecede durumların çoğu değişirse yayınlanmaz.

Kullanım:  python scraper/gece.py [--root .] [--haftalik] [--no-logos] [--veriler DIR (internetsiz deneme)]
Çıkış: 0 = yayınlanabilir, 2 = güvenlik kontrolü durdurdu. Her durumda report.md yazılır.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import legacy  # noqa: E402
from eski_tabanli import birlestir, write_questions  # noqa: E402
from logos import CDN  # noqa: E402

BYKT_JSON = "https://bykt.org/brands.json"
BYKT_STATUS = {"red": "Kesin Boykot", "orange": "İnsafa Bağlı", "green": "Alınabilir"}
MIN_COUNT = {"bd": 2500, "by": 1000}     # ilk çalıştırmada beklenen en az marka
MAX_DROP = 0.10                          # bir siteden gelen marka sayısı %10'dan fazla düşerse durdur
MAX_CHANGE = 0.05                        # bir gecede markaların %5'inden fazlasının durumu değişirse durdur
LOGO_BUDGET_S = 30 * 60


def read(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write(path, data, indent=1):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)
        f.write("\n")


def bykt_slug(name):
    """bykt.org'un kendi adres kuralı (sitedeki z() fonksiyonu)."""
    s = str(name).replace("İ", "i").replace("I", "i").lower().strip()
    s = re.sub(r"[^\w]+|_", lambda m: "_" if m.group(0) == "_" else "-", s)
    return s.strip("-")


def fetch_bykt(http):
    data = json.loads(http.get(BYKT_JSON) or "[]")
    out = []
    for b in data:
        name = (b.get("name") or "").strip()
        if not name:
            continue
        slug = bykt_slug(name)
        out.append({
            "marka_adi": name, "kategori": b.get("sector") or "",
            "boykot_durumu": BYKT_STATUS.get(b.get("status"), b.get("status") or ""),
            "resim_url": b.get("logo") or f"https://bykt.org/logos-card/{slug}.webp",
            "kanit_url": f"https://bykt.org/marka/{slug}",
        })
    return out


def fetch_bd(http, log):
    from sources import bd_crawl
    raw, _ = bd_crawl(http, log=log, key_by_url=True)
    return [{"marka_adi": e["name"], "kategori": (e["categories"] or [""])[0], "kategoriler": e["categories"],
             "boykot_durumu": e["label"], "resim_url": e.get("logo"), "kanit_url": e["url"]} for e in raw.values()]


def build_catalog(root, items, prev_meta, have_logo):
    """Ana liste → catalog.json + meta.json (uygulamaların okuduğu biçim)."""
    brands = legacy.convert(items)
    for b in brands:
        b["categories"] = [b["category"]] if b.get("category") else []
        if b["id"] in have_logo:
            b["logoURL"] = CDN.format(id=b["id"])
    body = json.dumps(brands, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(body.encode()).hexdigest()
    now = dt.datetime.now(dt.timezone.utc)
    if digest == prev_meta.get("contentSha256"):
        return brands, prev_meta, False
    version = max(int(now.strftime("%Y%m%d%H")), prev_meta.get("version", 0) + 1)
    catalog = {"version": version, "generatedAt": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "brands": brands}
    with open(os.path.join(root, "catalog.json"), "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, sort_keys=True)
        f.write("\n")
    sha = hashlib.sha256(open(os.path.join(root, "catalog.json"), "rb").read()).hexdigest()
    counts = {}
    for b in brands:
        for s in b["sources"]:
            counts[s["source"]] = counts.get(s["source"], 0) + 1
    meta = {"version": version, "generatedAt": catalog["generatedAt"], "brandCount": len(brands),
            "sourceCounts": counts, "catalog": "catalog.json", "catalogSha256": sha, "contentSha256": digest,
            "mode": "canli-durum"}
    with open(os.path.join(root, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    return brands, meta, True


def download_logos(root, items, have, log, budget_s):
    """Depoda logosu olmayan markaların logolarını indirir (logos/<id>.webp, 256 px)."""
    from common import Http
    from logos import update_logos
    todo = []
    for it in items:
        if it["id"] in have:
            continue
        src = legacy.logo_url(it)
        if src:
            todo.append({"id": it["id"], "name": it["marka_adi"], "_logo_src": src})
    if not todo:
        return 0, 0
    state_path = os.path.join(root, "state", "logolar.json")
    state = read(state_path, {})
    # update_logos artık katalogda olmayan logoları da siler; ona tüm kimlikleri veriyoruz
    keep = [{"id": i, "name": "", "_logo_src": None} for i in have]
    fetched, failed = update_logos(todo + keep, Http(delay=0.3), root, state, log=log, budget_s=budget_s)
    write(state_path, state)
    return fetched, failed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.path.dirname(HERE))
    ap.add_argument("--haftalik", action="store_true", help="yeni markaları ekle ve belirsizleri sor")
    ap.add_argument("--no-logos", action="store_true")
    ap.add_argument("--veriler", help="tarama yerine bu klasördeki boykot_dedektifi.json / bykt_org.json (deneme)")
    ap.add_argument("--zorla", action="store_true", help="durum değişikliği sınırını yok say (elle onaylı çalıştırma)")
    a = ap.parse_args()
    root = a.root
    P = lambda *x: os.path.join(root, *x)  # noqa: E731
    log = print
    report = [f"# Güncelleme — {dt.datetime.now(dt.timezone(dt.timedelta(hours=3))).strftime('%Y-%m-%d %H:%M')} (TSİ)", ""]

    master = read(P("kaynak", "birlesik_liste.json"))
    if master is None:
        sys.exit("kaynak/birlesik_liste.json yok")
    dec = read(P("config", "eslesme_kararlari_bd_bykt.json"), {})

    # Kullanıcının yüklediği eşleştirme kararları (GitHub'a sorular/eslesme_kararlari.json olarak)
    uploaded = P("sorular", "eslesme_kararlari.json")
    page = P("sorular", "eslestirme_sorular.html")
    haftalik = a.haftalik
    if os.path.exists(uploaded) and os.path.exists(page):
        import subprocess
        subprocess.run([sys.executable, os.path.join(HERE, "kararlari_isle.py"), "--sayfa", page,
                        "--cikti", uploaded, "--config", P("config", "eslesme_kararlari_bd_bykt.json")], check=True)
        dec = read(P("config", "eslesme_kararlari_bd_bykt.json"), {})
        os.makedirs(P("sorular", "islenmis"), exist_ok=True)
        stamp = dt.date.today().isoformat()
        shutil.move(uploaded, P("sorular", "islenmis", f"kararlar_{stamp}.json"))
        shutil.move(page, P("sorular", "islenmis", f"sorular_{stamp}.html"))
        report.append("✅ Yüklediğiniz eşleştirme kararları işlendi.")
        haftalik = True
    elif haftalik and os.path.exists(page):
        # Önceki haftanın soruları cevaplanmadan yeni marka eklenmez (sorular birbirine karışmasın)
        haftalik = False
        report.append("⏳ Önceki eşleştirme soruları cevap bekliyor; yeni markalar cevaptan sonra eklenecek.")

    # 1) Tara
    if a.veriler:
        bd = read(os.path.join(a.veriler, "boykot_dedektifi.json"))["markalar"]
        by = read(os.path.join(a.veriler, "bykt_org.json"))["markalar"]
    else:
        from common import Http
        http = Http(delay=1.0)
        bd = fetch_bd(http, log)
        by = fetch_bykt(http)
    counts = {"bd": len({e["kanit_url"] for e in bd}), "by": len({e["kanit_url"] for e in by})}

    # 2) Güvenlik: sitelerden gelen marka sayısı
    prev_counts = read(P("state", "sayilar.json"), {})
    problems = []
    names = {"bd": "Boykot Dedektifi", "by": "bykt.org"}
    for s, n in counts.items():
        p = prev_counts.get(s)
        if n == 0:
            problems.append(f"{names[s]}: hiç marka okunamadı (site yapısı değişmiş olabilir)")
        elif p is None and n < MIN_COUNT[s]:
            problems.append(f"{names[s]}: beklenenden az marka ({n} < {MIN_COUNT[s]})")
        elif p and n < p * (1 - MAX_DROP):
            problems.append(f"{names[s]}: marka sayısı {p} → {n} (%{round(100 * (p - n) / p)} düşüş)")

    # 3) Durumları güncelle
    out, questions, rep, changes = birlestir(bd, by, master, dec, yeni=haftalik, yalniz_durum=True)
    if len(changes) > len(master) * MAX_CHANGE and not a.zorla:
        problems.append(f"bir gecede {len(changes)} markanın durumu değişti (sınır %{int(MAX_CHANGE * 100)}). "
                        "Doğruysa Actions'ta 'zorla' seçeneğiyle yeniden çalıştırın.")

    report += [f"- Boykot Dedektifi: **{counts['bd']}** marka, bykt.org: **{counts['by']}** marka okundu",
               f"- Listede **{len(out)}** marka; durumu değişen: **{len(changes)}**", ""]
    if problems:
        report += ["## ⚠️ Yayınlanmadı", ""] + [f"- {p}" for p in problems] + [""]
    if changes:
        report += ["## Durumu değişenler", "", "| Marka | Kaynak | Önce | Şimdi |", "|---|---|---|---|"]
        report += [f"| {n} | {s} | {b or '—'} | {c or '—'} |" for n, s, b, c in changes[:300]]
        if len(changes) > 300:
            report.append(f"| … ve {len(changes) - 300} marka daha | | | |")
        report.append("")
    new_lines = [r for r in rep if r.startswith("yeni marka")]
    added = len(out) - len(master)
    if haftalik:
        report.append(f"- Yeni eklenen marka: **{added}**")
    elif new_lines:
        report.append(f"- Sitelerde listede olmayan **{len(new_lines)}** marka var; haftalık eşleştirmede eklenecek.")
    stale = [r for r in rep if "artık yok" in r]
    if stale:
        report += ["", "<details><summary>Sitede artık bulunmayan (eski durumu korunan) markalar: "
                   f"{len(stale)}</summary>", ""] + [f"- {r.split(': ', 1)[1]}" for r in stale] + ["", "</details>"]

    if problems:
        with open(P("report.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(report) + "\n")
        print("\n".join(report))
        return 2

    # 4) Yaz
    write(P("kaynak", "birlesik_liste.json"), out, indent=2)
    write(P("state", "sayilar.json"), counts)
    write(P("state", "son_tarama", "boykot_dedektifi.json"), {"markalar": bd})
    write(P("state", "son_tarama", "bykt_org.json"), {"markalar": by})
    if haftalik and questions:
        os.makedirs(os.path.dirname(page), exist_ok=True)
        write_questions(page, questions, bd)
        report += ["", f"## ❓ {len(questions)} eşleşme için kararınız gerekiyor", "",
                   "1. `sorular/eslestirme_sorular.html` dosyasını indirip tarayıcıda açın "
                   "(depoda dosyaya tıklayın → ⋯ → Download).",
                   "2. Seçimlerinizi yapıp **eslesme_kararlari.json**'u indirin.",
                   "3. Depoda `sorular/` klasörüne **Add file → Upload files** ile yükleyin. "
                   "Kararlarınız birkaç dakika içinde işlenir."]

    logo_dir = P("logos")
    def logo_ids():
        if not os.path.isdir(logo_dir):
            return set()
        return {f[:-5] for f in os.listdir(logo_dir) if f.endswith(".webp") and os.path.getsize(os.path.join(logo_dir, f)) > 0}
    have = logo_ids()
    if not a.no_logos:
        fetched, failed = download_logos(root, out, have, log, LOGO_BUDGET_S)
        have = logo_ids()
        if fetched or failed:
            report.append(f"- Logolar: {fetched} yeni indirildi, {failed} alınamadı")
    brands, meta, changed = build_catalog(root, out, read(P("meta.json"), {}), have)
    report.append(f"- Yayın: {'yeni sürüm **' + str(meta['version']) + '**' if changed else 'değişiklik yok'} "
                  f"({meta['brandCount']} marka)")
    with open(P("report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(report) + "\n")
    print("\n".join(report[:12]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
