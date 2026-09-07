#!/usr/bin/env python3
"""
THF (TEFAS) fonu icin gunluk veri cekme scripti.

TEFAS API'si gecmis yatirimci sayisi / fon buyuklugu serisini vermiyor,
sadece "su anki" anlik degerleri veriyor. Bu yuzden bu script her gun
calistirilarak THF'nin o gunku anlik degerlerini data/thf_history.json
dosyasina ekler; zaman icinde boylece kendi tarihsel serimiz olusur.

Coklu fon destegi icin: FON_KODLARI listesine yeni kod eklemek yeterli,
her fon icin ayri data/<KOD>_history.json dosyasi olusturulur.
"""
import json
import os
import sys
from datetime import datetime, timezone, date

# Takip edilecek fonlar. Yeni fon eklemek icin buraya kod eklemek yeterli.
FON_KODLARI = ["THF"]

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def fetch_fund_snapshot(fon_kodu: str) -> dict:
    """tefasmak uzerinden bir fonun anlik bilgisini ceker."""
    from tefasmak import fon_anlik_bilgi

    info = fon_anlik_bilgi(fon_kodu)
    return {
        "date": date.today().isoformat(),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "fund_code": info.get("fonKodu", fon_kodu),
        "fund_name": info.get("fonUnvan"),
        "price": info.get("sonFiyat"),
        "daily_return_pct": info.get("gunlukGetiri"),
        "portfolio_size": info.get("portBuyukluk"),
        "investor_count": info.get("yatirimciSayi"),
    }


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


def main():
    any_success = False
    for fon_kodu in FON_KODLARI:
        print(f"[{fon_kodu}] veri cekiliyor...")
        try:
            snapshot = fetch_fund_snapshot(fon_kodu)
        except Exception as e:
            print(f"[{fon_kodu}] HATA: {type(e).__name__}: {e}", file=sys.stderr)
            continue

        history = load_history(fon_kodu)

        # Ayni gun icin zaten kayit varsa guncelle (gun icinde birden fazla
        # kez calistirilirsa veya piyasa kapanisindan sonra tekrar cekilirse
        # tekrar tekrar eklenmesin diye).
        today_str = snapshot["date"]
        history = [h for h in history if h.get("date") != today_str]
        history.append(snapshot)
        history.sort(key=lambda h: h["date"])

        save_history(fon_kodu, history)
        print(f"[{fon_kodu}] kaydedildi: {snapshot}")
        any_success = True

    if not any_success:
        print("Hicbir fon icin veri cekilemedi.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
