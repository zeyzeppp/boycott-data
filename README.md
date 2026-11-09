# boycott-data

BOYCOTT uygulamasının (iOS / Android) marka verisi.

| Dosya | İçerik |
|---|---|
| `kaynak/birlesik_liste.json` | **Ana liste.** Markalar, kategoriler, görseller, Boykot Dedektifi ↔ bykt.org eşleşmeleri ve iki sitenin durumu. Markalar elle onaylanmadan değişmez; gece yalnızca durumlar yazılır. |
| `config/eslesme_kararlari_bd_bykt.json` | Eşleştirme kararlarınız (`birlestir` / `ayri`). Bir kez verilen karar tekrar sorulmaz. |
| `config/alt_markalar.json` | Ürün / alt marka adı → ana marka (fotoğrafta yalnız ürün adı okunduğunda). |
| `meta.json` | Sürüm, marka sayısı, `catalog.json` özeti (SHA-256). Uygulama açılışta yalnızca bunu indirir. |
| `catalog.json` | Uygulamanın okuduğu katalog (ana listeden üretilir). |
| `logos/<id>.webp` | En fazla 256 px logolar. Uygulamalar bunların 128 px kopyalarını içinde taşır. |
| `sorular/` | Haftalık eşleştirmede size sorulan markalar (`eslestirme_sorular.html`). |
| `state/` | Son tarama, site başına marka sayıları, logo kaynakları. |
| `kaynak/guncellenmis_liste.json` | İlk eski liste (arşiv). |

## Her gece (03:17 TSİ) — `scraper/gece.py`
1. Boykot Dedektifi'nin tüm kategori sayfaları ve bykt.org'un marka listesi okunur (istekler arası 1 sn).
2. Ana listedeki her marka kanıt adresiyle bulunur; **yalnızca boykot durumu** güncellenir. Sitede artık
   bulunmayan markanın eski durumu korunur.
3. **Güvenlik:** bir siteden gelen marka sayısı %10'dan fazla düşerse ya da bir gecede markaların %5'inden
   fazlasının durumu değişirse **yayınlanmaz**, "tarama" etiketli Issue açılır. Değişiklikler doğruysa
   Actions → Gece güncellemesi → Run workflow → "zorla" ile yayınlayabilirsiniz.
4. Değişiklik varsa `catalog.json` + `meta.json` yeni sürümle yayınlanır; telefonlar açılışta indirir.

## Her pazartesi — yeni markalar
- Sitelere yeni eklenen markalar listeye eklenir. Adı aynı olanlar otomatik eşleşir.
- Emin olunamayanlar `sorular/eslestirme_sorular.html`'de sorulur ve Issue açılır:
  1. Dosyayı indirip tarayıcıda açın, seçimlerinizi yapın, **eslesme_kararlari.json**'u indirin.
  2. Depoda `sorular/` klasörüne **Add file → Upload files** ile yükleyin.
  3. Kararlarınız birkaç dakika içinde işlenir (`config/`'e yazılır, sorular `sorular/islenmis/`'e taşınır).
- Sorular cevaplanana kadar yeni marka eklenmez (sorular birbirine karışmasın).

Uygulama karar vermez; her kaynağın kendi ifadesi gösterilir ve kaynağın sayfasına bağlantı verilir.

## Yerelde
```
pip install -r scraper/requirements.txt
python -m unittest discover -s scraper/tests        # internetsiz testler
python scraper/gece.py --no-logos                   # gerçek güncelleme (logosuz)
python scraper/gece.py --veriler DIR --no-logos     # internetsiz deneme (DIR: boykot_dedektifi.json + bykt_org.json)
```
