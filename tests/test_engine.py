import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.analytics import build_metrics
from scripts.fetch_tefas import append_status_warning, collect_fund, status, main
from scripts.tefas_summary import fetch_summary
from scripts.validate_data import validate_history


def row(day, price, aum, investors, shares):
    return {"date": day, "fund_code": "THF", "fund_name": "Test", "price": price, "portfolio_size": aum, "investor_count": investors, "shares_outstanding": shares}


class DataEngineTests(unittest.TestCase):
    @patch("scripts.fetch_tefas.now_istanbul", return_value=datetime(2026,9,17,18,0))
    def test_failed_attempt_does_not_advance_success_or_data_date(self, clock):
        from scripts.common import read_json, write_json_atomic
        with TemporaryDirectory() as directory, patch("scripts.fetch_tefas.fund_dir",return_value=Path(directory)):
            write_json_atomic(Path(directory)/"history.json",[row("2026-09-15",1,100,10,100)])
            write_json_atomic(Path(directory)/"status.json",{"last_success_at":"previous","summary":{"state":"error","message":"previous error"}})
            status("THF","error","timeout")
            result=read_json(Path(directory)/"status.json",{})
        self.assertEqual(result["data_date"],"2026-09-15")
        self.assertEqual(result["last_success_at"],"previous")
        self.assertEqual(result["summary"]["state"],"error")

    @patch("scripts.fetch_tefas.build")
    @patch("scripts.fetch_tefas.status")
    @patch("scripts.fetch_tefas.collect_summary")
    @patch("scripts.fetch_tefas.collect_fund",return_value=([row("2026-09-15",1,100,10,100)],0,[],False))
    @patch("scripts.fetch_tefas.load_config",return_value={"funds":[{"code":"THF","enabled":True}]})
    def test_offline_build_is_not_a_successful_scan(self, config, collect, summary, status_mock, build):
        with patch("sys.argv",["fetch_tefas","--skip-fetch"]): main()
        summary.assert_not_called()
        status_mock.assert_not_called()
        build.assert_called_once()

    @patch("scripts.fetch_tefas.expected_data_date", return_value=datetime(2026, 9, 22).date())
    @patch("scripts.fetch_tefas.build")
    @patch("scripts.fetch_tefas.status")
    @patch("scripts.fetch_tefas.collect_summary", return_value=(None, "summary timeout"))
    @patch("scripts.fetch_tefas.collect_fund", return_value=([row("2026-09-22", 1, 100, 10, 100)], 1, ["2026-09-21"], True))
    @patch("scripts.fetch_tefas.load_config", return_value={"funds":[{"code":"THF","enabled":True}]})
    def test_current_core_data_keeps_workflow_green_when_summary_warns(
        self, config, collect, summary, status_mock, build, expected
    ):
        with patch("sys.argv", ["fetch_tefas", "--skip-catalog"]):
            main()
        self.assertEqual(status_mock.call_args.args[1], "warning")
        self.assertTrue(status_mock.call_args.kwargs["data_success"])
        build.assert_called_once()

    @patch("scripts.fetch_tefas.now_istanbul", return_value=datetime(2026,9,17,18,0))
    @patch("scripts.fetch_tefas.fetch_range")
    def test_current_day_is_fetched_before_old_repair_timeouts(self, fetch_range, clock):
        fetch_range.side_effect = [[row("2026-09-17",1,100,10,100)], RuntimeError("timeout"), RuntimeError("timeout")]
        config = {"collector":{"default_history_days":30,"request_chunk_days":1,"request_delay_seconds":0}}
        with TemporaryDirectory() as directory, patch("scripts.fetch_tefas.fund_dir",return_value=Path(directory)):
            history, added, failed, stopped = collect_fund({"code":"THF"},config,False,None)
        self.assertEqual(fetch_range.call_args_list[0].args[1].isoformat(),"2026-09-17")
        self.assertEqual(history[-1]["date"],"2026-09-17")
        self.assertEqual(added,1)
        self.assertTrue(stopped)

    @patch("scripts.fetch_tefas.now_istanbul", return_value=datetime(2026, 9, 22, 12, 0))
    def test_expected_date_is_today_after_morning_scan_time(self, clock):
        from scripts.fetch_tefas import expected_data_date
        self.assertEqual(expected_data_date().isoformat(), "2026-09-22")

    @patch("scripts.fetch_tefas.now_istanbul", return_value=datetime(2026, 9, 22, 0, 54))
    def test_delayed_evening_run_expects_previous_business_day(self, clock):
        from scripts.fetch_tefas import expected_data_date
        self.assertEqual(expected_data_date().isoformat(), "2026-09-21")

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

    @patch("scripts.fetch_tefas.now_istanbul")
    @patch("scripts.fetch_tefas.fetch_range")
    def test_collector_caps_nonconsecutive_timeouts_per_run(self, fetch_range, now_istanbul):
        now_istanbul.return_value = datetime(2026, 9, 4, 10, 0)
        fetch_range.side_effect = [RuntimeError("timeout"), [], RuntimeError("timeout")]
        config = {"collector": {"request_chunk_days": 1, "request_delay_seconds": 0, "max_consecutive_failed_dates": 2, "max_failed_dates_per_run": 2}}
        with TemporaryDirectory() as directory, patch("scripts.fetch_tefas.fund_dir", return_value=Path(directory)):
            Path(directory, "history.json").write_text(
                '[{"date":"2026-09-01","fund_code":"THF","fund_name":"Test","price":1,"portfolio_size":100,"investor_count":10,"shares_outstanding":100}]',
                encoding="utf-8",
            )
            history, added, failed_dates, stopped_early = collect_fund({"code": "THF"}, config, False, 3)
        self.assertEqual(len(history), 1)
        self.assertEqual(added, 0)
        self.assertEqual(failed_dates, ["2026-09-02", "2026-09-04"])
        self.assertTrue(stopped_early)

    @patch("scripts.fetch_tefas.now_istanbul")
    def test_catalog_warning_preserves_existing_status_details(self, now_istanbul):
        now_istanbul.return_value = datetime(2026, 9, 4, 10, 0)
        with TemporaryDirectory() as directory, patch("scripts.fetch_tefas.fund_dir", return_value=Path(directory)):
            Path(directory, "status.json").write_text(
                '{"state":"ok","message":"1 yeni işlem günü işlendi","observations":52,"summary":{"state":"ok"}}',
                encoding="utf-8",
            )
            append_status_warning("THF", "Fon kataloğu güncellenemedi: timeout")
            import json
            result = json.loads(Path(directory, "status.json").read_text(encoding="utf-8"))
        self.assertEqual(result["state"], "warning")
        self.assertEqual(result["observations"], 52)
        self.assertIn("Fon kataloğu güncellenemedi", result["message"])

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
