"""Fon arama - TEK fon tipi tarar.

MIMARI NOTU: history.py ile ayni sebep - tek TEFAS sorgusu uzun surdugu
icin bu endpoint sadece TEK bir fon tipini tarar. Istemci tipleri
sirayla dener (SEC once, cunku fonlarin cogu orada).
"""
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json
from datetime import date, timedelta

VALID_TYPES = ["SEC", "PEN", "ETF", "RE", "VC"]


def get_type_list(fund_type):
    from tefasfon import get_funds
    # Bugun tatil/hafta sonu olabilir; son birkac gunu kapsayan kisa bir
    # aralik vererek en az bir islem gunu yakalamayi garantiliyoruz.
    end = date.today()
    start = end - timedelta(days=4)
    df = get_funds(
        fund_type=fund_type,
        start_date=start.strftime("%d.%m.%Y"),
        end_date=end.strftime("%d.%m.%Y"),
    )
    seen = {}
    if df is not None:
        for _, row in df.iterrows():
            code = row.get("fonKodu")
            if code and code not in seen:
                seen[code] = {
                    "code": code,
                    "name": row.get("fonUnvan"),
                    "type": fund_type,
                }
    return list(seen.values())


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        q = (qs.get("q") or [""])[0].strip().upper()
        fund_type = (qs.get("type") or ["SEC"])[0].strip().upper()

        if fund_type not in VALID_TYPES:
            fund_type = "SEC"

        if len(q) < 2:
            self._json(200, {"type": fund_type, "results": []})
            return

        try:
            items = get_type_list(fund_type)
        except Exception as e:
            self._json(502, {"error": f"{type(e).__name__}: {e}", "type": fund_type})
            return

        results = []
        for it in items:
            code = (it["code"] or "").upper()
            name = (it["name"] or "").upper()
            if q in code or q in name:
                results.append(it)
            if len(results) >= 30:
                break

        self._json(200, {"type": fund_type, "results": results})

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
