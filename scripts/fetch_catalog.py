"""Build a static, searchable catalogue of all fund types exposed by TEFAS."""
from __future__ import annotations

import math
import time

from .common import DATA_DIR, load_config, now_istanbul, write_json_atomic

FUND_TYPES = ("SEC", "PEN", "ETF", "RE", "VC")


def text_or_none(value) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    return text or None


def collect_catalog(config: dict) -> dict:
    from tefasfon import get_returns

    settings = config["collector"]
    by_code: dict[str, dict] = {}
    for fund_type in FUND_TYPES:
        error = None
        for attempt in range(settings["max_retries"]):
            try:
                frame = get_returns(fund_type, "RB")
                for _, row in frame.iterrows():
                    code = str(row.get("fonKodu") or "").strip().upper()
                    name = text_or_none(row.get("fonUnvan")) or ""
                    if code and name:
                        by_code[code] = {
                            "code": code,
                            "name": name,
                            "type": fund_type,
                            "category": text_or_none(row.get("fonTurAciklama")),
                            "active": bool(row.get("tefasDurum") is True),
                        }
                break
            except Exception as exc:
                error = exc
                if attempt + 1 < settings["max_retries"]:
                    time.sleep(settings["retry_delay_seconds"] * (attempt + 1))
        else:
            raise RuntimeError(f"TEFAS fon kataloğu alınamadı ({fund_type}): {type(error).__name__}: {error}")
    payload = {"generated_at": now_istanbul().isoformat(), "count": len(by_code), "funds": sorted(by_code.values(), key=lambda item: (item["code"], item["name"]))}
    write_json_atomic(DATA_DIR / "catalog.json", payload)
    return payload


if __name__ == "__main__":
    collect_catalog(load_config())
