using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.Data.Sqlite;

public sealed class SymbolState
{
    public decimal LastPrice { get; set; }
    public double Timestamp { get; set; }
    public long ProcessedTicks { get; set; }
    public string Signal { get; set; } = "WAIT";
    public string EventId { get; set; } = "";
    public string StreamId { get; set; } = "";
    public long Sequence { get; set; }
    public bool Blocked { get; set; }
}
public sealed class StreamState
{
    public string Symbol { get; set; } = "";
    public long LastSequence { get; set; }
    public long MaxSeen { get; set; }
}
public sealed class Snapshot
{
    public Dictionary<string, SymbolState> Symbols { get; set; } = new();
    public Dictionary<string, StreamState> Streams { get; set; } = new();
    public Dictionary<string, long> Offsets { get; set; } = new();
    public long Accepted { get; set; }
    public long Trades { get; set; }
    public long Duplicates { get; set; }
    public long OutOfOrder { get; set; }
    public long Gaps { get; set; }
    public long Quarantined { get; set; }
    public long Stale { get; set; }
}
public sealed record ProcessResult(string Outcome, Tick? Tick, bool Trade, Snapshot State);

// One active writer; the durable transaction contains application state, event
// ledger, offset and quarantine. An HTTP reader never sees uncommitted state.
public sealed class StateStore : IDisposable
{
    private readonly SqliteConnection db;
    private readonly FileStream writerLease;
    private readonly object gate = new();
    private readonly HashSet<string> symbols;
    private Snapshot state;

    public StateStore(string directory, IEnumerable<string> configuredSymbols)
    {
        Directory.CreateDirectory(directory);
        writerLease = new FileStream(Path.Combine(directory, "writer.lock"), FileMode.OpenOrCreate,
            FileAccess.ReadWrite, FileShare.None);
        try
        {
            symbols = new HashSet<string>(configuredSymbols, StringComparer.Ordinal);
            db = new SqliteConnection(new SqliteConnectionStringBuilder {
                DataSource = Path.Combine(directory, "strategy.sqlite"), Pooling = false }.ToString());
            db.Open();
            Execute(null, "PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA busy_timeout=5000;");
            Execute(null, """
                CREATE TABLE IF NOT EXISTS checkpoint(id INTEGER PRIMARY KEY CHECK(id=1), state TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS receipts(topic TEXT NOT NULL, partition_id INTEGER NOT NULL,
                    offset_id INTEGER NOT NULL, raw_hash TEXT NOT NULL, outcome TEXT NOT NULL,
                    PRIMARY KEY(topic,partition_id,offset_id));
                CREATE TABLE IF NOT EXISTS events(event_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL,
                    payload TEXT NOT NULL, signal TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS quarantine(topic TEXT NOT NULL, partition_id INTEGER NOT NULL,
                    offset_id INTEGER NOT NULL, reason TEXT NOT NULL, payload TEXT NOT NULL, received_at REAL NOT NULL, message_key TEXT,
                    PRIMARY KEY(topic,partition_id,offset_id));
                """);
            var saved = Scalar(null, "SELECT state FROM checkpoint WHERE id=1") as string;
            state = saved is null ? new Snapshot() : JsonSerializer.Deserialize<Snapshot>(saved)
                ?? throw new InvalidDataException("Checkpoint cannot be decoded");
            if (state.Symbols.Keys.Any(symbol => !symbols.Contains(symbol)))
                throw new InvalidDataException("Configured symbols no longer include checkpoint symbols");
            foreach (var symbol in symbols) state.Symbols.TryAdd(symbol, new SymbolState());
        }
        catch { writerLease.Dispose(); throw; }
    }

