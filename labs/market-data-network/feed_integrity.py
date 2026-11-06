#!/usr/bin/env python3
"""Bounded market-data sequence integrity tracking."""

import time
from dataclasses import dataclass, field


SEQUENCE_WINDOW_SIZE = 4096
MAX_MISSING_RANGES = 1024
MAX_GAP_REPORT = 256


class MissingRanges:
    """Store missing sequence numbers as compact, disjoint intervals."""

    def __init__(self):
        self.ranges = []
        self.count = 0

    def __len__(self):
        return self.count

    def __bool__(self):
        return self.count > 0

    def __contains__(self, sequence):
        return any(
            start <= sequence <= end
            for start, end in self.ranges
        )

    def add_range(self, start, end):
        """Add an inclusive interval of missing sequences."""
        if start > end:
            return

        merged = []
        inserted = False

        for left, right in self.ranges:
            if right + 1 < start:
                merged.append((left, right))
            elif end + 1 < left:
                if not inserted:
                    merged.append((start, end))
                    inserted = True
                merged.append((left, right))
            else:
                start = min(start, left)
                end = max(end, right)

        if not inserted:
            merged.append((start, end))

        if len(merged) > MAX_MISSING_RANGES:
            raise ValueError("Missing-range capacity exceeded")

        self.ranges = merged
        self.count = sum(
            right - left + 1
            for left, right in merged
        )

    def remove(self, sequence):
        """Recover one missing sequence, splitting ranges if needed."""
        for index, (start, end) in enumerate(self.ranges):
            if not start <= sequence <= end:
                continue

            replacement = []

            if start < sequence:
                replacement.append((start, sequence - 1))

            if sequence < end:
                replacement.append((sequence + 1, end))

            if len(self.ranges) - 1 + len(replacement) > MAX_MISSING_RANGES:
                raise ValueError("Missing-range capacity exceeded")

            self.ranges[index:index + 1] = replacement
            self.count -= 1
            return

        raise KeyError(sequence)

    def report(self, limit=MAX_GAP_REPORT):
        """Return a bounded list of individual missing sequences."""
        result = []

        for start, end in self.ranges:
            remaining = limit - len(result)

            if remaining <= 0:
                break

            result.extend(
                range(start, min(end + 1, start + remaining))
            )

        return result


@dataclass
class SessionState:
    highest: int = 0
    received: set[int] = field(default_factory=set)
    missing: MissingRanges = field(default_factory=MissingRanges)
    last_activity: float = field(default_factory=time.monotonic)


class FeedIntegrityTracker:
    def __init__(self):
        self.sessions = {}

    def _prune_received(self, state):
        """Evict old sequences without scanning a large gap."""
        lower_bound = max(
            1,
            state.highest - SEQUENCE_WINDOW_SIZE + 1,
        )

        previous = getattr(state, "_pruned_through", 0)

        # A large jump can invalidate the entire history.
        # Clear it in one operation instead of iterating
        # through potentially billions of sequence numbers.
        if lower_bound - previous > SEQUENCE_WINDOW_SIZE:
            state.received.intersection_update(
                sequence for sequence in state.received
                if sequence >= lower_bound
            )
        else:
            for sequence in range(previous + 1, lower_bound):
                state.received.discard(sequence)

        state._pruned_through = lower_bound - 1

    def process(self, tick):
        """Process a tick and return its integrity status."""
        session = tick["session_id"]
        symbol = tick["symbol"]
        sequence = tick["sequence"]

        if (
            not isinstance(session, str)
            or not session
            or not isinstance(symbol, str)
            or not symbol
            or type(sequence) is not int
            or sequence < 1
        ):
            raise ValueError("Invalid feed identity or sequence")

        key = (session, symbol)
        state = self.sessions.get(key)

        if state is None:
            state = SessionState(
                highest=sequence,
                received={sequence},
            )
            self.sessions[key] = state
            return "NEW_SESSION"

        state.last_activity = time.monotonic()

        if sequence in state.received:
            return "DUPLICATE"

        if sequence > state.highest:
            if sequence > state.highest + 1:
                state.missing.add_range(
                    state.highest + 1,
                    sequence - 1,
                )
                status = "GAP"
            else:
                status = "OK"

            state.highest = sequence
            state.received.add(sequence)
            self._prune_received(state)
            return status

        if sequence in state.missing:
            state.missing.remove(sequence)

            lower_bound = max(
                1,
                state.highest - SEQUENCE_WINDOW_SIZE + 1,
            )

            if sequence >= lower_bound:
                state.received.add(sequence)

            return "GAP_RECOVERED"

        lower_bound = max(
            1,
            state.highest - SEQUENCE_WINDOW_SIZE + 1,
        )

        if sequence < lower_bound:
            return "OUT_OF_WINDOW"

        state.received.add(sequence)
        return "OUT_OF_ORDER"

    def unresolved_gaps(self, session, symbol):
        """Return a bounded list of missing sequence numbers."""
        state = self.sessions.get((session, symbol))

        if state is None:
            return []

        return state.missing.report()

    def unresolved_gap_count(self, session, symbol):
        """Return the exact number of unresolved missing packets."""
        state = self.sessions.get((session, symbol))
        return len(state.missing) if state else 0

    def unresolved_gap_ranges(self, session, symbol):
        """Return compact missing-sequence intervals."""
        state = self.sessions.get((session, symbol))
        return list(state.missing.ranges) if state else []

    def cleanup_expired(self, ttl_seconds=900, now=None):
        """Expire idle sessions without unresolved gaps."""
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")

        if now is None:
            now = time.monotonic()

        expired = []

        for key, state in list(self.sessions.items()):
            if (
                now - state.last_activity >= ttl_seconds
                and not state.missing
            ):
                expired.append(key)
                del self.sessions[key]

        return expired
