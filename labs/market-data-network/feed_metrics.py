#!/usr/bin/env python3
"""Prometheus metrics for multicast market-data feed integrity."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread


class FeedMetrics:
    def __init__(self):
        self.lock = Lock()

        # Session-specific gap counts for isolated validation.
        self.session_gaps = {}

        self.counters = {
            "feed_packets_received_total": 0,
            "feed_sequence_gaps_total": 0,
            "feed_duplicates_total": 0,
            "feed_gap_recoveries_total": 0,
            "feed_invalid_packets_total": 0,
            "feed_sessions_total": 0,
        }

        self.gauges = {
            "feed_unresolved_gaps": 0,
            "feed_stale": 0,
            "feed_sessions_active": 0,
        }

    def record(self, status, unresolved):
        with self.lock:
            self.counters["feed_packets_received_total"] += 1

            if status == "GAP":
                self.counters["feed_sequence_gaps_total"] += 1
            elif status == "DUPLICATE":
                self.counters["feed_duplicates_total"] += 1
            elif status == "GAP_RECOVERED":
                self.counters["feed_gap_recoveries_total"] += 1
            elif status == "NEW_SESSION":
                self.counters["feed_sessions_total"] += 1

            self.gauges["feed_unresolved_gaps"] = unresolved

    def set_session_gaps(self, session_id, symbol, unresolved):
        """Update the unresolved-gap count for a specific feed session."""
        with self.lock:
            self.session_gaps[(session_id, symbol)] = unresolved

    def remove_sessions(self, expired):
        """Remove metrics for expired feed sessions."""
        with self.lock:
            for key in expired:
                self.session_gaps.pop(key, None)

    def set_active_sessions(self, count):
        """Publish the current number of tracked sessions."""
        with self.lock:
            self.gauges["feed_sessions_active"] = count

    def invalid(self):
        with self.lock:
            self.counters["feed_invalid_packets_total"] += 1

    def set_stale(self, stale):
        with self.lock:
            self.gauges["feed_stale"] = int(stale)

    def render(self):
        with self.lock:
            values = {**self.counters, **self.gauges}
            session_gaps = dict(self.session_gaps)

        lines = []

        for name, value in values.items():
            metric_type = (
                "counter" if name.endswith("_total") else "gauge"
            )
            lines.append(f"# TYPE {name} {metric_type}\n")
            lines.append(f"{name} {value}\n")

        if session_gaps:
            lines.append("# TYPE feed_session_unresolved_gaps gauge\n")

            for (session_id, symbol), unresolved in sorted(
                session_gaps.items()
            ):
                session_label = json.dumps(session_id)
                symbol_label = json.dumps(symbol)

                lines.append(
                    "feed_session_unresolved_gaps"
                    f"{{session_id={session_label},symbol={symbol_label}}} "
                    f"{unresolved}\n"
                )

        return "".join(lines)


def start_metrics_server(metrics, host="127.0.0.1", port=9108):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path != "/metrics":
                self.send_error(404)
                return

            body = metrics.render().encode("utf-8")
            self.send_response(200)
            self.send_header(
                "Content-Type",
                "text/plain; version=0.0.4; charset=utf-8",
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            pass

    server = ThreadingHTTPServer((host, port), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
