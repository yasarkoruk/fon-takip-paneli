"""Idempotent TEFAS collector: import legacy data, fill gaps, validate, then publish static JSON."""
from __future__ import annotations

import argparse
import time
from datetime import date, timedelta

from .build_dashboard_data import build
from .common import fund_dir, iso_date, load_config, now_istanbul, number, read_json, write_json_atomic
from .fetch_catalog import collect_catalog
from .tefas_summary import collect_summary
from .validate_data import validate_history


def row_value(row, *names):
    for name in names:
        value = row.get(name) if hasattr(row, "get") else None
        if value is not None:
            return value
    return None


def normalise(row, fund: dict) -> dict | None:
    record_date = iso_date(row_value(row, "tarih", "date"))
    if not record_date:
        return None
    return {
        "date": record_date,
        "fetched_at": now_istanbul().isoformat(),
        "fund_code": str(row_value(row, "fonKodu", "fund_code") or fund["code"]).upper(),
        "fund_name": row_value(row, "fonUnvan", "fund_name") or fund.get("name", ""),
        "price": number(row_value(row, "fiyat", "price")),
        "portfolio_size": number(row_value(row, "portfoyBuyukluk", "portfolio_size")),
        "investor_count": number(row_value(row, "kisiSayisi", "investor_count")),
        "shares_outstanding": number(row_value(row, "tedPaySayisi", "shares_outstanding")),
    }


def fetch_range(fund: dict, start: date, end: date, config: dict) -> list[dict]:
    # tefasfon's public get_funds filters fund codes after paging the whole
    # market result set. Supplying the code to TEFAS itself is essential for a
    # complete multi-day history of an individual fund.
    from tefasfon import getter
    settings = config["collector"]
    last_error = None
    for attempt in range(settings["max_retries"]):
        try:
            start_iso, end_iso = start.isoformat(), end.isoformat()
            session = getter._new_session(getter._FUND_PORTAL[fund["type"]], start_iso, end_iso, getter._FUND_URL_PARAM[fund["type"]])
            payload = {
                "fonTipi": getter._FUND_TIPI[fund["type"]], "fonKodu": fund["code"], "aramaMetni": None,
                "fonTurKod": None, "fonGrubu": None, "sfonTurKod": None,
                "basTarih": start.strftime("%Y%m%d"), "bitTarih": end.strftime("%Y%m%d"),
                "basSira": 1, "bitSira": getter._PAGE_SIZE,
                "fonTurAciklama": None, "dil": "TR", "kurucuKod": None,
            }
            rows = getter._get_all_pages(
                session, getter._API_ENDPOINT["general_information"], payload,
                getter._FUND_PORTAL[fund["type"]], start_iso, end_iso,
            )
            return [record for row in rows if (record := normalise(row, fund))]
        except Exception as error:  # TEFAS/Akamai errors are transient; preserve existing data.
            last_error = error
            if attempt + 1 < settings["max_retries"]:
                time.sleep(settings["retry_delay_seconds"] * (attempt + 1))
    raise RuntimeError(f"TEFAS sorgusu başarısız: {type(last_error).__name__}: {last_error}")


def collect_fund(fund: dict, config: dict, skip_fetch: bool, backfill_days: int | None) -> tuple[list[dict], int]:
    path = fund_dir(fund["code"]) / "history.json"
    existing = read_json(path, [])
    by_date = {item["date"]: item for item in existing if item.get("date")}
    if skip_fetch:
        history = [by_date[key] for key in sorted(by_date)]
        write_json_atomic(path, history)
        return history, 0
    today = now_istanbul().date()
    days = backfill_days if backfill_days is not None else config["collector"]["default_history_days"]
    # TEFAS may omit intervening rows from a multi-day query for a single fund.
    # Querying one calendar day at a time preserves every published transaction day.
    start = today - timedelta(days=days)
    cursor = start
    added = 0
    while cursor <= today:
        end = min(cursor + timedelta(days=config["collector"]["request_chunk_days"] - 1), today)
        # An explicit backfill fills gaps without needlessly re-querying dates
        # that were already validated in an earlier pass.
        if backfill_days is not None and cursor.isoformat() in by_date:
            cursor = end + timedelta(days=1)
            continue
        for record in fetch_range(fund, cursor, end, config):
            if record["date"] not in by_date:
                added += 1
            by_date[record["date"]] = record
        if config["collector"].get("request_delay_seconds"):
            time.sleep(config["collector"]["request_delay_seconds"])
        cursor = end + timedelta(days=1)
    history = [by_date[key] for key in sorted(by_date)]
    errors = validate_history(history, fund["code"])
    if errors:
        raise ValueError("; ".join(errors))
    write_json_atomic(path, history)
    return history, added


def status(code: str, state: str, message: str, observations: int = 0, summary_error: str | None = None) -> None:
    payload = {"state": state, "message": message, "checked_at": now_istanbul().isoformat(), "observations": observations}
    if summary_error:
        payload["summary"] = {"state": "error", "message": summary_error}
    else:
        payload["summary"] = {"state": "ok"}
    write_json_atomic(fund_dir(code) / "status.json", payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-fetch", action="store_true", help="Only migrate/build existing data; no TEFAS request.")
    parser.add_argument("--backfill-days", type=int, help="Explicit historical lookback; use a staged value such as 90 or 365.")
    args = parser.parse_args()
    config = load_config()
    for fund in config["funds"]:
        if not fund.get("enabled"):
            continue
        try:
            history, added = collect_fund(fund, config, args.skip_fetch, args.backfill_days)
            _, summary_error = collect_summary(fund, history, config)
            status(fund["code"], "ok", f"{added} yeni işlem günü işlendi", len(history), summary_error)
        except Exception as error:
            status(fund["code"], "error", str(error))
            raise
    if not args.skip_fetch:
        collect_catalog(config)
    build()


if __name__ == "__main__":
    main()
