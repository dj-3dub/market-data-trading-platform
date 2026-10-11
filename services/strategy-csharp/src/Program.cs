using System.Text.Json;
using Confluent.Kafka;
using Prometheus;

if (args.Contains("--replay")) return ReplayRunner.Run(args);
var builder = WebApplication.CreateBuilder(args);
var app = builder.Build();
var symbols = (Environment.GetEnvironmentVariable("MARKET_SYMBOLS") ?? "FAKE,FAKE2,FAKE3").Split(',');
if (symbols.Length != symbols.Distinct().Count() || symbols.Any(s => !System.Text.RegularExpressions.Regex.IsMatch(s, "^FAKE[0-9]*$")))
    throw new InvalidDataException("Use distinct FAKE simulation symbols");
var directory = Environment.GetEnvironmentVariable("STRATEGY_STATE_DIR") ?? "/data";
using var store = new StateStore(directory, symbols);
var topic = Environment.GetEnvironmentVariable("KAFKA_TICKS_TOPIC") ?? "ticks-v1";
var group = Environment.GetEnvironmentVariable("KAFKA_CONSUMER_GROUP") ?? "strategy-engine-v1";
var tickCounter = Metrics.CreateCounter("strategy_ticks_total", "Durably accepted unique ticks");
var tradeCounter = Metrics.CreateCounter("strategy_trades_total", "Durably recorded simulated BUY signals");
var errorCounter = Metrics.CreateCounter("strategy_errors_total", "Durably quarantined input records");
var duplicateCounter = Metrics.CreateCounter("strategy_duplicates_total", "Duplicate event identities suppressed");
var gapCounter = Metrics.CreateCounter("strategy_sequence_gaps_total", "Sequence gap records detected");
var reorderedCounter = Metrics.CreateCounter("strategy_out_of_order_total", "Events older than their stream sequence");
var staleCounter = Metrics.CreateCounter("strategy_stale_ticks_total", "Accepted stale ticks with signals suppressed");
var commitErrors = Metrics.CreateCounter("strategy_commit_errors_total", "Kafka commit errors; application stops to retry safely");
var lastPrice = Metrics.CreateGauge("strategy_last_price", "Last FAKE price");
var lastAge = Metrics.CreateGauge("strategy_last_tick_age_seconds", "Age of FAKE source tick");
var symbolAge = Metrics.CreateGauge("strategy_symbol_last_tick_age_seconds", "Age of source tick by symbol", new GaugeConfiguration { LabelNames = new[] { "symbol" } });
var blocked = Metrics.CreateGauge("strategy_symbol_sequence_blocked", "Sequence recovery required", new GaugeConfiguration { LabelNames = new[] { "symbol" } });
var latency = Metrics.CreateHistogram("strategy_tick_latency_seconds", "Generation to durable strategy processing latency");
var processing = Metrics.CreateHistogram("strategy_processing_time_seconds", "Consume to local durable checkpoint time");
var initial = store.Read();
tickCounter.Inc(initial.Accepted); tradeCounter.Inc(initial.Trades); errorCounter.Inc(initial.Quarantined);
duplicateCounter.Inc(initial.Duplicates); gapCounter.Inc(initial.Gaps); reorderedCounter.Inc(initial.OutOfOrder); staleCounter.Inc(initial.Stale);
var cts = new CancellationTokenSource();
var workerFailed = false;
var config = new ConsumerConfig {
    BootstrapServers = Environment.GetEnvironmentVariable("KAFKA_BOOTSTRAP_SERVERS") ?? "kafka:9092",
    SecurityProtocol = Environment.GetEnvironmentVariable("KAFKA_SECURITY_PROTOCOL") == "SSL" ? SecurityProtocol.Ssl : SecurityProtocol.Plaintext,
    GroupId = group, AutoOffsetReset = AutoOffsetReset.Error,
    EnableAutoCommit = false, EnableAutoOffsetStore = false
};
var fixedClockText = Environment.GetEnvironmentVariable("STRATEGY_TEST_CLOCK_SECONDS");
if (fixedClockText is not null && Environment.GetEnvironmentVariable("STRATEGY_TEST_MODE") != "1")
    throw new InvalidDataException("Fixed clock is allowed only in explicit test mode");
var fixedClock = fixedClockText is null ? (double?)null : double.Parse(fixedClockText, System.Globalization.CultureInfo.InvariantCulture);
if (fixedClock is not null && (!double.IsFinite(fixedClock.Value) || fixedClock <= 0))
    throw new InvalidDataException("Test clock must be finite and positive");
