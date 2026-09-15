import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.analytics import build_metrics
from scripts.fetch_tefas import collect_fund
from scripts.tefas_summary import fetch_summary
from scripts.validate_data import validate_history


def row(day, price, aum, investors, shares):
    return {"date": day, "fund_code": "THF", "fund_name": "Test", "price": price, "portfolio_size": aum, "investor_count": investors, "shares_outstanding": shares}


class DataEngineTests(unittest.TestCase):
    def test_validation_rejects_duplicate_dates(self):
        history = [row("2026-09-01", 1, 100, 10, 100), row("2026-09-01", 1.1, 120, 11, 109)]
        self.assertTrue(validate_history(history, "THF"))

    def test_metrics_are_explicitly_estimated_and_rolling(self):
        history = [row("2026-09-01", 1, 100, 10, 100), row("2026-09-02", 1.1, 132, 13, 120), row("2026-09-03", 1.1, 121, 12, 110)]
        metrics = build_metrics(history)
        self.assertEqual(metrics["periods"]["14"]["observations"], 2)
        self.assertEqual(metrics["flow_status"], "GÜÇLÜ ÇIKIŞ")
        self.assertAlmostEqual(metrics["daily"][-1]["estimated_net_flow"], -11)

    def test_single_observation_is_safe(self):
        metrics = build_metrics([row("2026-09-01", 1, 100, 10, 100)])
        self.assertEqual(metrics["flow_status"], "VERİ YETERSİZ")
        self.assertIsNone(metrics["periods"]["14"])

    @patch("scripts.fetch_tefas.now_istanbul")
    @patch("scripts.fetch_tefas.fetch_range")
    def test_collector_continues_after_one_date_times_out(self, fetch_range, now_istanbul):
        now_istanbul.return_value = datetime(2026, 9, 3, 10, 0)
        fetch_range.side_effect = [RuntimeError("timeout"), [row("2026-09-03", 1.1, 121, 12, 110)]]
        config = {"collector": {"request_chunk_days": 1, "request_delay_seconds": 0}}
        with TemporaryDirectory() as directory, patch("scripts.fetch_tefas.fund_dir", return_value=Path(directory)):
            Path(directory, "history.json").write_text(
                '[{"date":"2026-09-01","fund_code":"THF","fund_name":"Test","price":1,"portfolio_size":100,"investor_count":10,"shares_outstanding":100}]',
                encoding="utf-8",
            )
            history, added, failed_dates, stopped_early = collect_fund({"code": "THF"}, config, False, 2)
        self.assertEqual(added, 1)
        self.assertEqual(len(history), 2)
        self.assertEqual(failed_dates, ["2026-09-02"])
        self.assertFalse(stopped_early)

    @patch("scripts.fetch_tefas.now_istanbul")
    @patch("scripts.fetch_tefas.fetch_range", side_effect=RuntimeError("timeout"))
    def test_collector_fails_without_any_preserved_data(self, fetch_range, now_istanbul):
        now_istanbul.return_value = datetime(2026, 9, 2, 10, 0)
        config = {"collector": {"request_chunk_days": 1, "request_delay_seconds": 0, "max_consecutive_failed_dates": 2}}
        with TemporaryDirectory() as directory, patch("scripts.fetch_tefas.fund_dir", return_value=Path(directory)):
            with self.assertRaisesRegex(RuntimeError, "tüm tarih sorgularında başarısız"):
                collect_fund({"code": "THF"}, config, False, 1)

    @patch("scripts.fetch_tefas.now_istanbul")
    @patch("scripts.fetch_tefas.fetch_range", side_effect=RuntimeError("timeout"))
    def test_collector_preserves_history_and_stops_after_consecutive_timeouts(self, fetch_range, now_istanbul):
        now_istanbul.return_value = datetime(2026, 9, 3, 10, 0)
        config = {"collector": {"request_chunk_days": 1, "request_delay_seconds": 0, "max_consecutive_failed_dates": 2}}
        with TemporaryDirectory() as directory, patch("scripts.fetch_tefas.fund_dir", return_value=Path(directory)):
            Path(directory, "history.json").write_text(
                '[{"date":"2026-09-01","fund_code":"THF","fund_name":"Test","price":1,"portfolio_size":100,"investor_count":10,"shares_outstanding":100}]',
                encoding="utf-8",
            )
            history, added, failed_dates, stopped_early = collect_fund({"code": "THF"}, config, False, 2)
        self.assertEqual(len(history), 1)
        self.assertEqual(added, 0)
        self.assertEqual(failed_dates, ["2026-09-02", "2026-09-03"])
        self.assertTrue(stopped_early)

    @patch("scripts.tefas_summary._fund_information")
    @patch("tefasfon.get_portfolio")
    @patch("tefasfon.get_returns")
    def test_summary_preserves_official_rank_and_market_share(self, returns, portfolio, information):
        # Network calls are covered by the collector; this protects the
        # normalization contract for fields that used to be discarded.
        import pandas as pd

        returns.return_value = pd.DataFrame([{"getiri1a": 1, "getiri3a": 2, "getiri6a": 3, "getiri1y": 4}])
        portfolio.return_value = pd.DataFrame([{"tarih": "2026-09-08", "hs": 82.66}])
        information.return_value = {"fonKategori": "Hisse Senedi Fonu", "kategoriDerece": 2, "kategoriFonSay": 200, "pazarPayi": 34.82}
        summary = fetch_summary({"code": "THF", "type": "SEC", "category": "Eski"}, "2026-09-08", {"collector": {"max_retries": 1}})
        self.assertEqual(summary["category_rank_1y"], "2/200")
        self.assertEqual(summary["category_fund_count_1y"], 200)
        self.assertEqual(summary["market_share_pct"], 34.82)


if __name__ == "__main__":
    unittest.main()
