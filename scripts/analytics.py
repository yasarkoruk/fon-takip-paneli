"""Turn validated daily observations into dashboard-ready, explicitly estimated metrics."""
from __future__ import annotations

from .validate_data import warnings_for_adjacent

PERIODS = (1, 7, 14, 30, 90, 365)


def daily_rows(history: list[dict]) -> list[dict]:
    rows = []
    for previous, current in zip(history, history[1:]):
        price_return = current["price"] / previous["price"] - 1 if previous["price"] else None
        aum_change = current["portfolio_size"] - previous["portfolio_size"]
        price_effect = previous["portfolio_size"] * price_return if price_return is not None else None
        aum_flow = aum_change - price_effect if price_effect is not None else None
        share_change = current["shares_outstanding"] - previous["shares_outstanding"]
        share_flow = share_change * ((current["price"] + previous["price"]) / 2)
        warnings = warnings_for_adjacent(previous, current)
        rows.append({
            "date": current["date"],
            "estimated_net_flow": aum_flow,
            "share_based_flow": share_flow,
            "flow_method_gap": abs(aum_flow - share_flow) if aum_flow is not None else None,
            "investor_change": current["investor_count"] - previous["investor_count"],
            "shares_change": share_change,
            "aum_change": aum_change,
            "price_return_pct": price_return * 100 if price_return is not None else None,
            "quality_warnings": warnings,
        })
    return rows


def period_metrics(history: list[dict], daily: list[dict], days: int) -> dict | None:
    if len(history) < 2:
        return None
    used = daily[-days:]
    if not used:
        return None
    start = history[-len(used) - 1]
    end = history[-1]
    return {
        "observations": len(used),
        "from": start["date"],
        "to": end["date"],
        "estimated_net_flow": sum(row["estimated_net_flow"] or 0 for row in used),
        "share_based_flow": sum(row["share_based_flow"] or 0 for row in used),
        "investor_change": end["investor_count"] - start["investor_count"],
        "shares_change": end["shares_outstanding"] - start["shares_outstanding"],
        "aum_change": end["portfolio_size"] - start["portfolio_size"],
        "return_pct": (end["price"] / start["price"] - 1) * 100 if start["price"] else None,
    }


def flow_status(today: dict | None) -> str:
    if not today or today["estimated_net_flow"] is None:
        return "VERİ YETERSİZ"
    flow = today["estimated_net_flow"]
    investors = today["investor_change"]
    if flow > 0 and investors > 0:
        return "GÜÇLÜ GİRİŞ"
    if flow > 0:
        return "GİRİŞ"
    if flow < 0 and investors < 0:
        return "GÜÇLÜ ÇIKIŞ"
    if flow < 0:
        return "ÇIKIŞ"
    return "NÖTR"


def build_metrics(history: list[dict]) -> dict:
    daily = daily_rows(history)
    last = history[-1] if history else None
    return {
        "current": last,
        "daily": daily,
        "periods": {str(days): period_metrics(history, daily, days) for days in PERIODS},
        "flow_status": flow_status(daily[-1] if daily else None),
    }
