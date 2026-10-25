from dataclasses import dataclass, field


@dataclass
class SessionState:
    highest: int = 0
    received: set[int] = field(default_factory=set)
    missing: set[int] = field(default_factory=set)


class FeedIntegrityTracker:
    def __init__(self):
        self.sessions = {}

    def process(self, tick):
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
        new_session = key not in self.sessions
        state = self.sessions.setdefault(key, SessionState())

        if sequence in state.received:
            return "DUPLICATE"

        state.received.add(sequence)

        if new_session:
            state.highest = sequence
            return "NEW_SESSION"

        if sequence > state.highest + 1:
            state.missing.update(range(state.highest + 1, sequence))
            state.highest = sequence
            return "GAP"

        if sequence > state.highest:
            state.highest = sequence
            return "OK"

        if sequence in state.missing:
            state.missing.remove(sequence)
            return "GAP_RECOVERED"

        return "OUT_OF_ORDER"

    def unresolved_gaps(self, session, symbol):
        state = self.sessions.get((session, symbol))
        return sorted(state.missing) if state else []
