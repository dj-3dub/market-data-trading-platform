import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from feed_metrics import FeedMetrics


class FeedMetricsTests(unittest.TestCase):

    def test_global_gaps_preserved_across_sessions(self):
        metrics = FeedMetrics()

        metrics.record("GAP", 1)
        metrics.set_session_gaps("session-a", "FAKE", 1)

        metrics.record("NEW_SESSION", 1)
        metrics.set_session_gaps("session-b", "FAKE", 0)

        output = metrics.render()

        self.assertIn("feed_unresolved_gaps 1\n", output)
        self.assertIn(
            'feed_session_unresolved_gaps'
            '{session_id="session-a",symbol="FAKE"} 1\n',
            output,
        )
        self.assertIn(
            'feed_session_unresolved_gaps'
            '{session_id="session-b",symbol="FAKE"} 0\n',
            output,
        )

    def test_session_gap_recovery(self):
        metrics = FeedMetrics()

        metrics.set_session_gaps("session-a", "FAKE", 1)
        metrics.set_session_gaps("session-a", "FAKE", 0)

        self.assertIn(
            'feed_session_unresolved_gaps'
            '{session_id="session-a",symbol="FAKE"} 0\n',
            metrics.render(),
        )

    def test_existing_counters_preserved(self):
        metrics = FeedMetrics()

        metrics.record("NEW_SESSION", 0)
        metrics.record("GAP", 1)
        metrics.record("GAP_RECOVERED", 0)

        output = metrics.render()

        self.assertIn("feed_packets_received_total 3\n", output)
        self.assertIn("feed_sessions_total 1\n", output)
        self.assertIn("feed_sequence_gaps_total 1\n", output)
        self.assertIn("feed_gap_recoveries_total 1\n", output)


if __name__ == "__main__":
    unittest.main()
