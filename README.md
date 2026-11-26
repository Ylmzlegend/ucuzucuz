# ucuzucuz

E-bisiklet, robot süpürge ve televizyon tekliflerini Trendyol ve Hepsiburada genelinde karşılaştıran statik site.
Her teklifte toplam tutar, kargo, garanti türü ve son kontrol tarihi yazar. Sunucu ve veritabanı gerekmez.

## Klasörler
| Yol | Ne işe yarar |
|---|---|
| `data/kaynak/YYYY-AA-GG.json` | O gün mağaza sayfalarından toplanan ham fiyatlar (kaynak kaydı) |
| `data/urunler/<kategori>.csv` | Ürünler ve özellikleri (Excel'de açılır) |
| `data/offers.csv`, `data/sellers.csv` | Teklifler ve satıcılar |
| `data/price_history.csv` | Fiyat geçmişi; elle dokunma |
| `config.json` | Kategoriler, özellikler, filtreler, metinler |
| `build.py` | Siteyi `dist/` klasörüne üretir |
| `tools/` | Veri aktarma ve fiyat güncelleme araçları |
| `.github/workflows/yayinla.yml` | Her güncellemede siteyi otomatik yayınlar |

## Bilgisayarında görmek
Python 3 kur (python.org), sonra proje klasöründe:

    pip install -r requirements.txt
    python build.py --preview

`dist/index.html` dosyasını çift tıkla.

## İnternette yayınlamak (bir kez, yaklaşık 15 dakika)
1. github.com'da hesap aç. Yeni bir depo (repository) oluştur, adı `ucuzucuz`, herkese açık (Public).
2. Depo sayfasında "uploading an existing file"a tıkla, bu klasörün içindekileri sürükle. `dist` klasörünü yükleme. Gizli `.github` klasörünün de yüklendiğini kontrol et. Yüklenmediyse GitHub Desktop uygulamasıyla yükle.
3. Depoda Settings → Pages → Source: "GitHub Actions" seç.
4. Actions sekmesinde "Siteyi yayınla" çalışır, birkaç dakika sonra site `kullaniciadin.github.io/ucuzucuz` adresinde açılır.
5. Alan adı: Settings → Pages → Custom domain alanına `ucuzucuz.com` yaz. Alan adını aldığın firmanın DNS panelinde GitHub'ın gösterdiği kayıtları ekle (A kayıtları ve `www` için CNAME). "Enforce HTTPS"i işaretle.

Bundan sonra depoya her yeni dosya yüklediğinde site kendiliğinden yeniden yayınlanır.

## Fiyatları güncel tutmak
Büyük mağazalar sunuculardan gelen otomatik istekleri engelliyor. Bu yüzden fiyatlar bir tarayıcı üzerinden okunuyor:

- **Claude ile (önerilen):** Claude masaüstü uygulaması açıkken Claude'a "ucuzucuz fiyatlarını güncelle" de. Claude ürün sayfalarını tarayıcıda açıp yeni bir `data/kaynak/YYYY-AA-GG.json` hazırlar, sonra:

      python tools/import_snapshot.py data/kaynak/YYYY-AA-GG.json
      python build.py --preview

  Değişen `data/` dosyalarını GitHub'a yükle; site kendiliğinden güncellenir.
- **Elle, tek teklif:**

      python tools/set_price.py P07-TY-aldimgitti 17199
      python tools/set_price.py P07-TY-aldimgitti --ayni      # fiyat aynı, bugün kontrol ettim
      python tools/set_price.py P07-TY-aldimgitti --stok-yok

  Teklif kimlikleri `data/offers.csv` dosyasının ilk sütununda.

14 günden eski veya stokta olmayan teklif "en ucuz" hesabına girmez. Güncelleme yapılmazsa site eski fiyatı en ucuz diye göstermez.

## Yeni ürün veya kategori eklemek
- **Ürün:** Ürünü bir sonraki anlık görüntüye ekle (Claude'a model adını söyle) ya da `data/urunler/<kategori>.csv` ve `data/offers.csv` dosyalarına satır ekle.
- **Kategori:** `config.json` → `categories` içine bir blok ekle (`ozellikler`, `filtreler`, isteğe bağlı `deger`), sonra `data/urunler/<anahtar>.csv` dosyasını aynı sütun adlarıyla oluştur. Ürünü olmayan kategori sitede görünmez. Telefon, dizüstü, konsol ve e-scooter tanımları hazır, yalnızca ürün bekliyor.

## Veri kuralları
- Trendyol'da "Kargo Bedava" ilanlarda kargo 0 yazılır. Kargo net değilse alan boş kalır, sitede "Belirtilmemiş" yazar ve toplam tutara eklenmez.
- Hepsiburada'daki "Sepete özel" fiyat herkese uygulandığı için o fiyat kullanılır. Premium üyelere özel fiyat kullanılmaz.
- Garanti türü yalnızca ilanda yazıyorsa "Resmi garanti" olarak işaretlenir. Yazmıyorsa "Garanti türü belirtilmemiş" yazar.
- Fiyatı ana tekliflerin 1,5 katını aşan ilanlar (set ürünler, hatalı ilanlar) alınmaz.
- Ehliyet ve plaka notları bilgilendirme amaçlıdır. Yayına almadan önce resmi mevzuattan doğrula.
- Hata gördüğünde `build.py` hangi dosyanın kaçıncı satırında olduğunu yazar ve siteyi üretmez.
