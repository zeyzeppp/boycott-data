"""Ortak yardımcılar: metin normalleştirme (uygulamalardaki TextNormalizer ile aynı), durum → hüküm, nazik HTTP."""
import re
import time
import unicodedata

import requests

TR_MAP = str.maketrans("IİĞÜŞÖÇığüşöç", "iigusocigusoc")


def metin_temizle(metin: str) -> str:
    """main.py ile aynı (+ idempotent olması için son .lower()). iOS/Android TextNormalizer ile birebir."""
    metin = str(metin).strip().translate(TR_MAP).lower()
    metin = unicodedata.normalize("NFKD", metin).encode("ascii", "ignore").decode("ascii")
    metin = re.sub(r"[^\w\s]", " ", metin).lower()
    return re.sub(r"\s+", " ", metin).strip()


def compact(key: str) -> str:
    """Boşluksuz anahtar: "lay s" ve "lays" aynı sayılır (yalnızca noktalama/boşluk farkı)."""
    return key.replace(" ", "")


KNOWN = {
    "boykot listesinde": "boycott",
    "boykot": "boycott",
    "kesin boykot": "boycott",
    "boykotlu degil": "safe",
    "uygun": "safe",
    "alinabilir": "safe",
    "kismen boykot": "partial",
    "supheli": "caution",
    "ahlaken boykot": "caution",
    "insafa bagli": "caution",
}


def verdict(label: str) -> str:
    """Kaynağın ifadesi → sadeleştirilmiş hüküm (uygulamalardaki StatusNormalizer ile aynı mantık)."""
    if not label or not str(label).strip():
        return "unknown"
    key = metin_temizle(label)
    if key in KNOWN:
        return KNOWN[key]
    if any(w in key for w in ("degil", "alinabilir", "uygun")):
        return "safe"
    if any(w in key for w in ("supheli", "ahlaken", "insaf")):
        return "caution"
    if "kismen" in key:
        return "partial"
    if "boykot" in key:
        return "boycott"
    return "unknown"


def clean_text(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


class Http:
    """Siteleri yormadan tarama: istekler arası bekleme, tanımlı User-Agent, yeniden deneme."""

    def __init__(self, delay: float = 1.0, retries: int = 3, timeout: int = 30):
        self.delay = delay
        self.retries = retries
        self.timeout = timeout
        self.s = requests.Session()
        self.s.headers["User-Agent"] = "BoycottAppDataBot/1.0 (+https://github.com/zeyzeppp/boycott-data)"
        self.s.headers["Accept-Language"] = "tr-TR,tr;q=0.9"
        self._last = 0.0
        self.requests = 0

    def _wait(self):
        dt = time.time() - self._last
        if dt < self.delay:
            time.sleep(self.delay - dt)
        self._last = time.time()

    def get(self, url: str, binary: bool = False, polite: bool = True):
        err = None
        retries = self.retries if polite else 1          # üçüncü taraf logo sunucuları: tek deneme
        for attempt in range(retries):
            if polite:
                self._wait()
            try:
                r = self.s.get(url, timeout=self.timeout if polite else 15)
                self.requests += 1
                if r.status_code == 200:
                    return r.content if binary else r.text
                if r.status_code == 404:
                    return None
                err = f"HTTP {r.status_code}"
            except requests.RequestException as e:
                err = str(e)
            if attempt + 1 < retries:
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"{url}: {err}")