    private object? Scalar(SqliteTransaction? tx, string sql, params (string, object?)[] parameters)
    {
        using var command = db.CreateCommand(); command.Transaction = tx; command.CommandText = sql;
        foreach (var (key, value) in parameters) command.Parameters.AddWithValue(key, value ?? DBNull.Value);
        return command.ExecuteScalar();
    }
    private void Execute(SqliteTransaction? tx, string sql, params (string, object?)[] parameters)
    {
        using var command = db.CreateCommand(); command.Transaction = tx; command.CommandText = sql;
        foreach (var (key, value) in parameters) command.Parameters.AddWithValue(key, value ?? DBNull.Value);
        command.ExecuteNonQuery();
    }
    private static string Hash(string value) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value)));
    private static Snapshot Copy(Snapshot value) => JsonSerializer.Deserialize<Snapshot>(JsonSerializer.Serialize(value))!;
    public Snapshot Read() { lock(gate) return Copy(state); }
    public long NextOffset(string topic, int partition)
    {
        lock(gate) return state.Offsets.TryGetValue($"{topic}:{partition}", out var offset) ? offset + 1 : 0;
    }

    public ProcessResult Process(string topic, int partition, long offset, string? key,
        string payload, double now, Action? beforeCommit = null)
    {
        lock(gate)
        {
            var rawHash = Hash((key ?? "") + "\0" + payload);
            using var tx = db.BeginTransaction();
            var prior = Scalar(tx, "SELECT raw_hash FROM receipts WHERE topic=$t AND partition_id=$p AND offset_id=$o",
                ("$t", topic), ("$p", partition), ("$o", offset)) as string;
            if (prior is not null)
            {
                if (prior != rawHash) throw new InvalidDataException("Kafka topic/offset was reused with a different payload; state must not be reused after topic recreation");
                return new ProcessResult("offset-replay", null, false, Copy(state));
            }
            var offsetKey = $"{topic}:{partition}";
            if (offset != NextOffset(topic, partition))
                throw new InvalidDataException("Kafka offset gap: required history is missing; restore/replay into a separate state store");
            var next = Copy(state);
            Tick? tick = null;
            var outcome = "accepted";
            var trade = false;
            try
            {
                tick = JsonSerializer.Deserialize<Tick>(payload);
                TickRules.Validate(tick, now, symbols);
                if (key != tick!.symbol) throw new JsonException("Kafka key must equal symbol");
                var streamKey = $"{tick.source}:{tick.stream_id}:{tick.symbol}";
                if (!next.Streams.TryGetValue(streamKey, out var stream))
                    next.Streams[streamKey] = stream = new StreamState { Symbol = tick.symbol };
                var symbol = next.Symbols[tick.symbol];
                tick = tick with { price = decimal.Parse(tick.price.ToString("G29", System.Globalization.CultureInfo.InvariantCulture), System.Globalization.CultureInfo.InvariantCulture) };
                var canonical = JsonSerializer.Serialize(tick);
                var acceptedHash = Scalar(tx, "SELECT payload_hash FROM events WHERE event_id=$id", ("$id", tick.event_id)) as string;
                if (tick.sequence < stream.LastSequence) next.OutOfOrder++;
                if (acceptedHash is not null)
                {
                    if (acceptedHash != Hash(canonical)) outcome = "event-id-conflict";
                    else { outcome = "duplicate"; next.Duplicates++; }
                }
                else if (tick.sequence <= stream.LastSequence) outcome = "out-of-order";
                else if (tick.sequence != stream.LastSequence + 1)
                {
                    outcome = "sequence-gap"; next.Gaps++;
                    stream.MaxSeen = Math.Max(stream.MaxSeen, tick.sequence);
                    symbol.Blocked = true; symbol.Signal = "BLOCKED";
                }
                else if (tick.timestamp < symbol.Timestamp) outcome = "timestamp-regression";
                else
                {
                    stream.LastSequence = tick.sequence;
                    stream.MaxSeen = Math.Max(stream.MaxSeen, tick.sequence);
                    symbol.Blocked = next.Streams.Values.Any(s => s.Symbol == tick.symbol && s.LastSequence < s.MaxSeen);
                    var fresh = TickRules.Fresh(tick.timestamp, now);
                    var signal = !fresh ? "STALE" : symbol.Blocked ? "BLOCKED" : TickRules.Signal(symbol.LastPrice, tick.price);
                    trade = signal == "BUY";
                    if (trade) next.Trades++;
                    if (!fresh) next.Stale++;
                    next.Accepted++; symbol.ProcessedTicks++;
                    symbol.LastPrice = tick.price; symbol.Timestamp = tick.timestamp;
                    symbol.EventId = tick.event_id; symbol.StreamId = tick.stream_id;
                    symbol.Sequence = tick.sequence; symbol.Signal = signal;
                    Execute(tx, "INSERT INTO events VALUES ($id,$hash,$payload,$signal)",
                        ("$id", tick.event_id), ("$hash", Hash(canonical)), ("$payload", canonical), ("$signal", signal));
                }
            }
            catch (JsonException) { outcome = "invalid-tick"; }
            if (outcome is not "accepted" and not "duplicate")
            {
                next.Quarantined++;
                Execute(tx, "INSERT INTO quarantine VALUES ($t,$p,$o,$reason,$payload,$now,$key)",
                    ("$t", topic), ("$p", partition), ("$o", offset), ("$reason", outcome), ("$payload", payload), ("$now", now), ("$key", key));
            }
            next.Offsets[offsetKey] = offset;
            Execute(tx, "INSERT INTO receipts VALUES ($t,$p,$o,$hash,$outcome)",
                ("$t", topic), ("$p", partition), ("$o", offset), ("$hash", rawHash), ("$outcome", outcome));
            Execute(tx, "INSERT INTO checkpoint VALUES (1,$state) ON CONFLICT(id) DO UPDATE SET state=excluded.state",
                ("$state", JsonSerializer.Serialize(next)));
            beforeCommit?.Invoke(); // Crash/rollback seam used by the contract tests.
            tx.Commit();
            state = next;
            return new ProcessResult(outcome, tick, trade, Copy(state));
        }
    }

    public object[] Quarantine(int limit)
    {
        lock(gate)
        {
            using var cmd = db.CreateCommand();
            cmd.CommandText = "SELECT topic,partition_id,offset_id,reason,payload,received_at,message_key FROM quarantine ORDER BY received_at DESC LIMIT $n";
            cmd.Parameters.AddWithValue("$n", Math.Clamp(limit, 1, 100));
            using var reader = cmd.ExecuteReader(); var rows = new List<object>();
            while(reader.Read()) rows.Add(new { topic=reader.GetString(0), partition=reader.GetInt32(1),
                offset=reader.GetInt64(2), reason=reader.GetString(3), payload=reader.GetString(4), receivedAt=reader.GetDouble(5), key=reader.IsDBNull(6) ? null : reader.GetString(6) });
            return rows.ToArray();
        }
    }
    public void Dispose() { lock(gate) { db.Dispose(); writerLease.Dispose(); } }
}
