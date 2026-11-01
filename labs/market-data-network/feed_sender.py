#!/usr/bin/env python3
"""UDP multicast market-data sender with failure injection and replay."""

import argparse
import json
import math
import socket
import time
import uuid

GROUP = "239.192.0.10"
PORT = 50010
INTERFACE = "127.0.0.1"

SEQUENCE_PLAN = [1, 2, 3, 4, 6, 7, 7, 8, 6, 9, 10, 5]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--continuous", action="store_true")
    parser.add_argument("--replay", action="store_true")
    parser.add_argument("--rate", type=float, default=100.0)
    parser.add_argument("--duration", type=float)
    parser.add_argument("--symbol", default="FAKE")
    parser.add_argument("--session-id")
    parser.add_argument("--sequence", type=int)
    parser.add_argument("--drop-sequence", type=int)
    parser.add_argument("--duplicate-sequence", type=int)
    parser.add_argument("--reorder-sequence", type=int)
    parser.add_argument("--pause-after", type=int)
    parser.add_argument("--pause-seconds", type=float)

    args = parser.parse_args()

    if not args.symbol.strip():
        parser.error("--symbol cannot be empty")

    if args.replay:
        if args.continuous:
            parser.error("--replay and --continuous are mutually exclusive")
        if not args.session_id or not args.session_id.strip():
            parser.error("--replay requires --session-id")
        if args.sequence is None or args.sequence < 1:
            parser.error("--replay requires a positive --sequence")
        if (
            args.duration is not None
            or args.drop_sequence is not None
            or args.duplicate_sequence is not None
            or args.reorder_sequence is not None
            or args.pause_after is not None
            or args.pause_seconds is not None
        ):
            parser.error("--replay cannot use continuous injection options")
        return args

    if args.session_id is not None or args.sequence is not None:
        parser.error("--session-id and --sequence require --replay")

    if not math.isfinite(args.rate) or not 0 < args.rate <= 10000:
        parser.error("--rate must be between 0 and 10000")

    if args.duration is not None:
        if not math.isfinite(args.duration) or args.duration <= 0:
            parser.error("--duration must be positive and finite")
        if not args.continuous:
            parser.error("--duration requires --continuous")

    injections = [
        args.drop_sequence,
        args.duplicate_sequence,
        args.reorder_sequence,
    ]

    if sum(value is not None for value in injections) > 1:
        parser.error("Choose only one sequence injection mode")

    if any(value is not None for value in injections):
        if not args.continuous or args.duration is None:
            parser.error("Sequence injection requires --continuous --duration")
        if any(value is not None and value < 1 for value in injections):
            parser.error("Injected sequence numbers must be positive")
        if math.ceil(args.duration * args.rate) < max(
            value for value in injections if value is not None
        ):
            parser.error("Duration is too short for the selected injection")

    if (args.pause_after is None) != (args.pause_seconds is None):
        parser.error("--pause-after and --pause-seconds must be used together")

    if args.pause_after is not None:
        if not args.continuous or args.duration is None:
            parser.error("Pause injection requires --continuous --duration")
        if args.pause_after < 1:
            parser.error("--pause-after must be positive")
        if not math.isfinite(args.pause_seconds) or args.pause_seconds <= 0:
            parser.error("--pause-seconds must be positive and finite")
        if args.pause_after / args.rate + args.pause_seconds >= args.duration:
            parser.error("Duration must allow traffic after the pause")

    return args


def create_socket():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
    sock.setsockopt(
        socket.IPPROTO_IP,
        socket.IP_MULTICAST_IF,
        socket.inet_aton(INTERFACE),
    )
    return sock


def send_tick(sock, session_id, symbol, sequence):
    tick = {
        "session_id": session_id,
        "symbol": symbol,
        "sequence": sequence,
        "price": round(100 + sequence * 0.05, 2),
        "timestamp": time.time(),
    }
    sock.sendto(json.dumps(tick).encode("utf-8"), (GROUP, PORT))
    return tick


