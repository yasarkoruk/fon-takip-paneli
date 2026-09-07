# THF Fon Takip Paneli

TEFAS'taki THF fonu için günlük otomatik veri çekimi yapan ve para akışı /
yatırımcı değişimini tek ekranda gösteren, mobil ve masaüstü (macOS)
görünümlü bir panel.

## Nasıl çalışıyor?

1. **GitHub Actions** (`.github/workflows/daily.yml`) her hafta içi gün
   16:30 UTC'de (19:30 TR saati) otomatik çalışır, `scripts/fetch_tefas.py`
   scriptini çalıştırarak THF'nin o günkü anlık verisini (fiyat, fon
   büyüklüğü, yatırımcı sayısı) çeker ve `data/THF_history.json` dosyasına
   ekler.
2. Bu şekilde TEFAS'ın vermediği **tarihsel** yatırımcı sayısı / fon
   büyüklüğü serisi, zamanla kendi arşivimizde birikir.
3. **`index.html`** bu JSON dosyasını okuyup görselleştirir: bugünkü tahmini
   net para akışı, yatırımcı değişimi, 7/30 günlük özetler ve grafikler.
4. Panel **GitHub Pages** ile yayınlanır — hem telefondan hem Mac'ten bir
   linkle açılabilir.

## Önemli not: "Tahmini" net para akışı

TEFAS işlem bazlı (kim, ne zaman, ne kadar yatırdı/çekti) veri sağlamıyor;
sadece günlük anlık fon büyüklüğü, fiyat ve yatırımcı sayısını veriyor. Bu
yüzden panel gerçek giriş/çıkışı değil, **tahmini net akışı** gösterir:

```
Tahmini Net Akış = Fon Büyüklüğü Değişimi − (Önceki Büyüklük × Günlük Getiri)
```

Yani AUM'daki değişimin ne kadarının fiyat/getiriden, ne kadarının yeni
para girişi/çıkışından kaynaklandığı ayrıştırılır. Yatırımcı sayısındaki
net değişim de aynı şekilde sadece **net** olarak izlenebiliyor (kaç kişi
yeni girdi, kaç kişi çıktı ayrı ayrı bilinmiyor — sadece toplam farkı).

## Kurulum

```bash
pip install -r requirements.txt
python scripts/fetch_tefas.py   # elle bir kez çalıştırıp data/ dosyasını oluşturur
```

Sonra GitHub'da: **Settings → Pages → Source: Deploy from a branch → main / (root)**
seçilirse panel `https://<kullanıcı-adı>.github.io/thf-fon-takip-paneli/`
adresinde yayınlanır.

## Yeni fon eklemek

1. `scripts/fetch_tefas.py` içindeki `FON_KODLARI` listesine fon kodunu ekle.
2. `index.html` içindeki `FON_KODLARI` listesine aynı kodu ekle (panelde
   üstte fon geçiş düğmesi otomatik belirir).

## Bilinen risk

TEFAS'ın yeni (2026, Next.js tabanlı) sitesinde Akamai bot koruması var.
GitHub Actions'ın bulut sunucuları bazen bu korumaya takılabilir — ilk
otomatik çalıştırmanın **Actions** sekmesinden kontrol edilmesi önerilir.
Sorun olursa iş elle tetiklenebilir (`workflow_dispatch`) veya script farklı
bir TEFAS erişim yöntemine güncellenebilir.
