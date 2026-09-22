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


def collect_fund(fund: dict, config: dict, skip_fetch: bool, backfill_days: int | None) -> tuple[list[dict], int, list[str], bool]:
    path = fund_dir(fund["code"]) / "history.json"
    existing = read_json(path, [])
    by_date = {item["date"]: item for item in existing if item.get("date")}
    if skip_fetch:
        history = [by_date[key] for key in sorted(by_date)]
        write_json_atomic(path, history)
        return history, 0, [], False
    today = now_istanbul().date()
    days = backfill_days if backfill_days is not None else config["collector"]["default_history_days"]
    # TEFAS may omit intervening rows from a multi-day query for a single fund.
    # Querying one calendar day at a time preserves every published transaction day.
    start = today - timedelta(days=days)
    cursor = start
    added = 0
    successful_requests = 0
    failed_dates = []
    last_error = None
    consecutive_failures = 0
    stopped_early = False
    windows = []
    while cursor <= today:
        end = min(cursor + timedelta(days=config["collector"]["request_chunk_days"] - 1), today)
        windows.append((cursor, end))
        cursor = end + timedelta(days=1)
    # Normal recovery must reach today's data BEFORE older repair requests can
    # exhaust the timeout budget. Explicit historical backfills keep their order.
    if backfill_days is None:
        windows.reverse()
    for cursor, end in windows:
        # An explicit backfill fills gaps without needlessly re-querying dates
        # that were already validated in an earlier pass.
        if backfill_days is not None and cursor.isoformat() in by_date:
            continue
        try:
            records = fetch_range(fund, cursor, end, config)
            errors = validate_history(records, fund["code"])
            if errors or any(not cursor.isoformat() <= row["date"] <= end.isoformat() for row in records):
                raise ValueError("TEFAS yanıt tarihi veya veri doğrulaması başarısız: " + "; ".join(errors))
            successful_requests += 1
            consecutive_failures = 0
        except Exception as error:
            # Preserve existing data and continue. The next scheduled run will
            # query this missing day again, so one transient TEFAS timeout does
            # not invalidate every other date in the collection window.
            failed_dates.append(cursor.isoformat())
            last_error = error
            consecutive_failures += 1
            if (
                consecutive_failures >= config["collector"].get("max_consecutive_failed_dates", 2)
                or len(failed_dates) >= config["collector"].get("max_failed_dates_per_run", 2)
            ):
                stopped_early = True
                break
            continue
        for record in records:
            if record["date"] not in by_date:
                added += 1
            by_date[record["date"]] = record
        if config["collector"].get("request_delay_seconds"):
            time.sleep(config["collector"]["request_delay_seconds"])
    if not by_date and failed_dates and successful_requests == 0:
        raise RuntimeError(
            f"TEFAS tüm tarih sorgularında başarısız oldu ({len(failed_dates)} tarih): {last_error}"
        )
    history = [by_date[key] for key in sorted(by_date)]
    errors = validate_history(history, fund["code"])
    if errors:
        raise ValueError("; ".join(errors))
    write_json_atomic(path, history)
    return history, added, failed_dates, stopped_early


def expected_data_date() -> date:
    """Latest business date expected from TEFAS at the current Istanbul time."""
    current = now_istanbul()
    expected = current.date() if current.hour >= 10 else current.date() - timedelta(days=1)
    while expected.weekday() >= 5:
        expected -= timedelta(days=1)
    return expected


def status(code: str, state: str, message: str, observations: int = 0,
           summary_error: str | None = None, data_success: bool = False) -> None:
    previous = read_json(fund_dir(code) / "status.json", {})
    history = read_json(fund_dir(code) / "history.json", [])
    checked_at = now_istanbul().isoformat()
    payload = {"state": state, "message": message, "checked_at": checked_at, "observations": observations,
               "data_date": history[-1]["date"] if history else None,
               "last_success_at": checked_at if data_success else previous.get("last_success_at")}
    if summary_error:
        payload["summary"] = {"state": "error", "message": summary_error}
    else:
        payload["summary"] = previous.get("summary", {"state": "unknown"}) if state == "error" else {"state": "ok"}
    write_json_atomic(fund_dir(code) / "status.json", payload)


def append_status_warning(code: str, message: str) -> None:
    path = fund_dir(code) / "status.json"
    payload = read_json(path, {})
    payload["state"] = "warning"
    existing = payload.get("message")
    payload["message"] = f"{existing}; {message}" if existing else message
    payload["checked_at"] = now_istanbul().isoformat()
    write_json_atomic(path, payload)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-fetch", action="store_true", help="Only migrate/build existing data; no TEFAS request.")
    parser.add_argument("--backfill-days", type=int, help="Explicit historical lookback; use a staged value such as 90 or 365.")
    parser.add_argument("--recent-days", type=int, help="Bounded current-date recovery, newest date first.")
    parser.add_argument("--skip-catalog", action="store_true", help="Refresh fund data without the independent market catalogue.")
    args = parser.parse_args()
    config = load_config()
    if args.recent_days is not None:
        if not 1 <= args.recent_days <= 90:
            parser.error("recent-days must be between 1 and 90")
        config["collector"]["default_history_days"] = args.recent_days
    failed = False
    for fund in config["funds"]:
        if not fund.get("enabled"):
            continue
        try:
            history, added, failed_dates, stopped_early = collect_fund(fund, config, args.skip_fetch, args.backfill_days)
            _, summary_error = (None, None) if args.skip_fetch else collect_summary(fund, history, config)
            state = "warning" if failed_dates or summary_error else "ok"
            message = f"{added} yeni işlem günü işlendi"
            expected = expected_data_date()
            data_fresh = bool(history and history[-1]["date"] >= expected.isoformat())
            if not args.skip_fetch and not data_fresh:
                state = "warning"
                message += "; beklenen yakın dönem için yeni TEFAS kaydı doğrulanamadı (tatil veya yayın gecikmesi olabilir)"
            if failed_dates:
                message += f"; {len(failed_dates)} tarih geçici olarak alınamadı ve sonraki taramada yeniden denenecek"
            if stopped_early:
                message += "; art arda zaman aşımı nedeniyle tarama erken sonlandırıldı"
            if not args.skip_fetch:
                status(fund["code"], state, message, len(history), summary_error, data_success=data_fresh)
            # Summary/catalogue interruptions remain visible warnings, but a
            # current validated daily record must not turn the whole workflow
            # red. A stale/missing core history still fails loudly.
            failed = failed or (not args.skip_fetch and not data_fresh)
        except Exception as error:
            status(fund["code"], "error", str(error))
            failed = True
    if not args.skip_fetch and not args.skip_catalog:
        try:
            collect_catalog(config)
        except Exception as error:
            # Search can safely use the last successful static catalogue. A
            # catalogue outage must not discard freshly collected fund data.
            for fund in config["funds"]:
                if fund.get("enabled"):
                    append_status_warning(fund["code"], f"Fon kataloğu güncellenemedi: {error}")
    build()
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
