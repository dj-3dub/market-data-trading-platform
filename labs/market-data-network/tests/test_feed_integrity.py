import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from feed_integrity import FeedIntegrityTracker


class FeedIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tracker = FeedIntegrityTracker()

    def tick(self, session, sequence):
        return {
            "session_id": session,
            "symbol": "FAKE",
            "sequence": sequence,
        }

    def test_sequence_gap_and_recovery(self):
        t = self.tracker

        self.assertEqual(t.process(self.tick("session-a", 1)), "NEW_SESSION")
        self.assertEqual(t.process(self.tick("session-a", 2)), "OK")
        self.assertEqual(t.process(self.tick("session-a", 4)), "GAP")
        self.assertEqual(t.unresolved_gaps("session-a", "FAKE"), [3])

        self.assertEqual(t.process(self.tick("session-a", 3)), "GAP_RECOVERED")
        self.assertEqual(t.unresolved_gaps("session-a", "FAKE"), [])

    def test_duplicate(self):
        tick = self.tick("session-a", 1)
        self.assertEqual(self.tracker.process(tick), "NEW_SESSION")
        self.assertEqual(self.tracker.process(tick), "DUPLICATE")

    def test_new_sender_session(self):
        self.assertEqual(
            self.tracker.process(self.tick("session-a", 10)),
            "NEW_SESSION",
        )
        self.assertEqual(
            self.tracker.process(self.tick("session-b", 1)),
            "NEW_SESSION",
        )

    def test_out_of_order(self):
        t = self.tracker
        t.process(self.tick("session-a", 3))
        t.process(self.tick("session-a", 4))
        self.assertEqual(t.process(self.tick("session-a", 2)), "OUT_OF_ORDER")


if __name__ == "__main__":
    unittest.main()

