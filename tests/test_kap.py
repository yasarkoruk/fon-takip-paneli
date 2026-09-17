import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.fetch_kap import body_text, collect, merge_records, needs_review, normalize, rapid_needed, request_json
from scripts.common import read_json, write_json_atomic


def listed(index=10, code="THF", related=None):
    return {"disclosureBasic": {"disclosureIndex": index, "publishDate": "16.09.2026 20:35:10",
                               "stockCode": code, "relatedStocks": related, "title": "Genel Açıklama",
                               "summary": "İade ödemeleri", "companyTitle": "THF"}}


class KapTests(unittest.TestCase):
    def test_runtime_budget_stops_before_a_new_network_request(self):
        with patch("scripts.fetch_kap.time.monotonic", return_value=10), patch("scripts.fetch_kap.urllib.request.urlopen") as request:
            with self.assertRaises(RuntimeError):
                request_json("api/test", {"max_retries":3,"_deadline":9})
            request.assert_not_called()

    def test_adaptive_control_activates_for_incident_or_failure(self):
        self.assertTrue(rapid_needed({}))
        self.assertTrue(rapid_needed({"status": {"state": "error"}}))
        self.assertTrue(rapid_needed({"status": {"state": "ok"}, "reviewed_events": [{"disclosure_id":10,"state":"active"}]}))
        self.assertFalse(rapid_needed({"status": {"state": "ok"}}))

    def test_resolved_reviewed_candidate_does_not_keep_rapid_mode(self):
        archive = {"status": {"state": "ok"}, "funds": {"THF": [{"id":10,"candidate":True}]},
                   "reviewed_events": [{"disclosure_id":10,"state":"resolved"}]}
        self.assertFalse(rapid_needed(archive))
        archive["funds"]["THF"].append({"id":11,"candidate":True})
        self.assertTrue(rapid_needed(archive))

    def test_official_body_excludes_editor_and_unescapes_text(self):
        html = '<div class="note-editor">Hidden controls</div><div class="text-block-value"><p>İade &amp; likidite</p></div>'
        self.assertEqual(body_text([html]), "İade & likidite")

    def test_scope_requires_exact_code_not_substring(self):
        self.assertEqual(normalize(listed(), "THF")["scope"], "Fon")
        self.assertEqual(normalize(listed(code="SKP", related="THF, TMV"), "THF")["scope"], "İlişkili bildirim")
        with self.assertRaises(ValueError):
            normalize(listed(code="XTHF"), "THF")

    def test_merge_deduplicates_without_erasing_detail(self):
        old = normalize(listed(), "THF")
        old.update(body="Preserved official text", candidate=True, detail_checked_at="checked")
        result = merge_records([old], [normalize(listed(), "THF")]*2)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["body"], old["body"])
        self.assertTrue(result[0]["candidate"])

    def test_keywords_only_create_review_candidates(self):
        self.assertTrue(needs_review("Temerrüt oluşmamıştır"))
        # Negated statements remain review candidates, never automatic default verdicts.
        self.assertFalse(needs_review("Portföy dağılım raporu"))

    def test_failure_preserves_archive_event_and_success_time(self):
        config = {"sources": [{"code": "THF", "member_oid": "test"}], "lookback_days": 365,
                  "max_details_per_run": 20, "reviewed_events": []}
        old = normalize(listed(), "THF")
        old["detail_checked_at"] = "checked"
        with TemporaryDirectory() as directory, patch("scripts.fetch_kap.ARCHIVE", Path(directory)/"archive.json"):
            path = Path(directory)/"archive.json"
            write_json_atomic(path, {"funds": {"THF": [old]}, "reviewed_events": [{"disclosure_id": 10, "state": "active"}],
                                     "status": {"state": "ok", "last_success_at": "previous"}})
            with patch("scripts.fetch_kap.request_json", side_effect=RuntimeError("timeout")):
                result = collect(config)
            self.assertEqual(result["funds"]["THF"], [old])
            self.assertEqual(result["reviewed_events"][0]["state"], "active")
            self.assertEqual(result["status"]["last_success_at"], "previous")
            self.assertEqual(result["status"]["state"], "error")
            self.assertIn("timeout", result["status"]["errors"][0])

    def test_empty_success_is_not_event_resolution(self):
        config = {"sources": [{"code": "THF", "member_oid": "test"}], "lookback_days": 365,
                  "max_details_per_run": 20, "reviewed_events": []}
        with TemporaryDirectory() as directory, patch("scripts.fetch_kap.ARCHIVE", Path(directory)/"archive.json"):
            write_json_atomic(Path(directory)/"archive.json", {"funds": {"THF": []},
                               "reviewed_events": [{"disclosure_id": 10, "state": "active"}], "status": {}})
            with patch("scripts.fetch_kap.request_json", return_value=[]):
                result = collect(config)
            self.assertEqual(result["status"]["state"], "ok")
            self.assertEqual(result["reviewed_events"][0]["state"], "active")

    def test_pending_detail_recovers_next_run(self):
        config = {"sources": [{"code": "THF", "member_oid": "test"}], "lookback_days": 365,
                  "max_details_per_run": 20, "reviewed_events": []}
        with TemporaryDirectory() as directory, patch("scripts.fetch_kap.ARCHIVE", Path(directory)/"archive.json"):
            with patch("scripts.fetch_kap.request_json", return_value=[listed()]), patch("scripts.fetch_kap.fetch_detail", side_effect=RuntimeError("timeout")):
                first = collect(config)
            self.assertIsNone(first["funds"]["THF"][0]["detail_checked_at"])
            with patch("scripts.fetch_kap.request_json", return_value=[listed()]), patch("scripts.fetch_kap.fetch_detail", return_value=("İade ödemelerinde temerrüt", {})):
                second = collect(config)
            self.assertEqual(second["status"]["state"], "ok")
            self.assertTrue(second["funds"]["THF"][0]["candidate"])

    def test_resolution_requires_official_source(self):
        config = {"sources": [], "reviewed_events": [{"code": "THF", "disclosure_id": 10, "state": "resolved"}]}
        with TemporaryDirectory() as directory, patch("scripts.fetch_kap.ARCHIVE", Path(directory)/"archive.json"), patch("scripts.fetch_kap.fetch_detail", return_value=("temerrüt", {"stockCode":"THF"})):
            result = collect(config)
            self.assertEqual(result["status"]["state"], "error")
            self.assertEqual(result["reviewed_events"], [])
