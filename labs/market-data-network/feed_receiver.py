#!/usr/bin/env python3
import json
import socket
import time

from feed_integrity import FeedIntegrityTracker

GROUP = "239.192.0.10"
PORT = 50010
INTERFACE = "127.0.0.1"
STALE_SECONDS = 2.0

tracker = FeedIntegrityTracker()

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("", PORT))

membership = socket.inet_aton(GROUP) + socket.inet_aton(INTERFACE)
sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
sock.settimeout(0.5)

last_received = time.monotonic()
stale = False
seen_packet = False

print(f"Listening on {GROUP}:{PORT} via {INTERFACE}", flush=True)

try:
    while True:
        try:
            payload, address = sock.recvfrom(65535)
        except socket.timeout:
            if (
                seen_packet
                and not stale
                and time.monotonic() - last_received >= STALE_SECONDS
            ):
                stale = True
                print("STALE: No packets received for 2 seconds", flush=True)
            continue

        last_received = time.monotonic()

        if stale:
            stale = False
            print("RECOVERED: Feed traffic resumed", flush=True)

        seen_packet = True

        try:
            tick = json.loads(payload)
            status = tracker.process(tick)

            session = tick["session_id"]
            symbol = tick["symbol"]
            sequence = tick["sequence"]
            gaps = tracker.unresolved_gaps(session, symbol)

            print(
                f"{status:16} "
                f"session={session[:8]} "
                f"symbol={symbol} "
                f"seq={sequence} "
                f"unresolved={gaps} "
                f"source={address[0]}:{address[1]}",
                flush=True,
            )

        except (ValueError, KeyError, TypeError) as exc:
            print(f"INVALID: {exc}", flush=True)

except KeyboardInterrupt:
    print("\nReceiver stopped")
finally:
    sock.close()
