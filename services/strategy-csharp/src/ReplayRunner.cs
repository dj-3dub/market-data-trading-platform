using System.Text.Json;

public static class ReplayRunner
{
    public static int Run(string[] args)
    {
        string Arg(string key) => args[Array.IndexOf(args, key) + 1];
        var fixture = Arg("--replay");
        var directory = Arg("--state-dir");
        var clock = double.Parse(Arg("--clock"), System.Globalization.CultureInfo.InvariantCulture);
        if (!double.IsFinite(clock) || clock <= 0) throw new InvalidDataException("Replay clock must be finite and positive");
        using var store = new StateStore(directory, new[] { "FAKE", "FAKE2", "FAKE3" });
        var crashBoundary = args.Contains("--crash-boundary") ? Arg("--crash-boundary") : null;
        var crashOffset = args.Contains("--crash-offset") ? long.Parse(Arg("--crash-offset")) : -1;
        if (crashBoundary is not null && crashBoundary is not "before" and not "after")
            throw new ArgumentException("Crash boundary must be before or after");
        void CrashOnce() {
            var marker = Path.Combine(directory, "replay-crash-fired");
            if (!File.Exists(marker)) {
                using(var file = new FileStream(marker, FileMode.CreateNew)) { file.WriteByte(1); file.Flush(true); }
                Environment.Exit(86);
            }
        }
        foreach (var line in File.ReadLines(fixture).Where(line => !string.IsNullOrWhiteSpace(line)))
        {
            using var document = JsonDocument.Parse(line); var row = document.RootElement;
            var offset = row.GetProperty("offset").GetInt64();
            Action? beforeCommit = crashBoundary == "before" && offset == crashOffset ? CrashOnce : null;
            store.Process("replay-v1", row.GetProperty("partition").GetInt32(), offset,
                row.GetProperty("key").GetString(), row.GetProperty("payload").GetString()!, clock, beforeCommit);
            if (crashBoundary == "after" && offset == crashOffset) CrashOnce();
        }
        Console.WriteLine(JsonSerializer.Serialize(store.Read()));
        return 0;
    }
}
