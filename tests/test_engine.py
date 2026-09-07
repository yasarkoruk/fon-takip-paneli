import unittest

from scripts.analytics import build_metrics
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


if __name__ == "__main__":
    unittest.main()
