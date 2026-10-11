using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using Xunit;

public class TickRulesTests
{
    static readonly string Stream = "00000000000000000000000000000001";
    static readonly HashSet<string> Symbols = new() { "FAKE", "FAKE2", "FAKE3" };
    static Tick Tick(long sequence, decimal price=100m, string symbol="FAKE", double timestamp=999) =>
        new(1, Stream, $"{Stream}:{symbol}:{sequence}", sequence, symbol, price, "market-data-python", timestamp);
    static string Payload(Tick tick) => JsonSerializer.Serialize(tick);
    static string DirectoryPath() => Path.Combine(Path.GetTempPath(), "strategy-test-" + Guid.NewGuid().ToString("N"));

    [Theory]
    [InlineData(0,100,"HOLD")]
    [InlineData(100,100.1,"HOLD")]
    [InlineData(100,100.2,"BUY")]
    [InlineData(100,99,"HOLD")]
    public void SignalBoundary(double previous, double current, string expected) =>
        Assert.Equal(expected, TickRules.Signal((decimal)previous,(decimal)current));
    [Theory]
    [InlineData(990,false)] [InlineData(991,true)] [InlineData(1002,true)] [InlineData(1003,false)]
    public void FreshnessBoundary(double timestamp, bool expected) => Assert.Equal(expected, TickRules.Fresh(timestamp,1000));
    [Fact]
    public void RejectInvalidContractAndIdentity()
    {
        Assert.Throws<JsonException>(() => TickRules.Validate(null,1000,Symbols));
        foreach(var invalid in new[] { Tick(0), Tick(1,-1), Tick(1,timestamp:1003), Tick(1) with { schema_version=2 },
            Tick(1) with { event_id="forged" }, Tick(1) with { stream_id="bad" }, Tick(1,symbol:"OTHER") })
            Assert.Throws<JsonException>(() => TickRules.Validate(invalid,1000,Symbols));
    }
    [Fact]
    public void DuplicateAndLateDuplicateDoNotCreateTrades()
    {
        using var store = new StateStore(DirectoryPath(),Symbols);
        var first=Payload(Tick(1)); var second=Payload(Tick(2,100.2m));
        store.Process("ticks",0,0,"FAKE",first,1000);
        store.Process("ticks",0,1,"FAKE",second,1000);
        store.Process("ticks",0,2,"FAKE",second,1000);
        store.Process("ticks",0,3,"FAKE",first,1000);
        var state=store.Read();
        Assert.Equal(2,state.Accepted); Assert.Equal(1,state.Trades);
        Assert.Equal(2,state.Duplicates); Assert.Equal(1,state.OutOfOrder);
    }
    [Fact]
    public void GapBlocksSignalsUntilMissingPrefixIsReplayed()
    {
        using var store = new StateStore(DirectoryPath(),Symbols);
        store.Process("ticks",0,0,"FAKE",Payload(Tick(1)),1000);
        var gap=store.Process("ticks",0,1,"FAKE",Payload(Tick(4,104)),1000);
        Assert.Equal("sequence-gap",gap.Outcome); Assert.True(gap.State.Symbols["FAKE"].Blocked);
        store.Process("ticks",0,2,"FAKE",Payload(Tick(2,102)),1000);
        store.Process("ticks",0,3,"FAKE",Payload(Tick(3,103)),1000);
        Assert.Equal(0,store.Read().Trades);
        var recovered=store.Process("ticks",0,4,"FAKE",Payload(Tick(4,104)),1000);
        Assert.False(recovered.State.Symbols["FAKE"].Blocked); Assert.True(recovered.Trade);
        Assert.Single(store.Quarantine(100));
    }
    [Fact]
    public void StaleTicksUpdateAnalyticalStateButCannotBuy()
    {
        using var store = new StateStore(DirectoryPath(),Symbols);
        store.Process("ticks",0,0,"FAKE",Payload(Tick(1,timestamp:970)),1000);
        var stale=store.Process("ticks",0,1,"FAKE",Payload(Tick(2,102,timestamp:971)),1000);
        Assert.Equal("STALE",stale.State.Symbols["FAKE"].Signal); Assert.Equal(0,stale.State.Trades);
        var fresh=store.Process("ticks",0,2,"FAKE",Payload(Tick(3,103)),1000);
        Assert.True(fresh.Trade); Assert.Equal(2,fresh.State.Stale);
    }
    [Fact]
    public void MalformedAndWrongKeyRecordsAreDurablyQuarantined()
    {
        var path=DirectoryPath();
        using(var store=new StateStore(path,Symbols)) {
            Assert.Equal("invalid-tick",store.Process("ticks",0,0,"FAKE","not-json",1000).Outcome);
            Assert.Equal("invalid-tick",store.Process("ticks",0,1,"OTHER",Payload(Tick(1)),1000).Outcome);
        }
        using(var reopened=new StateStore(path,Symbols)) {
            Assert.Equal(2,reopened.Read().Quarantined); Assert.Equal(2,reopened.Quarantine(100).Length);
            Assert.Equal(2,reopened.NextOffset("ticks",0));
            Assert.Equal("accepted",reopened.Process("ticks",0,2,"FAKE",Payload(Tick(1)),1000).Outcome);
        }
    }
    [Fact]
    public void CrashBeforeCheckpointRollsBackStateAndOffset()
    {
        var path=DirectoryPath(); var payload=Payload(Tick(1));
        using(var store=new StateStore(path,Symbols)) {
            Assert.Throws<IOException>(() => store.Process("ticks",0,0,"FAKE",payload,1000,
                () => throw new IOException("crash before commit")));
            Assert.Equal(0,store.Read().Accepted); Assert.Equal(0,store.NextOffset("ticks",0));
        }
        using(var recovered=new StateStore(path,Symbols)) {
            recovered.Process("ticks",0,0,"FAKE",payload,1000);
            Assert.Equal(1,recovered.Read().Accepted);
        }
    }
    [Fact]
    public void CrashAfterCheckpointBeforeKafkaAckPreservesStateAndSuppressesReplay()
    {
        var path=DirectoryPath(); var payload=Payload(Tick(1));
        using(var store=new StateStore(path,Symbols)) store.Process("ticks",0,0,"FAKE",payload,1000);
        using(var recovered=new StateStore(path,Symbols)) {
            Assert.Equal(1,recovered.NextOffset("ticks",0));
            Assert.Equal("offset-replay",recovered.Process("ticks",0,0,"FAKE",payload,1000).Outcome);
            Assert.Equal(1,recovered.Read().Accepted);
            Assert.Throws<InvalidDataException>(() => recovered.Process("ticks",0,0,"FAKE",Payload(Tick(1,999)),1000));
        }
    }
    [Fact]
    public void EventIdConflictCannotPoisonPrice()
    {
        using var store=new StateStore(DirectoryPath(),Symbols);
        store.Process("ticks",0,0,"FAKE",Payload(Tick(1)),1000);
        Assert.Equal("event-id-conflict",store.Process("ticks",0,1,"FAKE",Payload(Tick(1,999)),1000).Outcome);
        Assert.Equal(100,store.Read().Symbols["FAKE"].LastPrice);
    }
    [Fact]
    public void MissingKafkaOffsetsFailClosed()
    {
        using var store=new StateStore(DirectoryPath(),Symbols);
        Assert.Throws<InvalidDataException>(() => store.Process("ticks",0,3,"FAKE",Payload(Tick(1)),1000));
        Assert.Equal(0,store.Read().Accepted);
    }
    [Fact]
    public void SymbolsHaveIndependentPricesAndSequences()
    {
        using var store=new StateStore(DirectoryPath(),Symbols);
        store.Process("ticks",0,0,"FAKE",Payload(Tick(1)),1000);
        store.Process("ticks",0,1,"FAKE2",Payload(Tick(1,900,"FAKE2")),1000);
        Assert.Equal(0,store.Read().Trades);
        Assert.Equal(1,store.Read().Symbols["FAKE2"].ProcessedTicks);
    }
}
