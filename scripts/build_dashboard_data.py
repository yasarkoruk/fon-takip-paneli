"""Build the one small static JSON payload read by the browser."""
from __future__ import annotations

from .analytics import build_metrics
from .common import DATA_DIR, fund_dir, load_config, now_istanbul, read_json, write_json_atomic
from .validate_data import validate_history


def build() -> dict:
    config = load_config()
    funds = []
    for fund in config["funds"]:
        if not fund.get("enabled"):
            continue
        history = read_json(fund_dir(fund["code"]) / "history.json", [])
        errors = validate_history(history, fund["code"])
        if errors:
            raise ValueError("; ".join(errors))
        metrics = build_metrics(history)
        funds.append({"fund": fund, "history": history, "metrics": metrics})
        write_json_atomic(fund_dir(fund["code"]) / "metrics.json", metrics)
        write_json_atomic(fund_dir(fund["code"]) / "current.json", metrics["current"])
    payload = {"generated_at": now_istanbul().isoformat(), "timezone": config["timezone"], "funds": funds}
    write_json_atomic(DATA_DIR / "dashboard.json", payload)
    return payload


if __name__ == "__main__":
    build()
