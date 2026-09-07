#!/usr/bin/env python3
"""
THF (TEFAS) fonu icin gunluk / geriye donuk veri cekme scripti.

tefasfon paketinin get_funds() fonksiyonu TEFAS'in tarih araligi bazli
"genel bilgi" uc noktasini kullanir ve GERCEK tarihsel fiyat, pay sayisi,
yatirimci sayisi ve fon buyuklugu serisini dondurur (tahmini degil).

Coklu fon destegi icin: FON_KODLARI listesine yeni kod eklemek yeterli,
her fon icin ayri data/<KOD>_history.json dosyasi olusturulur.

BACKFILL_DAYS ortam degiskeni > 0 ise, bugunden geriye o kadar gun
icin tarihsel veri cekilir (ilk kurulumda veya eksik gunleri doldurmak
icin kullanilir). Varsayilan 0: sadece bugunku veri cekilir.
"""
import json
import os
import sys
from datetime import datetime, timezone, date, timedelta

# Takip edilecek fonlar ve TEFAS fon tipi.
# Fon tipi: SEC (Hisse Senedi/Yatirim Fonu), PEN (Emeklilik), ETF, RE, VC
FON_KODLARI = ["THF"]
FON_TIPI = "SEC"

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def fetch_range(start_date: date, end_date: date):
    """tefasfon uzerinden tarih araligi icin genel fon bilgisini ceker."""
    from tefasfon import get_funds

    df = get_funds(
        fund_type=FON_TIPI,
        start_date=start_date.strftime("%d.%m.%Y"),
        end_date=end_date.strftime("%d.%m.%Y"),
        fund_codes=FON_KODLARI,
    )
    return df


def df_to_snapshots(df) -> dict:
    """DataFrame'i {fon_kodu: [snapshot, ...]} sozlugune cevirir."""
    result: dict[str, list] = {}
    for _, row in df.iterrows():
        fon_kodu = row["fonKodu"]
        tarih = row["tarih"]
        d = tarih.date().isoformat() if hasattr(tarih, "date") else str(tarih)[:10]
        snap = {
            "date": d,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "fund_code": fon_kodu,
            "fund_name": row.get("fonUnvan"),
            "price": row.get("fiyat"),
            "portfolio_size": row.get("portfoyBuyukluk"),
            "investor_count": row.get("kisiSayisi"),
            "shares_outstanding": row.get("tedPaySayisi"),
        }
        result.setdefault(fon_kodu, []).append(snap)
    return result


def load_history(fon_kodu: str) -> list:
    path = os.path.join(DATA_DIR, f"{fon_kodu}_history.json")
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_history(fon_kodu: str, history: list) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    path = os.path.join(DATA_DIR, f"{fon_kodu}_history.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def merge_snapshots(fon_kodu: str, new_snaps: list) -> int:
    """Yeni snapshotlari (ayni tarih varsa uzerine yazarak) mevcut
    tarihceyle birlestirir. Eklenen/guncellenen kayit sayisini dondurur."""
    history = load_history(fon_kodu)
    by_date = {h["date"]: h for h in history}
    for snap in new_snaps:
        by_date[snap["date"]] = snap
    merged = sorted(by_date.values(), key=lambda h: h["date"])
    save_history(fon_kodu, merged)
    return len(new_snaps)


def main():
    backfill_days = int(os.environ.get("BACKFILL_DAYS", "0") or "0")
    end = date.today()
    start = end - timedelta(days=backfill_days) if backfill_days > 0 else end

    print(f"Veri cekiliyor: {start.isoformat()} -> {end.isoformat()} (fonlar: {FON_KODLARI})")
    try:
        df = fetch_range(start, end)
    except Exception as e:
        print(f"HATA: veri cekilemedi: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)

    if df is None or len(df) == 0:
        print("Sonuc bos dondu. Fon kodu / tarih araligi / tatil gunu olabilir.", file=sys.stderr)
        sys.exit(1)

    by_fund = df_to_snapshots(df)
    any_success = False
    for fon_kodu, snaps in by_fund.items():
        n = merge_snapshots(fon_kodu, snaps)
        print(f"[{fon_kodu}] {n} gunluk kayit islendi (son: {snaps[-1]})")
        any_success = True

    if not any_success:
        print("Hicbir fon icin veri islenemedi.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
