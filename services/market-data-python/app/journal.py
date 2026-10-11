"""Durable producer outbox: a retry keeps the exact tick, key and identity."""
import json
import sqlite3
import uuid
from pathlib import Path


class Journal:
    def __init__(self, path, symbols, source="market-data-python"):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS symbols (symbol TEXT PRIMARY KEY, sequence INTEGER NOT NULL, price REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS pending (singleton INTEGER PRIMARY KEY CHECK(singleton=1), payload TEXT NOT NULL);
        """)
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO metadata VALUES ('stream_id', ?)", (uuid.uuid4().hex,))
            self.db.execute("INSERT OR IGNORE INTO metadata VALUES ('source', ?)", (source,))
            for symbol in symbols:
                self.db.execute("INSERT OR IGNORE INTO symbols VALUES (?, 0, 100)", (symbol,))
        self.stream_id = self.db.execute("SELECT value FROM metadata WHERE key='stream_id'").fetchone()[0]
        if self.db.execute("SELECT value FROM metadata WHERE key='source'").fetchone()[0] != source:
            raise ValueError("Producer source changed; restore its configuration or use a separate state directory")
        self.source = source

    def prepare(self, symbol, timestamp, movement):
        pending = self.db.execute("SELECT payload FROM pending WHERE singleton=1").fetchone()
        if pending:
            return json.loads(pending[0])
        sequence, price = self.db.execute("SELECT sequence,price FROM symbols WHERE symbol=?", (symbol,)).fetchone()
        tick = {"schema_version": 1, "stream_id": self.stream_id,
                "event_id": f"{self.stream_id}:{symbol}:{sequence + 1}",
                "sequence": sequence + 1, "symbol": symbol,
                "price": round(max(1, price + movement), 4),
                "source": self.source, "timestamp": timestamp}
        with self.db:
            self.db.execute("INSERT INTO pending VALUES (1, ?)", (json.dumps(tick, allow_nan=False),))
        return tick

    def acknowledge(self, tick):
        pending = self.db.execute("SELECT payload FROM pending WHERE singleton=1").fetchone()
        if not pending or json.loads(pending[0]) != tick:
            raise ValueError("Acknowledgement does not match durable pending tick")
        with self.db:
            self.db.execute("UPDATE symbols SET sequence=?,price=? WHERE symbol=?",
                            (tick["sequence"], tick["price"], tick["symbol"]))
            self.db.execute("DELETE FROM pending WHERE singleton=1")

    def close(self):
        self.db.close()
