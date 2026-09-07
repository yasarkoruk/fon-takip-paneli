"""TEFAS fon verisi - TEK tarih araligi sorgusu.

MIMARI NOTU (onemli):
Tek bir TEFAS sorgusu 30-50 saniye surebiliyor ve Vercel fonksiyonlari
en fazla 60 saniye calisabiliyor. Bu yuzden bu endpoint KASITLI olarak
sadece TEK bir sorgu yapar; tarih araligini parcalara bolme isi
istemcide (index.html) yapilir ve her parca ayri bir HTTP istegi olarak
gelir. Boylece her fonksiyon cagrisi limit icinde kalir.
"""
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json

FUND_TYPES = ["SEC", "PEN", "ETF", "RE", "VC"]


def fetch_range(fund_code, start_str, end_str, fund_type=None):
    from tefasfon import get_funds
    types_to_try = [fund_type] if fund_type else FUND_TYPES
    last_err = None
    for t in types_to_try:
        try:
            df = get_funds(
                fund_type=t,
                start_date=start_str,
                end_date=end_str,
                fund_codes=[fund_code],
            )
        except Exception as e:
            last_err = e
            continue
        if df is not None and len(df) > 0:
            return df, t
    if last_err:
        raise last_err
    return None, None


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        code = (qs.get("code") or [""])[0].strip().upper()
        start = (qs.get("start") or [""])[0]
        end = (qs.get("end") or [""])[0]
        fund_type = (qs.get("type") or [None])[0]

        if not code or not start or not end:
            self._json(400, {"error": "code, start, end (DD.MM.YYYY) parametreleri gerekli"})
            return

        try:
            df, used_type = fetch_range(code, start, end, fund_type)
        except Exception as e:
            self._json(502, {"error": f"{type(e).__name__}: {e}"})
            return

        if df is None or len(df) == 0:
            # Hata degil: bu aralikta islem gunu olmayabilir (hafta sonu/tatil).
            self._json(200, {"fund_type": used_type, "data": []})
            return

        out = []
        for _, row in df.iterrows():
            tarih = row["tarih"]
            d = tarih.date().isoformat() if hasattr(tarih, "date") else str(tarih)[:10]
            out.append({
                "date": d,
                "fund_code": row.get("fonKodu"),
                "fund_name": row.get("fonUnvan"),
                "price": row.get("fiyat"),
                "portfolio_size": row.get("portfoyBuyukluk"),
                "investor_count": row.get("kisiSayisi"),
                "shares_outstanding": row.get("tedPaySayisi"),
            })
        out.sort(key=lambda r: r["date"])
        self._json(200, {"fund_type": used_type, "data": out})

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors()
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)
