#!/usr/bin/env python3
import json
import socket
import time

GROUP = "239.192.0.10"
PORT = 50010
INTERFACE = "127.0.0.1"

sequence_plan = [1, 2, 3, 4, 6, 7, 7, 8, 6, 9, 10]

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
sock.setsockopt(
    socket.IPPROTO_IP,
    socket.IP_MULTICAST_IF,
    socket.inet_aton(INTERFACE),
)

try:
    for sequence in sequence_plan:
        tick = {
            "symbol": "FAKE",
            "sequence": sequence,
            "price": round(100 + sequence * 0.05, 2),
            "timestamp": time.time(),
        }

        payload = json.dumps(tick).encode("utf-8")
        sock.sendto(payload, (GROUP, PORT))

        print(f"SENT symbol=FAKE seq={sequence}", flush=True)
        time.sleep(0.5)
finally:
    sock.close()
