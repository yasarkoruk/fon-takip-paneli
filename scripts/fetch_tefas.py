"""Idempotent TEFAS collector: import legacy data, fill gaps, validate, then publish static JSON."""
from __future__ import annotations

import argparse
import time
from datetime import date, timedelta

from .build_dashboard_data import build
from .common import ROOT, fund_dir, iso_date, load_config, now_istanbul, number, read_json, write_json_atomic
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


def legacy_history(code: str) -> list[dict]:
    return read_json(ROOT / "data" / f"{code}_history.json", [])


def fetch_range(fund: dict, start: date, end: date, config: dict) -> list[dict]:
    from tefasfon import get_funds
    settings = config["collector"]
    last_error = None
    for attempt in range(settings["max_retries"]):
        try:
            frame = get_funds(fund_type=fund["type"], start_date=start.strftime("%d.%m.%Y"), end_date=end.strftime("%d.%m.%Y"), fund_codes=[fund["code"]])
            return [normalise(row, fund) for _, row in frame.iterrows() if normalise(row, fund)] if frame is not None else []
        except Exception as error:  # TEFAS/Akamai errors are transient; preserve existing data.
            last_error = error
            if attempt + 1 < settings["max_retries"]:
                time.sleep(settings["retry_delay_seconds"] * (attempt + 1))
    raise RuntimeError(f"TEFAS sorgusu başarısız: {type(last_error).__name__}: {last_error}")


def collect_fund(fund: dict, config: dict, skip_fetch: bool, backfill_days: int | None) -> tuple[list[dict], int]:
    path = fund_dir(fund["code"]) / "history.json"
    existing = read_json(path, []) or legacy_history(fund["code"])
    by_date = {item["date"]: item for item in existing if item.get("date")}
    if skip_fetch:
        history = [by_date[key] for key in sorted(by_date)]
        write_json_atomic(path, history)
        return history, 0
    today = now_istanbul().date()
    days = backfill_days if backfill_days is not None else config["collector"]["default_history_days"]
    # Normal runs inspect a bounded recent window (fast recovery). A manual, explicit
    # --backfill-days 365 run can progressively widen historical coverage.
    start = today - timedelta(days=days)
    cursor = start
    added = 0
    while cursor <= today:
        end = min(cursor + timedelta(days=config["collector"]["request_chunk_days"] - 1), today)
        for record in fetch_range(fund, cursor, end, config):
            if record["date"] not in by_date:
                added += 1
            by_date[record["date"]] = record
        cursor = end + timedelta(days=1)
    history = [by_date[key] for key in sorted(by_date)]
    errors = validate_history(history, fund["code"])
    if errors:
        raise ValueError("; ".join(errors))
    write_json_atomic(path, history)
    return history, added


def status(code: str, state: str, message: str, observations: int = 0) -> None:
    write_json_atomic(fund_dir(code) / "status.json", {"state": state, "message": message, "checked_at": now_istanbul().isoformat(), "observations": observations})


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
            status(fund["code"], "ok", f"{added} yeni işlem günü işlendi", len(history))
        except Exception as error:
            status(fund["code"], "error", str(error))
            raise
    build()


if __name__ == "__main__":
    main()
