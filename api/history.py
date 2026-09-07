from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError

MAX_TOTAL_SECONDS = 50  # toplam fonksiyon suresi icin guvenlik siniri

FUND_TYPES = ["SEC", "PEN", "ETF", "RE", "VC"]
CHUNK_DAYS = 7          # tefasfon/TEFAS genis tarih araliklarinda sayfalama
                        # sinirina takilip sadece son gunu donduruyor; bu yuzden
                        # istegi kucuk parcalara bolup birlestiriyoruz.
CHUNK_TIMEOUT = 25     # saniye - bir parca bu surede donmezse vazgecilir
CHUNK_DELAY = 1        # saniye - parcalar arasi kisa bekleme (ardisik istekler
                        # arasinda kucuk bir bosluk birakmak guvenilirligi artirdi)
# NOT: Parcalar KASITLI olarak SIRALI (paralel degil) cekiliyor. Ayni anda
# birden fazla istek gonderilirse TEFAS/Akamai bot korumasi devreye girip
# coklu istegin cogunu askida birakiyor (test edildi). Sirali istekler daha
# yavas ama guvenilir.


def parse_date(s):
    return datetime.strptime(s, "%d.%m.%Y")


def fmt_date(d):
    return d.strftime("%d.%m.%Y")


def build_chunks(start_dt, end_dt):
    chunks = []
    cursor = start_dt
    while cursor <= end_dt:
        chunk_end = min(cursor + timedelta(days=CHUNK_DAYS - 1), end_dt)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def fetch_chunk(fund_code, start_dt, end_dt, fund_type):
    from tefasfon import get_funds
    return get_funds(
        fund_type=fund_type,
        start_date=fmt_date(start_dt),
        end_date=fmt_date(end_dt),
        fund_codes=[fund_code],
    )


def fetch_chunk_with_timeout(fund_code, start_dt, end_dt, fund_type):
    """Bir parcayi CHUNK_TIMEOUT saniye icinde cekmeye calisir; asilirsa
    None dondurur (hatayi yutar). ONEMLI: ThreadPoolExecutor'i "with" ile
    kullanmiyoruz cunku "with" bloktan cikarken shutdown(wait=True)
    cagirir ve bu, zaman asimina ugrayan (hala arka planda calisan)
    is parcasinin bitmesini bekleyerek timeout'u anlamsizlastirir."""
    ex = ThreadPoolExecutor(max_workers=1)
    future = ex.submit(fetch_chunk, fund_code, start_dt, end_dt, fund_type)
    try:
        result = future.result(timeout=CHUNK_TIMEOUT)
        ex.shutdown(wait=False)
        return result, None
    except FutureTimeoutError:
        ex.shutdown(wait=False)
        return None, TimeoutError(f"{fmt_date(start_dt)}-{fmt_date(end_dt)} zaman asimina ugradi")
    except Exception as e:
        ex.shutdown(wait=False)
        return None, e


def fetch_history(fund_code, start_str, end_str, fund_type=None):
    start_dt = parse_date(start_str)
    end_dt = parse_date(end_str)
    types_to_try = [fund_type] if fund_type else FUND_TYPES
    chunks = build_chunks(start_dt, end_dt)

    for t in types_to_try:
        rows_by_date = {}
        last_err = None
        ok_count = 0
        fail_count = 0

        # Sirali: TEFAS/Akamai ayni anda gelen coklu istekleri askiya
        # aliyor, bu yuzden parcalari tek tek, birbiri ardina cekiyoruz.
        start_time = time.monotonic()
        for idx, (c_start, c_end) in enumerate(chunks):
            if time.monotonic() - start_time > MAX_TOTAL_SECONDS:
                last_err = TimeoutError("toplam sure siniri asildi, kalan parcalar atlandi")
                fail_count += len(chunks) - idx
                break
            if idx > 0:
                time.sleep(CHUNK_DELAY)
            df, err = fetch_chunk_with_timeout(fund_code, c_start, c_end, t)
            if err is not None:
                last_err = err
                fail_count += 1
                continue
            if df is not None and len(df) > 0:
                ok_count += 1
                for _, row in df.iterrows():
                    tarih = row["tarih"]
                    d = tarih.date().isoformat() if hasattr(tarih, "date") else str(tarih)[:10]
                    rows_by_date[d] = row

        if ok_count > 0:
            return list(rows_by_date.values()), t, {"ok": ok_count, "failed": fail_count}
        if last_err and t == types_to_try[-1]:
            raise last_err

    return None, None, None


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
            rows, used_type, chunk_info = fetch_history(code, start, end, fund_type)
        except Exception as e:
            self._json(502, {"error": f"{type(e).__name__}: {e}"})
            return

        if not rows:
            self._json(404, {"error": "Bu fon kodu / tarih araligi icin veri bulunamadi"})
            return

        out = []
        for row in rows:
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
        self._json(200, {"fund_type": used_type, "chunks": chunk_info, "data": out})

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
