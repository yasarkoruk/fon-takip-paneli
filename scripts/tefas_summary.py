"""TEFAS return and portfolio summary collector for the static dashboard."""
from __future__ import annotations

import time
from datetime import date

from .common import iso_date, now_istanbul, number, write_json_atomic, fund_dir


# TEFAS portfolio_breakdown field names. Unknown/non-zero fields are retained
# with their TEFAS code so a new allocation is never silently discarded.
ASSET_LABELS = {
    "hs": "Hisse Senedi",
    "yyf": "Yatırım Fonları Katılma Payları",
    "vint": "Vadeli İşlemler Nakit Teminatları",
    "fb": "Finansman Bonosu",
    "db": "Devlet Tahvili",
    "hb": "Hazine Bonosu",
    "byf": "Borsa Yatırım Fonu",
    "tpp": "Ters Repo",
    "vm": "Vadeli Mevduat",
    "kks": "Kira Sertifikası",
    "gyy": "Gayrimenkul Yatırım Ortaklığı",
}
RETURN_FIELDS = {"1m": "getiri1a", "3m": "getiri3a", "6m": "getiri6a", "1y": "getiri1y"}
IDENTITY_FIELDS = {"fonKodu", "fonUnvan", "tarih", "bilFiyat", "rn"}


def _first_row(frame):
    if frame is None or frame.empty:
        raise ValueError("TEFAS yanıtında fon için kayıt bulunamadı")
    return frame.iloc[0]


def _asset_allocation(row) -> list[dict]:
    assets = []
    for field, value in row.items():
        if field in IDENTITY_FIELDS:
            continue
        ratio = number(value)
        if ratio is not None and ratio > 0:
            assets.append({"code": field, "name": ASSET_LABELS.get(field, f"TEFAS varlık kalemi ({field})"), "ratio_pct": ratio})
    return sorted(assets, key=lambda item: item["ratio_pct"], reverse=True)


def _fund_information(fund: dict, source_date: str) -> dict:
    """Read the official TEFAS fund-information panel.

    The historical endpoint intentionally contains only daily price/AUM/share
    records.  Category rank and market share live in a separate TEFAS response,
    so they must be collected independently instead of being silently rendered
    as unavailable.
    """
    from tefasfon import getter

    start = date.fromisoformat(source_date)
    start_iso = start.isoformat()
    session = getter._new_session(
        getter._FUND_PORTAL[fund["type"]], start_iso, start_iso,
        getter._FUND_URL_PARAM[fund["type"]],
    )
    response = session.post(
        "https://www.tefas.gov.tr/api/funds/fonBilgiGetir",
        json={"fonKodu": fund["code"]},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("resultList") or []
    if payload.get("errorCode") or not rows:
        raise ValueError(payload.get("errorMessage") or "TEFAS fon bilgisi bulunamadı")
    return rows[0]


def _category_rank(information: dict) -> str | None:
    rank = number(information.get("kategoriDerece"))
    total = number(information.get("kategoriFonSay"))
    if rank is None or total is None:
        return None
    return f"{rank:g}/{total:g}"


def fetch_summary(fund: dict, source_date: str, config: dict) -> dict:
    """Fetch TEFAS' current return and allocation panels and normalize them."""
    from tefasfon import get_portfolio, get_returns

    settings = config["collector"]
    error = None
    for attempt in range(settings["max_retries"]):
        try:
            returns = _first_row(get_returns(fund["type"], "RB", fund_codes=[fund["code"]]))
            portfolio = _first_row(get_portfolio(
                fund["type"],
                date.fromisoformat(source_date).strftime("%d.%m.%Y"),
                date.fromisoformat(source_date).strftime("%d.%m.%Y"),
                fund_codes=[fund["code"]],
            ))
            information = _fund_information(fund, source_date)
            return {
                "state": "ok",
                "fetched_at": now_istanbul().isoformat(),
                "source_date": iso_date(portfolio.get("tarih")) or source_date,
                "fund_category": information.get("fonKategori") or fund.get("category"),
                "category_rank_1y": _category_rank(information),
                "category_fund_count_1y": number(information.get("kategoriFonSay")),
                "market_share_pct": number(information.get("pazarPayi")),
                "returns_pct": {period: number(returns.get(field)) for period, field in RETURN_FIELDS.items()},
                "asset_allocation": _asset_allocation(portfolio),
            }
        except Exception as exc:  # Keep the last good summary on transient TEFAS failures.
            error = exc
            if attempt + 1 < settings["max_retries"]:
                time.sleep(settings["retry_delay_seconds"] * (attempt + 1))
    raise RuntimeError(f"TEFAS özet sorgusu başarısız: {type(error).__name__}: {error}")


def collect_summary(fund: dict, history: list[dict], config: dict) -> tuple[dict | None, str | None]:
    if not history:
        return None, "Özet alınamadı: doğrulanmış tarihsel kayıt yok"
    try:
        summary = fetch_summary(fund, history[-1]["date"], config)
        write_json_atomic(fund_dir(fund["code"]) / "tefas_summary.json", summary)
        return summary, None
    except Exception as error:
        return None, str(error)
