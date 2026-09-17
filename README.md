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

Actions hafta içi Türkiye saatiyle 10:00, 18:00 ve gecikmeler için 21:00'de çalışır. Normal çalışmada son 30 günü **en yeni tarihten başlayarak** tarar; eski bir sorgu hatası güncel günü engellemez. Aynı tarih için tek kayıt bırakır. Hatalı veya eksik çekim arşiv korunduktan ve panel verisi üretildikten sonra başarısız çıkış verir. Önce son 3 gün için tekrar deneme, o da başarısızsa farklı GitHub Windows ağı üzerinden son 3 gün telafisi uygulanır. TEFAS tüm ağlardan erişilemiyorsa son başarılı kayıtlar ve açık hata korunur; erişim garantisi yoktur. İlk geniş tarihçe yalnızca onaylı `--backfill-days 90` ile tamamlanır; daha uzun süre kullanıcı onayı gerektirir.

Yerelde:

```bash
pip install -r requirements.txt
python -m scripts.fetch_tefas
python -m scripts.fetch_tefas --skip-fetch
python -m unittest discover -s tests -v
```

Dashboard varsayılan olarak 1G'yi seçer; veri yetersizse mevcut en kısa dönemi gösterir. Üstteki arama, günlük collector tarafından oluşturulan tüm TEFAS fon kataloğunu kod veya adla tarar. Arşivlenmiş fonlar panelde açılır; henüz collector kapsamına alınmamış fonlar TEFAS detay sayfasında açılır. “Excel Raporu” seçili fonun tarihçesini `.xlsx` olarak indirir. **Arşivi Yenile** yalnızca yayınlanan JSON'u yeniden okur; TEFAS çekimi yaptığını iddia etmez. **TEFAS Taraması** GitHub'ın yetkili workflow ekranını açar; kullanıcı burada `Run workflow` ile güvenli çekim başlatabilir. Tarayıcıya GitHub token veya canlı-query servisi eklenmez. Son veri tarihi, son deneme ve son başarılı tarama ayrıdır; eski arşiv için yeşil “veriler güncel” mesajı verilmez. Hafta sonu dikkate alınır, tatil ve TEFAS yayın gecikmeleri kesin veri eksikliği sayılmadan açıklanır.

## KAP haberleri ve likidite kontrolü

`KAP resmi sorgusu → scripts.fetch_kap → data/kap/archive.json → statik panel`

- `config/kap.json` takip edilen fonların KAP member OID'lerini ve insan incelemesinden geçen olayları saklar. Başlangıç kapsamı THF; Pusula kurucu bildirimi ayrı piyasa izleme notudur, tüm Pusula fonlarına atanmaz.
- KAP'ın kendi güncel istemcisinin kullandığı `tr/api/disclosure/filter/FILTERYFBF/{memberOid}/ALL/365` liste uç noktası her kontrolde okunur; ID bazında birleştirilir. Bu 365 günlük **bildirim** taraması, 90 günlük TEFAS fiyat tarihçesini büyütmez. Liste tek JSON dizisidir; şema veya kapsam değişirse hata kaydedilir.
- Fonun genel açıklama/iade/likidite adaylarının resmi metni `tr/api/notification/attachment-detail/{index}` üzerinden alınır. Ek PDF'ler otomatik yorumlanmaz. İlk ekranda son 5 doğrudan fon bildirimi, isteğe bağlı ilişkili kurum bildirimleri ve eski kayıtları açma bulunur.
- Kelimeler yalnızca **inceleme adayı** üretir; otomatik temerrüt, iflas veya yatırım kararı vermez. İncelenmiş olaylar `reviewed_events` içinde açık kalır. Haber yokluğu, fiyat yükselişi, erişim hatası veya yapılandırmadan kaydın çıkarılması olayı kapatmaz. Kapatma ancak açık bir inceleme ve aynı kapsamlı resmi `resolution_disclosure_id` ile yapılır.
- `.github/workflows/kap.yml` her gün Türkiye saati 08:00–23:00 saatlik kontrol eder. Açık olay, inceleme adayı veya önceki kontrol hatası varsa :30 ek kontrolleri açar (23:30 dahil). Gece 02:00 ve 05:00 kontrolü vardır. GitHub planlı işleri geciktirebilir; gerçek kontrol zamanı gösterilir, kesin gerçek-zaman garantisi yoktur.
- 3 deneme, artan bekleme, 25 saniye istek sınırı ve çalışma başına 20 aday detay sınırı vardır. Eksik detaylar sonraki kontrolde tamamlanır. Hata halinde başarılı arşiv ve olaylar korunur; `last_attempt_at`, `last_success_at`, hata ve art arda başarısızlık sayısı saklanır. KAP kontrol durumunun yeşil olması **fonun güvenli olduğu anlamına gelmez**.
- Tarayıcı dakikada bir yalnızca kendi statik KAP arşivini kontrol eder; KAP'a canlı istek atmaz. KAP kontrol hataları ve gecikme uyarısı panelin en altındadır, finansal risk olayı haber bölümündedir.
- TEFAS ve KAP veri yazıcıları aynı concurrency grubunu kullanır; birbirlerini yarıda kesmez. Yayın öncesi kaynak güncellemeleri korunur.

Manuel kontrol: `python -m scripts.fetch_kap`. Kontrol kapsamı ve resmi kaynak bağlantıları panelde görünür; arşiv tarihleri Europe/Istanbul'dur.

TEFAS özeti, koleksiyon sırasında ayrıca alınır: fon bilgisi, portföy varlık dağılımı ile 1A/3A/6A/1Y getirileri. Kaynak açık yanıtta kategori derecesi veya pazar payı vermiyorsa panel bu alanları `—` gösterir; ekran görüntüsündeki eski değerleri sabitlemez. Özet isteği geçici olarak başarısız olursa son başarılı özet korunur ve hata `status.json` üzerinden panelde görünür.

## Yayın

Vercel kullanılmaz. Panel yalnızca GitHub Pages üzerinden yayınlanır.

## Cihaza ekleme

Panelde özel bir yükleme kartı yoktur; tarayıcının yerleşik PWA işlevi kullanılır. Chrome veya Edge'de adres çubuğundaki **Yükle** simgesini seçin. iPhone/iPad'de bağlantıyı Safari'de açın, **Paylaş → Ana Ekrana Ekle → Ekle** yolunu kullanın. WhatsApp, Instagram veya Chrome iOS içindeki gömülü tarayıcılar Safari'nin Ana Ekrana Ekle seçeneğini sunmaz.
