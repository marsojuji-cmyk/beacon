"""Core path: a failed fetch never flips or deletes a program."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "reverify", ROOT / "scripts" / "reverify.py"
)
reverify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reverify)


class TransportFailure(unittest.TestCase):
    def test_keeps_status_and_identity(self):
        program = {
            "id": "ab-innovation",
            "name": "Alberta Innovation",
            "status": "open",
            "tier": "VERIFIED",
            "source_url": "https://example.test/program",
        }
        downgraded, event = reverify.record_transport_failure(
            program, "URLError: timed out"
        )
        self.assertTrue(downgraded)
        self.assertEqual(program["id"], "ab-innovation")
        self.assertEqual(program["status"], "open")
        self.assertEqual(program["tier"], "INFERRED")
        self.assertEqual(event["old_status"], "open")
        self.assertEqual(event["new_status"], "open")
        self.assertIn("timed out", event["concern"])

    def test_inferred_stays_inferred(self):
        program = {"id": "x", "status": "paused", "tier": "INFERRED", "source_url": ""}
        downgraded, event = reverify.record_transport_failure(program, "URLError")
        self.assertFalse(downgraded)
        self.assertEqual(program["tier"], "INFERRED")
        self.assertEqual(event["new_status"], "paused")


class DetectStatus(unittest.TestCase):
    def test_server_error_does_not_change_status(self):
        status, note = reverify.detect_status(500, "closed", "open", "Alberta Innovation")
        self.assertIsNone(status)
        self.assertIn("no status change", note)

    def test_ok_without_keyword_keeps_current(self):
        status, note = reverify.detect_status(200, "welcome", "open", "Alberta Innovation")
        self.assertIsNone(status)
        self.assertIn("keep current", note)

    def test_gone_is_an_observed_close_not_a_silent_keep(self):
        status, note = reverify.detect_status(404, "", "open", "Alberta Innovation")
        self.assertEqual(status, "closed")
        self.assertEqual(note, "HTTP 404")

    def test_closed_keyword_near_the_program_name_flips(self):
        body = "CanExport is no longer accepting applications."
        status, note = reverify.detect_status(200, body, "open", "CanExport")
        self.assertEqual(status, "closed")
        self.assertEqual(note, "keyword:closed")


if __name__ == "__main__":
    unittest.main()
