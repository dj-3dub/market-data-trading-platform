import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from feed_integrity import FeedIntegrityTracker


class SessionRetentionTests(unittest.TestCase):
    def setUp(self):
        self.tracker = FeedIntegrityTracker()

    def tick(self, session, sequence):
        return {
            "session_id": session,
            "symbol": "FAKE",
            "sequence": sequence,
        }

    def test_expired_resolved_session_removed(self):
        t = self.tracker
        t.process(self.tick("session-a", 1))

        state = t.sessions[("session-a", "FAKE")]
        expired = t.cleanup_expired(now=state.last_activity + 901)

        self.assertEqual(expired, [("session-a", "FAKE")])
        self.assertNotIn(("session-a", "FAKE"), t.sessions)

    def test_active_session_preserved(self):
        t = self.tracker
        t.process(self.tick("session-a", 1))

        state = t.sessions[("session-a", "FAKE")]
        expired = t.cleanup_expired(now=state.last_activity + 100)

        self.assertEqual(expired, [])
        self.assertIn(("session-a", "FAKE"), t.sessions)

    def test_unresolved_gap_preserved(self):
        t = self.tracker
        t.process(self.tick("session-a", 1))
        t.process(self.tick("session-a", 3))

        state = t.sessions[("session-a", "FAKE")]
        expired = t.cleanup_expired(now=state.last_activity + 3600)

        self.assertEqual(expired, [])
        self.assertEqual(t.unresolved_gaps("session-a", "FAKE"), [2])

    def test_recovered_session_can_expire(self):
        t = self.tracker
        t.process(self.tick("session-a", 1))
        t.process(self.tick("session-a", 3))
        t.process(self.tick("session-a", 2))

        state = t.sessions[("session-a", "FAKE")]
        expired = t.cleanup_expired(now=state.last_activity + 901)

        self.assertEqual(expired, [("session-a", "FAKE")])

    def test_expired_session_restarts_as_new(self):
        t = self.tracker
        t.process(self.tick("session-a", 1))

        state = t.sessions[("session-a", "FAKE")]
        t.cleanup_expired(now=state.last_activity + 901)

        self.assertEqual(
            t.process(self.tick("session-a", 2)),
            "NEW_SESSION",
        )

    def test_ttl_boundary(self):
        t = self.tracker
        t.process(self.tick("session-a", 1))

        state = t.sessions[("session-a", "FAKE")]
        self.assertEqual(
            t.cleanup_expired(now=state.last_activity + 899),
            [],
        )
        self.assertEqual(
            t.cleanup_expired(now=state.last_activity + 900),
            [("session-a", "FAKE")],
        )


if __name__ == "__main__":
    unittest.main()
