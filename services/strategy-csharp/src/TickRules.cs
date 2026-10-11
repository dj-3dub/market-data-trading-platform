using System.Text.Json;
using System.Text.Json.Serialization;

[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record Tick(int schema_version, string stream_id, string event_id,
    long sequence, string symbol, decimal price, string source, double timestamp);

public static class TickRules
{
    public static void Validate(Tick? tick, double now, IReadOnlySet<string> symbols)
    {
        if (tick is null || tick.schema_version != 1 || !symbols.Contains(tick.symbol ?? "")
            || tick.price <= 0 || tick.price > 1000000000m || !double.IsFinite(tick.timestamp)
            || tick.timestamp <= 0 || tick.timestamp > now + 2
            || tick.sequence < 1 || tick.sequence > 9007199254740991L
            || !Guid.TryParseExact(tick.stream_id, "N", out _)
            || tick.stream_id != tick.stream_id.ToLowerInvariant()
            || tick.source != "market-data-python"
            || tick.event_id != $"{tick.stream_id}:{tick.symbol}:{tick.sequence}")
            throw new JsonException("Invalid v1 simulated tick");
    }

    public static string Signal(decimal previous, decimal current) =>
        previous > 0 && current > previous * 1.001m ? "BUY" : "HOLD";

    public static bool Fresh(double timestamp, double now) =>
        timestamp > 0 && now - timestamp >= -2 && now - timestamp < 10;
}
