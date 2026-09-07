# Fon Takip Paneli

Statik, mobil uyumlu TEFAS fon paneli. Tarayıcı TEFAS veya Vercel'e istek atmaz; yalnızca GitHub Actions tarafından üretilmiş kalıcı JSON verisini okur.

## Mimari

`TEFAS → Python collector → doğrulanan history.json → analytics → dashboard.json → GitHub Pages`

- `config/funds.json` fon kaynağıdır. Yeni fon eklemek için yalnızca buraya kod, ad ve fon tipi kaydı eklenir; collector, arama alanı ve dashboard aynı kayıtları kullanır.
- `data/funds/<KOD>/history.json` kalıcı ham tarihçedir; atomik yazılır ve duplicate tarih kabul edilmez.
- `metrics.json`, `current.json`, `status.json`, `tefas_summary.json` ve `dashboard.json` türetilmiş statik çıktılardır.
- Zaman dilimi `Europe/Istanbul`'dur. Kayıt tarihi TEFAS satırındaki işlem tarihidir; sunucu günü değildir.

## Akış ve kalite

Ana metrik **tahmini net para akışı**dır: AUM değişiminden fiyat etkisi ayrıştırılır. Pay adedi değişimi × ortalama fiyat ikinci bağımsız kontroldür. Bunlar gerçekleşmiş işlem bilgisi değildir. Büyük sıçramalar silinmez; `quality_warnings` olarak saklanır. TEFAS erişimi bozulursa son başarılı tarihçe korunur, `status.json` hata durumunu kaydeder ve workflow başarısız görünür.

## Otomasyon ve recovery

Actions hafta içi 19:15, 20:00 ve 21:00 Türkiye saatinde çalışır. Normal çalışmada son 30 günü tarayarak eksik işlem günlerini doldurur; aynı tarih için yalnızca tek kayıt bırakır. Böylece kaçırılan çalışma sonraki başarılı çalışmada iyileşir. İlk geniş tarihçe için işi tek dev isteğe çevirmeden `--backfill-days 90`, sonra `180`, sonra `365` ile aşamalı manuel çalıştırma yapılır.

Yerelde:

```bash
pip install -r requirements.txt
python -m scripts.fetch_tefas
python -m scripts.fetch_tefas --skip-fetch
python -m unittest discover -s tests -v
```

Dashboard varsayılan olarak 14G'yi seçer; veri yetersizse mevcut en kısa dönemi gösterir. Üstteki arama, günlük collector tarafından oluşturulan tüm TEFAS fon kataloğunu kod veya adla tarar. Arşivlenmiş fonlar panelde açılır; henüz collector kapsamına alınmamış fonlar TEFAS detay sayfasında açılır. “Excel Raporu” seçili fonun tarihçesini `.xlsx` olarak indirir. “Veriyi Yenile” yalnızca `dashboard.json` ve katalog için cache-bust edilmiş statik yeniden yüklemedir.

TEFAS özeti, koleksiyon sırasında ayrıca alınır: fon bilgisi, portföy varlık dağılımı ile 1A/3A/6A/1Y getirileri. Kaynak açık yanıtta kategori derecesi veya pazar payı vermiyorsa panel bu alanları `—` gösterir; ekran görüntüsündeki eski değerleri sabitlemez. Özet isteği geçici olarak başarısız olursa son başarılı özet korunur ve hata `status.json` üzerinden panelde görünür.

## Yayın

Vercel kullanılmaz. Panel yalnızca GitHub Pages üzerinden yayınlanır.

## Cihaza ekleme

Panelde özel bir yükleme kartı yoktur; tarayıcının yerleşik PWA işlevi kullanılır. Chrome veya Edge'de adres çubuğundaki **Yükle** simgesini seçin. iPhone/iPad'de bağlantıyı Safari'de açın, **Paylaş → Ana Ekrana Ekle → Ekle** yolunu kullanın. WhatsApp, Instagram veya Chrome iOS içindeki gömülü tarayıcılar Safari'nin Ana Ekrana Ekle seçeneğini sunmaz.
