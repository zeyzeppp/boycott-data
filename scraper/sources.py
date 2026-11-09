"""Kaynak siteler: sayfa ayrıştırma (saf fonksiyonlar, testli) + tarama.

Her kaynak `{anahtar: kayıt}` döndürür. Kayıt:
  name, label (kaynağın kendi ifadesi), url (marka sayfası = "Kanıtı incele"), logo (kaynak görsel adresi),
  categories (kaynağın kategori adları), desc (kısa açıklama; uygulamada gösterilmez, yalnızca eşleşme onayı için)
"""
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from common import clean_text, metin_temizle

# ---------------------------------------------------------------- Boykot Dedektifi

BD_BASE = "https://boykotdedektifi.com"


def bd_parse_categories(html: str):
    """/categories → [(ad, mutlak adres, marka sayısı)]"""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for a in soup.select("a.category-card[href]"):
        h3 = a.find("h3")
        if not h3:
            continue
        em = a.find("em")
        m = re.search(r"\d+", em.get_text() if em else "")
        out.append((clean_text(h3.get_text()), urljoin(BD_BASE, a["href"]), int(m.group()) if m else None))
    return out


def bd_parse_category_page(html: str):
    """Kategori sayfası → ([kart], sonraki sayfa var mı)"""
    soup = BeautifulSoup(html, "html.parser")
    cards = []
    for a in soup.select("a.brand-card[href]"):
        h3 = a.find("h3")
        if not h3:
            continue
        badge = a.select_one(".status-badge")
        img = a.select_one(".brand-logo img")
        body = a.select_one(".brand-card-body")
        desc = ""
        if body:
            for child in body.find_all("div", recursive=False):
                cls = child.get("class") or []
                if "brand-title-row" in cls or "brand-meta" in cls:
                    continue
                desc = clean_text(child.get_text(" "))
                break
        meta = [clean_text(s.get_text()) for s in a.select(".brand-meta span")]
        cards.append({
            "name": clean_text(h3.get_text()),
            "label": clean_text(badge.get_text()) if badge else "",
            "url": urljoin(BD_BASE, a["href"]),
            "logo": urljoin(BD_BASE, img["src"]) if img and img.get("src") else None,
            "meta": meta,
            "desc": desc[:300],
        })
    nxt = None
    for link in soup.select("a.pagination-link"):
        if clean_text(link.get_text()).lower().startswith("sonraki"):
            nxt = link
    has_next = nxt is not None and "is-disabled" not in (nxt.get("class") or [])
    return cards, has_next


def bd_crawl(http, log=print, max_pages=60, key_by_url=False):
    """Tüm kategorileri sayfa sayfa gezer. Markanın kategorileri: göründüğü tüm kategori sayfaları
    (kart üstündeki sırayla; ilki ana kategori)."""
    cats = bd_parse_categories(http.get(f"{BD_BASE}/categories") or "")
    if len(cats) < 30:
        raise RuntimeError(f"Boykot Dedektifi: kategori listesi tanınmadı ({len(cats)} kategori)")
    names = {c[0] for c in cats}
    brands = {}
    for cname, curl, expected in cats:
        seen = 0
        for page in range(1, max_pages + 1):
            html = http.get(f"{curl}?pageNumber={page}")
            if not html:
                break
            cards, has_next = bd_parse_category_page(html)
            for c in cards:
                key = c["url"] if key_by_url else metin_temizle(c["name"])   # aynı adlı iki marka olabilir
                if not key:
                    continue
                b = brands.get(key)
                if b is None:
                    meta_cats = [m for m in c["meta"] if m in names]
                    b = brands[key] = {
                        "name": c["name"], "label": c["label"], "url": c["url"], "logo": c["logo"],
                        "categories": meta_cats, "desc": c["desc"],
                    }
                if cname not in b["categories"]:
                    b["categories"].append(cname)
            seen += len(cards)
            if not cards or not has_next:
                break
        log(f"  Dedektif / {cname}: {seen} marka (site: {expected})")
    return brands, [c[0] for c in cats]


# ---------------------------------------------------------------- boykot.co

BC_BASE = "https://www.boykot.co"
BC_LABEL = "Boykot Listesinde"   # boykot.co yalnızca boykot listesi tutar


def bc_parse_categories(html: str):
    """Ana sayfa → [(ad, mutlak adres)]"""
    soup = BeautifulSoup(html, "html.parser")
    out, seen = [], set()
    for a in soup.select('a[href*="/c/"]'):
        url = urljoin(BC_BASE, a["href"])
        name = clean_text(a.get_text())
        if not name or url in seen:
            continue
        seen.add(url)
        out.append((name, url))
    return out


def bc_parse_category_page(html: str):
    """Kategori sayfası (tablo) → [kart]"""
    soup = BeautifulSoup(html, "html.parser")
    cards, seen = [], set()
    for row in soup.select("tr"):
        a = row.select_one('h6 a[href*="/d/"]') or row.select_one('a[href*="/d/"]')
        if not a:
            continue
        url = urljoin(BC_BASE, a["href"])
        name = clean_text(a.get_text())
        if not name or url in seen or name.lower() == "neden?":
            continue
        seen.add(url)
        img = row.find("img")
        p = row.find("p")
        cards.append({
            "name": name, "url": url,
            "logo": urljoin(BC_BASE, img["src"]) if img and img.get("src") else None,
            "desc": clean_text(p.get_text())[:300] if p else "",
        })
    return cards


def bc_crawl(http, log=print):
    cats = bc_parse_categories(http.get(f"{BC_BASE}/") or "")
    if len(cats) < 10:
        raise RuntimeError(f"boykot.co: kategori listesi tanınmadı ({len(cats)} kategori)")
    brands = {}
    for cname, curl in cats:
        cards = bc_parse_category_page(http.get(curl) or "")
        for c in cards:
            key = metin_temizle(c["name"])
            if not key:
                continue
            b = brands.get(key)
            if b is None:
                b = brands[key] = {"name": c["name"], "label": BC_LABEL, "url": c["url"], "logo": c["logo"],
                                   "categories": [], "desc": c["desc"]}
            if cname not in b["categories"]:
                b["categories"].append(cname)
        log(f"  boykot.co / {cname}: {len(cards)} marka")
    return brands, [c[0] for c in cats]
