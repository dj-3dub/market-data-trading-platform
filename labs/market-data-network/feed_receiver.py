#!/usr/bin/env python3
import json
import socket
import struct
import time

GROUP = "239.192.0.10"
PORT = 50010
INTERFACE = "127.0.0.1"

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(("", PORT))

membership = socket.inet_aton(GROUP) + socket.inet_aton(INTERFACE)
sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membership)
sock.settimeout(2)

last_sequence = {}
last_received = time.monotonic()

print(f"Listening on {GROUP}:{PORT} via {INTERFACE}", flush=True)

try:
    while True:
        try:
            payload, address = sock.recvfrom(65535)
        except socket.timeout:
            if time.monotonic() - last_received >= 2:
                print("STALE: No multicast packets received for 2 seconds", flush=True)
                last_received = time.monotonic()
            continue

        last_received = time.monotonic()

        try:
            tick = json.loads(payload)
            symbol = tick["symbol"]
            sequence = tick["sequence"]

            if not isinstance(symbol, str) or type(sequence) is not int or sequence < 1:
                raise ValueError("Invalid symbol or sequence")

            previous = last_sequence.get(symbol)

            if previous is None:
                status = "INITIAL"
            elif sequence == previous:
                status = "DUPLICATE"
            elif sequence < previous:
                status = "OUT_OF_ORDER"
            elif sequence > previous + 1:
                status = f"GAP missing={previous + 1}-{sequence - 1}"
            else:
                status = "OK"

            if previous is None or sequence > previous:
                last_sequence[symbol] = sequence

            print(
                f"{status:24} symbol={symbol} seq={sequence} "
                f"source={address[0]}:{address[1]}",
                flush=True,
            )

        except (ValueError, KeyError, TypeError) as exc:
            print(f"INVALID: {exc}", flush=True)

except KeyboardInterrupt:
    print("\nReceiver stopped")
finally:
    sock.close()
