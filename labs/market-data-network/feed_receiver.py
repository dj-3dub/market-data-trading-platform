#!/usr/bin/env python3
"""UDP multicast market-data receiver with validated stale-feed recovery."""
import json
import math
import socket
import time

from feed_integrity import FeedIntegrityTracker
from feed_metrics import FeedMetrics, start_metrics_server

GROUP = "239.192.0.10"
PORT = 50010
INTERFACE = "127.0.0.1"
STALE_SECONDS = 2.0


def validate_tick(tick):
    """Validate fields used by the feed integrity tracker before processing."""
    if not isinstance(tick, dict):
        raise ValueError("tick must be a JSON object")
    for key in ("session_id", "symbol"):
        if not isinstance(tick.get(key), str) or not tick[key].strip():
            raise ValueError(f"{key} must be a non-empty string")
    sequence = tick.get("sequence")
    if type(sequence) is not int or sequence < 1:
        raise ValueError("sequence must be a positive integer")
    for key in ("price", "timestamp"):
        value = tick.get(key)
        if type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError(f"{key} must be a finite number")
    if tick["price"] < 0:
        raise ValueError("price cannot be negative")
    return tick



SESSION_TTL_SECONDS = 900
MAINTENANCE_INTERVAL_SECONDS = 30


def maintain_sessions(tracker, metrics, now=None):
    """Expire resolved idle sessions and synchronize exporter metrics."""
    expired = tracker.cleanup_expired(
        ttl_seconds=SESSION_TTL_SECONDS,
        now=now,
    )

    metrics.remove_sessions(expired)
    metrics.set_active_sessions(len(tracker.sessions))

    return expired


def main():
    tracker = FeedIntegrityTracker()
    metrics = FeedMetrics()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    metrics_server = None
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", PORT))
        membership = socket.inet_aton(GROUP) + socket.inet_aton(INTERFACE)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
        sock.settimeout(0.5)

        metrics_server = start_metrics_server(metrics, host="0.0.0.0", port=9108)
        last_received = time.monotonic()
        stale = False
        seen_packet = False
        last_maintenance = time.monotonic()

        print(f"Listening on {GROUP}:{PORT} via {INTERFACE}", flush=True)
        print("Metrics endpoint: http://127.0.0.1:9108/metrics", flush=True)

        while True:
            now = time.monotonic()

            if now - last_maintenance >= MAINTENANCE_INTERVAL_SECONDS:
                expired = maintain_sessions(tracker, metrics, now=now)
                last_maintenance = now

                if expired:
                    print(
                        f"MAINTENANCE: expired={len(expired)} "
                        f"active={len(tracker.sessions)}",
                        flush=True,
                    )

            try:
                payload, address = sock.recvfrom(65535)
            except socket.timeout:
                if (seen_packet and not stale and
                        time.monotonic() - last_received >= STALE_SECONDS):
                    stale = True
                    metrics.set_stale(True)
                    print(f"STALE: No valid packets received for {STALE_SECONDS:g} seconds", flush=True)
                continue

            try:
                tick = validate_tick(json.loads(payload))
                status = tracker.process(tick)
                session = tick["session_id"]
                symbol = tick["symbol"]
                sequence = tick["sequence"]
                gaps = tracker.unresolved_gaps(session, symbol)
                total_unresolved = sum(
                    len(state.missing) for state in tracker.sessions.values()
                )
                metrics.record(status, total_unresolved)
                metrics.set_session_gaps(session, symbol, len(gaps))
                metrics.set_active_sessions(len(tracker.sessions))
            except (ValueError, KeyError, TypeError, UnicodeDecodeError, OverflowError) as exc:
                metrics.invalid()
                print(f"INVALID: {exc}", flush=True)
                continue

            # Only successfully validated and processed ticks refresh feed health.
            last_received = time.monotonic()
            seen_packet = True
            if stale:
                stale = False
                metrics.set_stale(False)
                print("RECOVERED: Feed traffic resumed", flush=True)

            print(
                f"{status:16} session={session[:8]} symbol={symbol} "
                f"seq={sequence} unresolved={gaps} "
                f"source={address[0]}:{address[1]}",
                flush=True,
            )
    except KeyboardInterrupt:
        print("\nReceiver stopped", flush=True)
    finally:
        sock.close()
        if metrics_server is not None:
            metrics_server.shutdown()
            metrics_server.server_close()


if __name__ == "__main__":
    main()
