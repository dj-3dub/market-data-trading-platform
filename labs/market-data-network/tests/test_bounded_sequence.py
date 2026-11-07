
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from feed_integrity import (
    FeedIntegrityTracker,
    MAX_MISSING_RANGES,
    SEQUENCE_WINDOW_SIZE,
)


class BoundedSequenceTests(unittest.TestCase):

    def setUp(self):
        self.tracker = FeedIntegrityTracker()

    def tick(self, sequence, session="bounded-test"):
        return {
            "session_id": session,
            "symbol": "FAKE",
            "sequence": sequence,
        }

    def state(self):
        return self.tracker.sessions[("bounded-test", "FAKE")]

    def test_recent_history_is_bounded(self):
        for sequence in range(1, 10001):
            self.tracker.process(self.tick(sequence))

        self.assertLessEqual(
            len(self.state().received),
            SEQUENCE_WINDOW_SIZE,
        )

    def test_recent_duplicate_still_detected(self):
        for sequence in range(1, 5001):
            self.tracker.process(self.tick(sequence))

        self.assertEqual(
            self.tracker.process(self.tick(5000)),
            "DUPLICATE",
        )

    def test_old_packet_outside_window(self):
        for sequence in range(1, 5001):
            self.tracker.process(self.tick(sequence))

        self.assertEqual(
            self.tracker.process(self.tick(1)),
            "OUT_OF_WINDOW",
        )

    def test_gap_recovery_preserved(self):
        self.tracker.process(self.tick(1))
        self.tracker.process(self.tick(4))

        self.assertEqual(
            self.tracker.unresolved_gaps("bounded-test", "FAKE"),
            [2, 3],
        )

        self.assertEqual(
            self.tracker.process(self.tick(2)),
            "GAP_RECOVERED",
        )

        self.assertEqual(
            self.tracker.process(self.tick(3)),
            "GAP_RECOVERED",
        )

        self.assertEqual(
            self.tracker.unresolved_gap_count(
                "bounded-test", "FAKE"
            ),
            0,
        )

    def test_large_gap_uses_compact_range(self):
        self.tracker.process(self.tick(1))
        self.tracker.process(self.tick(1_000_000_000))

        self.assertEqual(
            self.tracker.unresolved_gap_count(
                "bounded-test", "FAKE"
            ),
            999_999_998,
        )

        self.assertEqual(
            self.tracker.unresolved_gap_ranges(
                "bounded-test", "FAKE"
            ),
            [(2, 999_999_999)],
        )

        self.assertEqual(len(self.state().missing.ranges), 1)

    def test_partial_interval_recovery(self):
        self.tracker.process(self.tick(1))
        self.tracker.process(self.tick(10))

        self.assertEqual(
            self.tracker.process(self.tick(5)),
            "GAP_RECOVERED",
        )

        self.assertEqual(
            self.tracker.unresolved_gap_ranges(
                "bounded-test", "FAKE"
            ),
            [(2, 4), (6, 9)],
        )

        self.assertEqual(
            self.tracker.unresolved_gap_count(
                "bounded-test", "FAKE"
            ),
            7,
        )

    def test_gap_report_is_bounded(self):
        self.tracker.process(self.tick(1))
        self.tracker.process(self.tick(100000))

        gaps = self.tracker.unresolved_gaps(
            "bounded-test", "FAKE"
        )

        self.assertLessEqual(len(gaps), 256)
        self.assertEqual(gaps[0], 2)

    def test_missing_range_capacity_is_enforced(self):
        self.tracker.process(self.tick(1))

        # Each jump leaves one isolated missing sequence.
        # This creates exactly MAX_MISSING_RANGES intervals.
        for sequence in range(3, 2 * MAX_MISSING_RANGES + 2, 2):
            self.tracker.process(self.tick(sequence))

        self.assertEqual(
            len(self.state().missing.ranges),
            MAX_MISSING_RANGES,
        )

        with self.assertRaisesRegex(
            ValueError, "Missing-range capacity exceeded"
        ):
            self.tracker.process(
                self.tick(2 * MAX_MISSING_RANGES + 3)
            )

        # A rejected update must not corrupt existing state.
        self.assertEqual(
            len(self.state().missing.ranges),
            MAX_MISSING_RANGES,
        )
        self.assertEqual(
            self.state().highest,
            2 * MAX_MISSING_RANGES + 1,
        )


if __name__ == "__main__":
    unittest.main()