def run_deterministic(sock, session_id, symbol):
    print(f"SESSION_ID={session_id}", flush=True)
    for sequence in SEQUENCE_PLAN:
        send_tick(sock, session_id, symbol, sequence)
        print(f"SENT seq={sequence}", flush=True)
        time.sleep(0.5)


def run_replay(sock, session_id, symbol, sequence):
    send_tick(sock, session_id, symbol, sequence)
    print(
        f"REPLAY_SENT session_id={session_id} "
        f"symbol={symbol} seq={sequence}",
        flush=True,
    )


def run_continuous(sock, session_id, args):
    interval = 1.0 / args.rate
    start = time.monotonic()
    deadline = start + args.duration if args.duration is not None else None
    next_send = start

    sequence = 1
    attempted = 0
    sent = 0
    dropped = 0
    duplicated = 0
    reordered = 0
    pending_reordered = None
    paused = False

    print(
        f"SESSION_ID={session_id} rate={args.rate} "
        f"duration={args.duration}",
        flush=True,
    )

    try:
        while True:
            now = time.monotonic()
            if deadline is not None and now >= deadline:
                break

            if now < next_send:
                time.sleep(min(next_send - now, 0.1))
                continue

            if (
                args.pause_after is not None
                and not paused
                and attempted >= args.pause_after
            ):
                paused = True
                print(
                    f"INJECTED_PAUSE after={attempted} "
                    f"seconds={args.pause_seconds}",
                    flush=True,
                )
                time.sleep(args.pause_seconds)
                print("INJECTED_RESUME", flush=True)
                next_send = time.monotonic()
                continue

            if sequence == args.drop_sequence:
                dropped += 1
                print(f"INJECTED_DROP seq={sequence}", flush=True)

            elif sequence == args.duplicate_sequence:
                send_tick(sock, session_id, args.symbol, sequence)
                send_tick(sock, session_id, args.symbol, sequence)
                sent += 2
                duplicated += 1
                print(f"INJECTED_DUPLICATE seq={sequence}", flush=True)

            elif sequence == args.reorder_sequence:
                send_tick(sock, session_id, args.symbol, sequence + 1)
                sent += 1
                pending_reordered = sequence
                reordered += 1
                print(
                    f"INJECTED_REORDER early_seq={sequence + 1}",
                    flush=True,
                )

            elif pending_reordered is not None:
                send_tick(sock, session_id, args.symbol, pending_reordered)
                sent += 1
                print(
                    f"INJECTED_REORDER late_seq={pending_reordered}",
                    flush=True,
                )
                pending_reordered = None

            else:
                send_tick(sock, session_id, args.symbol, sequence)
                sent += 1

            attempted += 1
            sequence += 1
            next_send += interval

            if next_send < time.monotonic():
                next_send = time.monotonic() + interval

            if attempted % max(1, int(args.rate)) == 0:
                print(
                    f"PROGRESS attempted={attempted} sent={sent}",
                    flush=True,
                )

    except KeyboardInterrupt:
        print("Sender interrupted", flush=True)

    elapsed = time.monotonic() - start
    print(
        f"SUMMARY session_id={session_id} "
        f"attempted={attempted} sent={sent} "
        f"dropped={dropped} duplicated={duplicated} "
        f"reordered={reordered} "
        f"elapsed={elapsed:.2f}s "
        f"avg_tx_rate={sent / elapsed if elapsed else 0:.2f}",
        flush=True,
    )


def main():
    args = parse_args()
    session_id = args.session_id if args.replay else str(uuid.uuid4())

    sock = create_socket()
    try:
        if args.replay:
            run_replay(sock, session_id, args.symbol, args.sequence)
        elif args.continuous:
            run_continuous(sock, session_id, args)
        else:
            run_deterministic(sock, session_id, args.symbol)
    finally:
        sock.close()


if __name__ == "__main__":
    main()
