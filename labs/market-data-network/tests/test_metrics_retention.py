import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from feed_metrics import FeedMetrics


class MetricsRetentionTests(unittest.TestCase):
    def setUp(self):
        self.metrics = FeedMetrics()

    def test_expired_session_metric_removed(self):
        m = self.metrics

        m.set_session_gaps("session-a", "FAKE", 0)
        m.set_session_gaps("session-b", "FAKE", 1)

        m.remove_sessions([("session-a", "FAKE")])

        output = m.render()

        self.assertNotIn(
            'session_id="session-a"',
            output,
        )
        self.assertIn(
            'session_id="session-b"',
            output,
        )

    def test_global_metrics_preserved(self):
        m = self.metrics

        m.record("GAP", 1)
        m.set_session_gaps("session-a", "FAKE", 1)

        m.remove_sessions([("session-a", "FAKE")])

        output = m.render()

        self.assertIn("feed_unresolved_gaps 1", output)
        self.assertIn("feed_sequence_gaps_total 1", output)

    def test_active_session_gauge(self):
        m = self.metrics

        m.set_active_sessions(3)

        self.assertIn(
            "feed_sessions_active 3",
            m.render(),
        )

    def test_remove_nonexistent_session(self):
        m = self.metrics

        m.remove_sessions([("missing", "FAKE")])

        self.assertIn(
            "feed_unresolved_gaps 0",
            m.render(),
        )


if __name__ == "__main__":
    unittest.main()
