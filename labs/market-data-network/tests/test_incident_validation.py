import importlib.util
import pathlib
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "incident-validation.py"

spec = importlib.util.spec_from_file_location(
    "incident_validation", SCRIPT
)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class IncidentValidationTests(unittest.TestCase):

    def test_session_query_uses_correct_labels(self):
        with patch.object(
            validator, "prom_query", return_value=1.0
        ) as mock_query:
            result = validator.session_gap_query(
                "http://localhost:9090",
                "session-123",
                "FAKE",
            )

        self.assertEqual(result, 1.0)
        mock_query.assert_called_once_with(
            "http://localhost:9090",
            'feed_session_unresolved_gaps'
            '{job="market-data-network",'
            'session_id="session-123",symbol="FAKE"}',
        )

    def test_missing_session_metric_returns_none(self):
        with patch.object(
            validator, "prom_query", return_value=None
        ):
            self.assertIsNone(
                validator.session_gap_query(
                    "http://localhost:9090", "unknown-session"
                )
            )

    def test_session_labels_are_escaped(self):
        with patch.object(
            validator, "prom_query", return_value=0.0
        ) as mock_query:
            validator.session_gap_query(
                "http://localhost:9090",
                'session-"test"',
            )

        query = mock_query.call_args.args[1]
        self.assertIn('session_id="session-\\"test\\""', query)


if __name__ == "__main__":
    unittest.main()
