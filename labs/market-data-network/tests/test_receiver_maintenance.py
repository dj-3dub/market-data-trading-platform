import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from feed_integrity import FeedIntegrityTracker
from feed_metrics import FeedMetrics
from feed_receiver import maintain_sessions


class ReceiverMaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.tracker = FeedIntegrityTracker()
        self.metrics = FeedMetrics()

    def tick(self, session, sequence):
        return {
            "session_id": session,
            "symbol": "FAKE",
            "sequence": sequence,
        }

    def test_expired_session_removed_from_tracker_and_metrics(self):
        t = self.tracker
        m = self.metrics

        t.process(self.tick("session-a", 1))
        m.set_session_gaps("session-a", "FAKE", 0)

        state = t.sessions[("session-a", "FAKE")]

        expired = maintain_sessions(
            t, m, now=state.last_activity + 901
        )

        self.assertEqual(expired, [("session-a", "FAKE")])
        self.assertNotIn(("session-a", "FAKE"), t.sessions)
        self.assertNotIn('session_id="session-a"', m.render())
        self.assertIn("feed_sessions_active 0", m.render())

    def test_unresolved_incident_survives_maintenance(self):
        t = self.tracker
        m = self.metrics

        t.process(self.tick("session-a", 1))
        t.process(self.tick("session-a", 3))

        m.record("GAP", 1)
        m.set_session_gaps("session-a", "FAKE", 1)

        state = t.sessions[("session-a", "FAKE")]

        expired = maintain_sessions(
            t, m, now=state.last_activity + 3600
        )

        self.assertEqual(expired, [])
        self.assertIn(("session-a", "FAKE"), t.sessions)
        self.assertIn('session_id="session-a"', m.render())
        self.assertIn("feed_unresolved_gaps 1", m.render())
        self.assertIn("feed_sessions_active 1", m.render())

    def test_only_resolved_session_expires(self):
        t = self.tracker
        m = self.metrics

        t.process(self.tick("resolved", 1))
        t.process(self.tick("unresolved", 1))
        t.process(self.tick("unresolved", 3))

        m.set_session_gaps("resolved", "FAKE", 0)
        m.set_session_gaps("unresolved", "FAKE", 1)

        now = max(
            state.last_activity for state in t.sessions.values()
        ) + 901

        expired = maintain_sessions(t, m, now=now)

        self.assertEqual(expired, [("resolved", "FAKE")])
        self.assertIn(("unresolved", "FAKE"), t.sessions)
        self.assertNotIn('session_id="resolved"', m.render())
        self.assertIn('session_id="unresolved"', m.render())
        self.assertIn("feed_sessions_active 1", m.render())


if __name__ == "__main__":
    unittest.main()
