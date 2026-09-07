from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json
import time
from datetime import date

FUND_TYPES = ["SEC", "PEN", "ETF", "RE", "VC"]
CACHE_TTL = 900  # 15 dakika
_cache = {}


def get_type_list(fund_type):
    now = time.time()
    cached = _cache.get(fund_type)
    if cached and now - cached[0] < CACHE_TTL:
        return cached[1]
    from tefasfon import get_funds
    today = date.today().strftime("%d.%m.%Y")
    df = get_funds(fund_type=fund_type, start_date=today, end_date=today)
    items = []
    if df is not None:
        for _, row in df.iterrows():
            items.append({
                "code": row.get("fonKodu"),
                "name": row.get("fonUnvan"),
                "type": fund_type,
            })
    _cache[fund_type] = (now, items)
    return items


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        qs = parse_qs(urlparse(self.path).query)
        q = (qs.get("q") or [""])[0].strip().upper()
        if len(q) < 2:
            self._json(200, {"results": []})
            return

        results = []
        errors = []
        for t in FUND_TYPES:
            try:
                items = get_type_list(t)
            except Exception as e:
                errors.append(f"{t}: {type(e).__name__}")
                continue
            for it in items:
                code = (it["code"] or "").upper()
                name = (it["name"] or "").upper()
                if q in code or q in name:
                    results.append(it)
            if len(results) >= 30:
                break

        payload = {"results": results[:30]}
        if not results and errors:
            payload["warning"] = "; ".join(errors)
        self._json(200, payload)

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")

    def _json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors()
        self.end_headers()
        self.wfile.write(body)
