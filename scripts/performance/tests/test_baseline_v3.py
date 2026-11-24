import importlib.util
import unittest
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "baseline_v3.py"
)

spec = importlib.util.spec_from_file_location(
    "baseline_v3", SCRIPT
)
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)


class CounterTests(unittest.TestCase):

    def test_counter_delta(self):
        samples = [
            (100.0, 10.0),
            (105.0, 15.0),
            (110.0, 20.0),
        ]

        result = baseline.counter_result(
            samples, "test_counter", 5
        )

        self.assertEqual(result["delta"], 10)
        self.assertEqual(result["elapsed_seconds"], 10)
        self.assertEqual(result["rate_per_second"], 1.0)

    def test_counter_reset_rejected(self):
        samples = [
            (100.0, 100.0),
            (105.0, 105.0),
            (110.0, 2.0),
        ]

        with self.assertRaisesRegex(
            RuntimeError, "Counter reset"
        ):
            baseline.counter_result(
                samples, "test_counter", 5
            )

    def test_scrape_gap_rejected(self):
        samples = [
            (100.0, 10.0),
            (105.0, 15.0),
            (130.0, 20.0),
        ]

        with self.assertRaisesRegex(
            RuntimeError, "Scrape gap"
        ):
            baseline.counter_result(
                samples, "test_counter", 5
            )


class HistogramTests(unittest.TestCase):

    def test_histogram_quantile(self):
        buckets = {
            "0.005": 50,
            "0.010": 95,
            "0.025": 99,
            "+Inf": 100,
        }

        result = baseline.histogram_quantile(
            buckets, 0.95
        )

        self.assertAlmostEqual(result, 10.0)

    def test_unbounded_quantile(self):
        buckets = {
            "0.005": 10,
            "0.010": 20,
            "+Inf": 100,
        }

        result = baseline.histogram_quantile(
            buckets, 0.99
        )

        self.assertIsNone(result)


class LabelTests(unittest.TestCase):

    def test_metric_name_ignored(self):
        original = {
            "__name__": "strategy_ticks_total",
            "job": "strategy-engine",
            "instance": "strategy-engine:7002",
        }

        timestamp_labels = {
            "job": "strategy-engine",
            "instance": "strategy-engine:7002",
        }

        self.assertEqual(
            baseline.series_key(original),
            baseline.series_key(timestamp_labels),
        )


if __name__ == "__main__":
    unittest.main()
