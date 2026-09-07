"""Validation that rejects corrupt data without deleting valid observations."""
from __future__ import annotations

from collections import Counter

REQUIRED = ("date", "fund_code", "price", "portfolio_size", "investor_count", "shares_outstanding")


def validate_history(records: list[dict], code: str) -> list[str]:
    errors: list[str] = []
    dates = []
    for index, item in enumerate(records):
        prefix = f"{code}[{index}]"
        for field in REQUIRED:
            if item.get(field) is None:
                errors.append(f"{prefix}: {field} boş")
        if item.get("fund_code") and item["fund_code"].upper() != code.upper():
            errors.append(f"{prefix}: fon kodu uyuşmuyor")
        dates.append(item.get("date"))
        for field in ("price", "portfolio_size", "investor_count", "shares_outstanding"):
            value = item.get(field)
            if value is not None and (not isinstance(value, (int, float)) or value < 0):
                errors.append(f"{prefix}: {field} geçersiz")
    duplicates = [d for d, count in Counter(dates).items() if d and count > 1]
    if duplicates:
        errors.append(f"{code}: tekrar eden tarihler: {', '.join(sorted(duplicates))}")
    if dates != sorted(dates):
        errors.append(f"{code}: tarihler sıralı değil")
    return errors


def warnings_for_adjacent(previous: dict, current: dict) -> list[str]:
    warnings = []
    for field in ("price", "portfolio_size", "shares_outstanding"):
        before, after = previous.get(field), current.get(field)
        if before and after is not None and abs(after / before - 1) > 0.60:
            warnings.append(f"{field} bir önceki iş gününe göre %60'tan fazla değişti")
    return warnings
