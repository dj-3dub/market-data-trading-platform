using System.Net.Http.Json;
using System.Text.Json;
using Confluent.Kafka;
using Prometheus;

Console.WriteLine("Strategy Engine starting...");

var builder = WebApplication.CreateBuilder(args);

// HttpClient is still here if we want HTTP fallback later
builder.Services.AddSingleton<HttpClient>();

var app = builder.Build();

// ---- Prometheus metrics ----
var tickCounter = Metrics.CreateCounter(
    name: "strategy_ticks_total",
    help: "Total number of ticks processed by the strategy engine");

var tradeCounter = Metrics.CreateCounter(
    name: "strategy_trades_total",
    help: "Total number of trades executed by the strategy engine");

var errorCounter = Metrics.CreateCounter(
    name: "strategy_errors_total",
    help: "Total number of errors encountered by the strategy engine");

var lastPriceGauge = Metrics.CreateGauge(
    name: "strategy_last_price",
    help: "Last observed price in the strategy engine");

var lastTickAgeGauge = Metrics.CreateGauge(
    name: "strategy_last_tick_age_seconds",
    help: "Age in seconds of the last processed tick");

// ---- Shared state for health ----
double lastPrice = 0.0;
double previousPrice = 0.0;
string lastSymbol = "FAKE";
string lastSource = "market-data-python";
DateTime lastTickTime = DateTime.MinValue;

// Kafka config
var kafkaBootstrap = Environment.GetEnvironmentVariable("KAFKA_BOOTSTRAP_SERVERS") ?? "kafka:9092";
var kafkaTopic = Environment.GetEnvironmentVariable("KAFKA_TICKS_TOPIC") ?? "ticks";

var consumerConfig = new ConsumerConfig
{
    BootstrapServers = kafkaBootstrap,
    GroupId = "strategy-engine-consumer",
    AutoOffsetReset = AutoOffsetReset.Earliest,
    EnableAutoCommit = true
};

Console.WriteLine($"[KAFKA] Strategy consumer connecting to {kafkaBootstrap}, topic={kafkaTopic}");

// ---- Background Kafka consumer loop ----
var cts = new CancellationTokenSource();

_ = Task.Run(() =>
{
    using var consumer = new ConsumerBuilder<Ignore, string>(consumerConfig).Build();
    consumer.Subscribe(kafkaTopic);

    Console.WriteLine("[KAFKA] Strategy consumer loop started...");

    try
    {
        while (!cts.Token.IsCancellationRequested)
        {
            try
            {
                var cr = consumer.Consume(cts.Token);
                var json = cr.Message.Value;

                var tick = JsonSerializer.Deserialize<Tick>(json);
                if (tick is not null)
                {
                    tickCounter.Inc();

                    previousPrice = lastPrice;
                    lastPrice = tick.price;
                    lastSymbol = tick.symbol;
                    lastSource = tick.source;
                    lastTickTime = DateTime.UtcNow;

                    lastPriceGauge.Set(lastPrice);
                    if (lastTickTime != DateTime.MinValue)
                    {
                        var ageSeconds = (DateTime.UtcNow - lastTickTime).TotalSeconds;
                        lastTickAgeGauge.Set(ageSeconds);
                    }

                    Console.WriteLine($"[TICK-KAFKA] {lastSymbol} {lastPrice}");

                    // simple strategy: buy if price is up > 0.1% from previous
                    if (previousPrice > 0.0 && lastPrice > previousPrice * 1.001)
                    {
                        tradeCounter.Inc();
                        Console.WriteLine($"[TRADE] BUY {lastSymbol} at {lastPrice} (total trades: {tradeCounter.Value})");
                    }
                }
            }
            catch (ConsumeException ex)
            {
                errorCounter.Inc();
                Console.WriteLine($"[KAFKA ERROR] Consume error: {ex.Error.Reason}");
            }
            catch (OperationCanceledException)
            {
                // graceful shutdown
                break;
            }
            catch (Exception ex)
            {
                errorCounter.Inc();
                Console.WriteLine($"[ERROR] {ex.Message}");
            }
        }
    }
    finally
    {
        consumer.Close();
        Console.WriteLine("[KAFKA] Strategy consumer loop stopping...");
    }
}, cts.Token);

// ---- Health endpoint ----
app.MapGet("/health", () =>
{
    var status = new
    {
        status = "ok",
        lastPrice,
        lastSymbol,
        lastSource,
        lastTickTime
    };

    return Results.Ok(status);
});

// HTTP metrics for all requests
app.UseHttpMetrics();

// Expose Prometheus metrics at /metrics
app.MapMetrics("/metrics");

// Ensure background loop stops on shutdown
app.Lifetime.ApplicationStopping.Register(() => cts.Cancel());

// Listen on port 7002 inside the container
await app.RunAsync("http://0.0.0.0:7002");

public record Tick(string symbol, double price, string source);
