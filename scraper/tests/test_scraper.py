"""python -m unittest discover -s scraper/tests  (internet gerektirmez; örnek sayfalarla)"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from common import metin_temizle, verdict  # noqa: E402
from merge import build, carry_over, resolve_keys  # noqa: E402
from sources import bc_parse_categories, bc_parse_category_page, bd_parse_categories, bd_parse_category_page  # noqa: E402


def sample(name):
    with open(os.path.join(HERE, "samples", name), encoding="utf-8") as f:
        return f.read()


class ParseTests(unittest.TestCase):
    def test_dedektif_categories(self):
        cats = bd_parse_categories(sample("dedektif_kategoriler.html"))
        self.assertEqual(cats[0], ("Araç Lastiği", "https://boykotdedektifi.com/c/arac-lastigi-88", 22))
        self.assertEqual(cats[1][0], "Bisküvi")

    def test_dedektif_category_page(self):
        cards, has_next = bd_parse_category_page(sample("dedektif_kategori_s3.html"))
        self.assertFalse(has_next)  # "Sonraki" devre dışı
        self.assertEqual([c["name"] for c in cards], ["Torku", "Twix", "Ülker", "Lays"])
        self.assertEqual(cards[0]["label"], "Uygun")
        self.assertEqual(cards[1]["label"], "Boykot")
        self.assertEqual(cards[1]["url"], "https://boykotdedektifi.com/b/twix-361")
        self.assertEqual(cards[1]["logo"], "https://boykotservisi.com/uploads/brands/twix-361.webp")
        self.assertEqual(cards[1]["meta"], ["Bisküvi", "Çikolata", "Dondurma"])
        self.assertTrue(cards[0]["desc"].startswith("Torku, Konya"))
        self.assertEqual(cards[2]["desc"], "")

    def test_boykotco(self):
        cats = bc_parse_categories(sample("boykotco_ana.html"))
        self.assertEqual([c[0] for c in cats], ["Kahve", "Gıda", "Teknoloji"])
        cards = bc_parse_category_page(sample("boykotco_kategori.html"))
        self.assertEqual([c["name"] for c in cards], ["Kahve Dünyası", "Tchibo", "Lay's"])
        self.assertEqual(cards[0]["url"], "https://www.boykot.co/d/kahve-dunyasi")
        self.assertIn("gstatic", cards[0]["logo"])
        self.assertEqual(cards[2]["logo"], "https://www.boykot.co/assets/images/logo/brand4/lays.webp")  # göreli adres

    def test_verdicts(self):
        self.assertEqual(verdict("Uygun"), "safe")
        self.assertEqual(verdict("Boykot"), "boycott")
        self.assertEqual(verdict("Şüpheli"), "caution")
        self.assertEqual(verdict("Boykot Listesinde"), "boycott")
        self.assertEqual(verdict(""), "unknown")


def bd_entry(name, label="Boykot", cats=("Bisküvi",)):
    return {"name": name, "label": label, "url": f"https://boykotdedektifi.com/b/{metin_temizle(name)}",
            "logo": f"https://boykotservisi.com/{metin_temizle(name)}.webp", "categories": list(cats), "desc": ""}


def bc_entry(name, cats=("Gıda",)):
    return {"name": name, "label": "Boykot Listesinde", "url": f"https://www.boykot.co/d/{metin_temizle(name)}",
            "logo": None, "categories": list(cats), "desc": ""}


class MergeTests(unittest.TestCase):
    def test_exact_and_punctuation_merge(self):
        bd = {"ulker": bd_entry("Ülker"), "lays": bd_entry("Lays", cats=("Cips",))}
        bc = {"ulker": bc_entry("Ülker"), "lay s": bc_entry("Lay's")}
        mapping, pending = resolve_keys(bd, bc, {})
        self.assertEqual(mapping, {"ulker": "ulker", "lay s": "lays"})
        self.assertEqual(pending, [])

    def test_similar_goes_to_pending_until_decided(self):
        bd = {"nescafe": bd_entry("Nescafé", cats=("Kahve",))}
        bc = {"nescafe gold": bc_entry("Nescafe Gold", cats=("Kahve",)), "starbucks": bc_entry("Starbucks")}
        mapping, pending = resolve_keys(bd, bc, {})
        self.assertEqual(mapping["nescafe gold"], "nescafe gold")       # henüz birleşmez
        self.assertEqual([p["boykotco"] for p in pending], ["nescafe gold"])
        # Kullanıcı "aynı" derse birleşir, "farklı" derse bir daha sorulmaz
        mapping, pending = resolve_keys(bd, bc, {"birlestir": {"Nescafe Gold": "Nescafé"}})
        self.assertEqual(mapping["nescafe gold"], "nescafe")
        self.assertEqual(pending, [])
        mapping, pending = resolve_keys(bd, bc, {"ayri": [["Nescafe Gold", "Nescafé"]]})
        self.assertEqual(pending, [])

    def test_build_categories_sources_ids(self):
        bd = {"ulker": bd_entry("Ülker", cats=("Bisküvi", "Kek")), "eti": bd_entry("Eti", "Uygun")}
        bc = {"ulker": bc_entry("Ülker"), "tchibo": bc_entry("Tchibo", cats=("Kahve",))}
        ids = {"ulker": "id-ulker"}
        brands, pending = build(bd, bc, {}, {"Kahve": "Kahve", "Gıda": "Temel Gıda"}, ids,
                                {"eti": ["Gong"]})
        by = {b["name"]: b for b in brands}
        self.assertEqual(by["Ülker"]["id"], "id-ulker")                  # eski kimlik korunur
        self.assertEqual(by["Ülker"]["category"], "Bisküvi")             # Dedektif kategorisi esas
        self.assertEqual(by["Ülker"]["categories"], ["Bisküvi", "Kek"])
        self.assertEqual([s["source"] for s in by["Ülker"]["sources"]], ["boykotdedektifi", "boykotco"])
        self.assertEqual(by["Tchibo"]["categories"], ["Kahve"])          # boykot.co → eşleme tablosu
        self.assertEqual(by["Eti"]["sources"][0]["verdict"], "safe")
        self.assertEqual(by["Eti"]["products"], ["Gong"])
        self.assertIn("tchibo", ids)                                     # yeni kimlik kaydedilir

    def test_user_can_split_auto_match(self):
        bd = {"dove": bd_entry("Dove")}
        bc = {"dove": bc_entry("Dove")}
        brands, _ = build(bd, bc, {"ayri": [["Dove", "Dove"]]}, {}, {}, {})
        self.assertEqual(len(brands), 2)                                   # iki ayrı kayıt
        self.assertEqual(sorted(len(b["sources"]) for b in brands), [1, 1])

    def test_logo_priority(self):
        bd = {"ulker": bd_entry("Ülker")}
        bc = {"ulker": dict(bc_entry("Ülker"), logo="https://www.boykot.co/ulker.png"),
              "tchibo": dict(bc_entry("Tchibo"), logo="https://www.boykot.co/tchibo.png")}
        brands, _ = build(bd, bc, {}, {}, {}, {})
        by = {b["name"]: b for b in brands}
        self.assertEqual(by["Ülker"]["_logo_src"], "https://boykotservisi.com/ulker.webp")   # aynı marka → Dedektif logosu
        self.assertEqual(by["Tchibo"]["_logo_src"], "https://www.boykot.co/tchibo.png")      # yalnız boykot.co'da → onun logosu

    def test_removal_after_two_runs(self):
        e = bd_entry("Twix")
        out, st = carry_over({"twix": e}, {}, "boykotdedektifi")
        self.assertIn("twix", out)
        out, st = carry_over({}, st, "boykotdedektifi")                  # 1. kez yok → tutulur
        self.assertIn("twix", out)
        out, st = carry_over({}, st, "boykotdedektifi")                  # 2. kez yok → kalkar
        self.assertNotIn("twix", out)


class FakeHttp:
    """Örnek sayfalarla tarama (internet yok)."""

    def __init__(self, pages):
        self.pages = pages
        self.requests = 0

    def get(self, url, binary=False, polite=True):
        self.requests += 1
        for k, v in self.pages.items():
            if url.startswith(k):
                return v
        return None


class EndToEnd(unittest.TestCase):
    def test_full_run_and_safety(self):
        import run as runner
        import sources
        # Kategori sayısı kontrollerini küçük örnek için gevşet
        bd_cats_html = sample("dedektif_kategoriler.html")
        many = "".join(f'<a class="category-card" href="/c/k-{i}"><h3>Kat{i}</h3><em>0 marka</em></a>' for i in range(40))
        pages = {
            "https://boykotdedektifi.com/categories": bd_cats_html.replace("</div></body>", many + "</div></body>"),
            "https://boykotdedektifi.com/c/biskuvi-42": sample("dedektif_kategori_s3.html"),
            "https://boykotdedektifi.com/c/": "<html></html>",
            "https://www.boykot.co/c/kahve-3": sample("boykotco_kategori.html"),
            "https://www.boykot.co/c/": "<html></html>",
            "https://www.boykot.co/": sample("boykotco_ana.html").replace(
                "</body>", "".join(f'<a href="/c/x-{i}">X{i}</a>' for i in range(10)) + "</body>"),
        }
        root = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(root, "config"))
            shutil.copy(os.path.join(HERE, "..", "..", "config", "kategori_esleme.json"), os.path.join(root, "config"))
            fake = FakeHttp(pages)
            orig = runner.Http
            runner.Http = lambda delay=1.0: fake
            runner.MIN_FIRST_RUN = {"boykotdedektifi": 1, "boykotco": 1}
            sys.argv = ["run.py", "--root", root, "--no-logos"]
            self.assertEqual(runner.main(), 0)
            cat = json.load(open(os.path.join(root, "catalog.json"), encoding="utf-8"))
            names = sorted(b["name"] for b in cat["brands"])
            self.assertEqual(names, ["Kahve Dünyası", "Lays", "Tchibo", "Torku", "Twix", "Ülker"])
            lays = next(b for b in cat["brands"] if b["name"] == "Lays")
            self.assertEqual({s["source"] for s in lays["sources"]}, {"boykotdedektifi", "boykotco"})
            meta = json.load(open(os.path.join(root, "meta.json")))
            self.assertEqual(meta["brandCount"], 6)
            v1 = meta["version"]
            # Değişiklik yoksa sürüm aynı kalır
            self.assertEqual(runner.main(), 0)
            self.assertEqual(json.load(open(os.path.join(root, "meta.json")))["version"], v1)
            # Site bozulursa (boykot.co boş) yayınlanmaz
            pages["https://www.boykot.co/c/kahve-3"] = "<html></html>"
            self.assertEqual(runner.main(), 2)
            self.assertIn("Yayınlanmadı", open(os.path.join(root, "report.md"), encoding="utf-8").read())
            runner.Http = orig
        finally:
            shutil.rmtree(root)


if __name__ == "__main__":
    unittest.main()
