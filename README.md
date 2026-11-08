# boycott-data

BOYCOTT uygulamasının (iOS / Android) marka verisi.

> **Şu anki mod: eski liste.** Katalog `kaynak/guncellenmis_liste.json`'dan (Boykot Dedektifi + bykt.org, önceden eşleştirilmiş)
> `python scraper/eski_liste.py` ile üretiliyor; gece taraması kapalı. Canlı taramaya geçmek için
> `.github/workflows/guncelle.yml`'deki `schedule` satırlarını açın.

| Dosya | İçerik |
|---|---|
| `meta.json` | Sürüm, marka sayısı, kaynak başına sayı, `catalog.json` özeti. Uygulama açılışta yalnızca bunu indirir. |
| `catalog.json` | Tüm markalar: ad, kategoriler, logo adresi, her kaynağın kendi hükmü ve marka sayfası ("Kanıtı incele"). |
| `logos/<id>.webp` | En fazla 256 px logolar (kaynaktan indirilip küçültülmüş). |
| `config/` | Elle tutulan ayarlar: kategori eşlemesi, onaylanan eşleşmeler, ürün → marka listesi. |
| `state/` | Taramanın hafızası: marka kimlikleri, kaldırma sayaçları, logo kaynakları, onay bekleyenler. |

## Kaynaklar
- **Boykot Dedektifi** (boykotdedektifi.com) — ana kaynak: durum, kategoriler, logo.
- **boykot.co** — boykot listesi.

Uygulama karar vermez; her kaynağın kendi ifadesi gösterilir ve kaynağın sayfasına bağlantı verilir.
Siteler nazikçe taranır (istekler arası 1 sn, tanımlı User-Agent).

## Nasıl çalışır
`.github/workflows/guncelle.yml` her gece `scraper/run.py`'yi çalıştırır:
1. İki site kategori kategori taranır.
2. Markalar birleştirilir (aynı ad / yalnız noktalama farkı → tek marka; benzer adlar → **onay bekleyen** listesi).
3. **Güvenlik kontrolü:** bir kaynaktan hiç marka gelmezse ya da sayı %10'dan fazla düşerse yayınlanmaz.
4. Değişiklik varsa `catalog.json`, `meta.json`, `logos/` güncellenip commit edilir.
5. Sorun ya da onay bekleyen eşleşme varsa **"tarama" etiketli Issue** açılır/güncellenir (e-posta bildirimi).

## Eşleşme onayı
Issue'daki tabloda iki sitedeki benzer adlı markalar logoları ve kategorileriyle gösterilir. Karar `config/eslesmeler.json`'a yazılır:
```json
{ "birlestir": { "Nescafe Gold": "Nescafé" }, "ayri": [["Kent", "Kenton"]] }
```
Dosya değişince tarama hemen yeniden çalışır.

## Yerelde
```
pip install -r scraper/requirements.txt
python -m unittest discover -s scraper/tests   # internetsiz testler
python scraper/run.py --no-logos               # gerçek tarama (logosuz, hızlı)
```