double Now() => fixedClock ?? DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0;
void CrashOnce(string eventId) {
    if (Environment.GetEnvironmentVariable("STRATEGY_TEST_MODE") != "1")
        throw new InvalidDataException("Crash injection is allowed only in explicit test mode");
    var marker = Path.Combine(directory, "crash-fired-" + Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(eventId))));
    if (!File.Exists(marker)) {
        using(var file = new FileStream(marker, FileMode.CreateNew)) { file.WriteByte(1); file.Flush(true); }
        Environment.Exit(86);
    }
}
var consumerTask = Task.Run(() => {
    using var consumer = new ConsumerBuilder<string, string>(config)
        .SetPartitionsAssignedHandler((_, partitions) => partitions.Select(p =>
            new TopicPartitionOffset(p, new Offset(store.NextOffset(p.Topic, p.Partition.Value)))))
        .Build();
    consumer.Subscribe(topic);
    try {
        while (!cts.IsCancellationRequested) {
            ConsumeResult<string,string> record;
            try { record = consumer.Consume(cts.Token); }
            catch (ConsumeException error) when (!error.Error.IsFatal && error.Error.Code != ErrorCode.OffsetOutOfRange && error.Error.Code != ErrorCode.Local_AutoOffsetReset) {
                Console.Error.WriteLine(JsonSerializer.Serialize(new { component="consumer", error=error.Error.Reason }));
                continue;
            }
            var timer = System.Diagnostics.Stopwatch.StartNew();
            var crashEvent = Environment.GetEnvironmentVariable("STRATEGY_CRASH_EVENT_ID");
            var crashBefore = Environment.GetEnvironmentVariable("STRATEGY_CRASH_BOUNDARY") == "before";
            Action? beforeCommit = null;
            if (crashBefore && crashEvent is not null) {
                try {
                    using var document = JsonDocument.Parse(record.Message.Value ?? "null");
                    if (document.RootElement.ValueKind == JsonValueKind.Object
                        && document.RootElement.TryGetProperty("event_id", out var id) && id.GetString() == crashEvent)
                        beforeCommit = () => CrashOnce(crashEvent);
                } catch(JsonException) { }
            }
            var result = store.Process(record.Topic, record.Partition.Value, record.Offset.Value,
                record.Message.Key, record.Message.Value ?? "null", Now(), beforeCommit);
            if (result.Outcome != "offset-replay") {
                var current = result.State;
                tickCounter.IncTo(current.Accepted); tradeCounter.IncTo(current.Trades); errorCounter.IncTo(current.Quarantined);
                duplicateCounter.IncTo(current.Duplicates); gapCounter.IncTo(current.Gaps);
                reorderedCounter.IncTo(current.OutOfOrder); staleCounter.IncTo(current.Stale);
                if (result.Outcome == "accepted") latency.Observe(Math.Max(0, Now() - result.Tick!.timestamp));
                processing.Observe(timer.Elapsed.TotalSeconds);
            }
            // Optional, explicit lab-only one-shot crash AFTER the SQLite commit
            // and BEFORE the Kafka commit. The marker survives process restart.
            if (!crashBefore && crashEvent is not null && result.Tick?.event_id == crashEvent && result.Outcome == "accepted")
                CrashOnce(crashEvent);
            try { consumer.Commit(record); }
            catch (KafkaException) { commitErrors.Inc(); throw; }
            Console.WriteLine(JsonSerializer.Serialize(new { eventId=result.Tick?.event_id, symbol=result.Tick?.symbol,
                topic=record.Topic, partition=record.Partition.Value, offset=record.Offset.Value,
                outcome=result.Outcome, simulatedBuy=result.Trade }));
        }
    }
    catch (OperationCanceledException) when (cts.IsCancellationRequested) { }
    catch (Exception error) {
        workerFailed = true; Environment.ExitCode = 1;
        Console.Error.WriteLine(JsonSerializer.Serialize(new { component="strategy", fatal=error.Message }));
        app.Lifetime.StopApplication();
    }
    finally { try { consumer.Close(); } catch(Exception error) { Console.Error.WriteLine(error.Message); } }
});
app.Lifetime.ApplicationStopping.Register(() => cts.Cancel());
app.MapGet("/health", () => Results.Json(new { status=workerFailed ? "worker-failed" : "ok" }, statusCode:workerFailed ? 503 : 200));
app.MapGet("/state", (string? symbol) => GetState(symbol ?? "FAKE"));
app.MapGet("/ready", () => {
    var state = store.Read(); var now = Now();
    return Results.Json(new { status=state.Symbols.Values.All(s => !s.Blocked && TickRules.Fresh(s.Timestamp,now)) ? "ready" : "stale" },
        statusCode:!workerFailed && state.Symbols.Values.All(s => !s.Blocked && TickRules.Fresh(s.Timestamp,now)) ? 200 : 503);
});
app.MapGet("/integrity", () => Results.Json(store.Read()));
app.MapGet("/quarantine", (int? limit) => Results.Json(store.Quarantine(limit ?? 20)));
IResult GetState(string symbol) {
    var state = store.Read();
    if (!state.Symbols.TryGetValue(symbol, out var value)) return Results.NotFound(new { error="Unsupported simulated symbol" });
    var fresh = !workerFailed && !value.Blocked && TickRules.Fresh(value.Timestamp,Now());
    return Results.Json(new { status=fresh ? "ok" : value.Blocked ? "sequence-blocked" : "stale",
        lastPrice=value.LastPrice, lastSymbol=symbol, lastSource="market-data-python", timestamp=value.Timestamp,
        ageSeconds=value.Timestamp > 0 ? Math.Max(0,Now()-value.Timestamp) : (double?)null,
        lastLatencySeconds=value.Timestamp > 0 ? Math.Max(0,Now()-value.Timestamp) : (double?)null,
        processedTicks=value.ProcessedTicks, signal=value.Signal,
        allSymbolsFresh=state.Symbols.Values.All(s => !s.Blocked && TickRules.Fresh(s.Timestamp,Now())), eventId=value.EventId,
        streamId=value.StreamId, sequence=value.Sequence, sequenceBlocked=value.Blocked }, statusCode:fresh ? 200 : 503);
}
app.Use(async (context, next) => {
    var snapshot = store.Read();
    foreach(var (symbol, value) in snapshot.Symbols) {
        var age = value.Timestamp > 0 ? Math.Max(0,Now()-value.Timestamp) : double.PositiveInfinity;
        symbolAge.WithLabels(symbol).Set(age); blocked.WithLabels(symbol).Set(value.Blocked ? 1 : 0);
        if(symbol == "FAKE") { lastAge.Set(age); lastPrice.Set((double)value.LastPrice); }
    }
    await next(context);
});
app.UseHttpMetrics(); app.MapMetrics("/metrics");
await app.RunAsync("http://0.0.0.0:7002");
await consumerTask;
return Environment.ExitCode;
