#!/usr/bin/env python3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread


class FeedMetrics:
    def __init__(self):
        self.lock = Lock()

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

    def invalid(self):
        with self.lock:
            self.counters["feed_invalid_packets_total"] += 1

    def set_stale(self, stale):
        with self.lock:
            self.gauges["feed_stale"] = int(stale)

    def render(self):
        with self.lock:
            values = {**self.counters, **self.gauges}

        return "".join(
            f"# TYPE {name} {'counter' if name.endswith('_total') else 'gauge'}\n"
            f"{name} {value}\n"
            for name, value in values.items()
        )


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
