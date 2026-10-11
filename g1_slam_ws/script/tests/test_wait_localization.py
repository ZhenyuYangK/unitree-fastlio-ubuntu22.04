"""Offline checks for the readiness decision; no ROS or hardware required."""

import importlib.util
from pathlib import Path
import unittest


HELPER = Path(__file__).resolve().parents[1] / "g1_wait_localization.py"
spec = importlib.util.spec_from_file_location("g1_wait_localization", HELPER)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class LocalizationReadinessTest(unittest.TestCase):
    def setUp(self):
        self.now = 10_000_000_000
        self.status = {
            "state": "TRACKING",
            "valid": True,
            "stamp_ns": self.now - 100_000_000,
            "last_success_stamp_ns": self.now - 500_000_000,
            "reason": "tracking",
        }

    def ready(self):
        return helper.assess_status(self.status, self.now)[0]

    def test_current_localized_and_tracking_are_ready(self):
        for state in ("TRACKING", "LOCALIZED"):
            self.status["state"] = state
            self.assertTrue(self.ready())

    def test_only_explicit_valid_success_is_ready(self):
        for state in ("WAITING_DATA", "VERIFYING", "AMBIGUOUS", "FAILED", "LOST"):
            self.status["state"] = state
            self.assertFalse(self.ready())
        self.status["state"] = "TRACKING"
        for valid in (False, "true", 1, None):
            self.status["valid"] = valid
            self.assertFalse(self.ready())

    def test_live_publication_cannot_hide_stale_success_scan(self):
        self.status["last_success_stamp_ns"] = self.now - 3_000_000_001
        self.assertFalse(self.ready())

    def test_stale_publication_is_rejected(self):
        self.status["stamp_ns"] = self.now - 1_000_000_001
        self.assertFalse(self.ready())

    def test_future_and_malformed_timestamps_are_rejected(self):
        for field in ("stamp_ns", "last_success_stamp_ns"):
            original = self.status[field]
            for stamp in (self.now + 1, True, "10000000000", 0, None, 1.0):
                self.status[field] = stamp
                self.assertFalse(self.ready(), (field, stamp))
            self.status[field] = original

    def test_non_object_is_rejected(self):
        for status in ([], None, "TRACKING", 1):
            self.assertFalse(helper.assess_status(status, self.now)[0])

    def test_malformed_state_and_clock_are_rejected(self):
        for state in ([], {}, True, 1, None):
            self.status["state"] = state
            self.assertFalse(self.ready())
        self.status["state"] = "TRACKING"
        for now in (0, -1, True, None, "10000000000", 1.0):
            self.assertFalse(helper.assess_status(self.status, now)[0])

    def test_success_cannot_be_later_than_status_publication(self):
        self.status["last_success_stamp_ns"] = self.now - 50_000_000
        self.assertFalse(self.ready())


if __name__ == "__main__":
    unittest.main()
