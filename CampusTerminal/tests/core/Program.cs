// SPDX-License-Identifier: GPL-3.0-or-later
using System.Buffers.Binary;
using System.Text;
using CampusAuth;

int checks = 0;
void Check(bool condition, string label)
{
    if (!condition)
    {
        Console.WriteLine("FAIL " + label);
        Console.Out.Flush();
        throw new InvalidOperationException(label);
    }
    checks++;
}
if (args.Contains("--logging-only", StringComparer.Ordinal))
{
    LoggingChecks.Run(Check);
    Console.WriteLine($"PASS: {checks} logging checks.");
    return;
}
var identity = new TrialIdentity(Guid.NewGuid(), "020000000001", "192.0.2.1", "test-route");
var snapshot = new TrialSnapshot(identity, true, false, true, false, true);
var gate = new TrialAddressGate(identity);
Check(gate.Observe(snapshot) == null && gate.BoundIdentity == null, "No premature binding");
GuiHost.ApplyProtocolStage(gate, "EapSuccessNotConnectivityVerified");
Check(gate.Authenticated, "GUI EAP event advances address gate");
Check(gate.Observe(snapshot) == null && gate.BoundIdentity == identity, "Post-authentication address binds");
Check(TrialSafety.IsOriginalGui("iNode Client") && !TrialSafety.IsOriginalSuite("iNode Client"),
    "Orphan iNode GUI is not treated as the 802.1X suite");
var portable = Path.Combine(Path.GetTempPath(), "CampusTerminal-portable-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(portable);
File.WriteAllText(Path.Combine(portable, "probes.json"), "{}");
Check(string.Equals(GuiHost.FindRepositoryRoot(portable), Path.GetFullPath(portable), StringComparison.OrdinalIgnoreCase),
    "Portable folder without observer tree is still a valid data root");
Directory.Delete(portable, true);
Check(gate.Observe(snapshot with { OriginalClientRunning=true }) != null, "Original client excluded");
Check(gate.Observe(snapshot with { Identity=identity with { Ipv4="192.0.2.2" } }) != null, "IP change rejected");
Check(typeof(TrialSnapshot).GetProperty("PolicyExcluded") == null, "Connection safety has no scheduled campus shutdown");
var budgetDir = Path.Combine(Path.GetTempPath(), "campus-auto-fail-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(budgetDir);
AutoFailureBudget.UseStore(Path.Combine(budgetDir, "auto-failures.json"));
AutoFailureBudget.Reset();
Check(!AutoFailureBudget.Blocked && AutoFailureBudget.Count == 0, "Fresh auto-failure budget is open");
for (var i = 0; i < AutoFailureBudget.Max; i++) AutoFailureBudget.Record();
Check(AutoFailureBudget.Blocked && AutoFailureBudget.Count == 5, "Five auth failures block further automatic EAP");
AutoFailureBudget.Reset();
Check(!AutoFailureBudget.Blocked, "Verified success clears the persisted cap");
for (var i = 0; i < AutoFailureBudget.Max; i++) AutoFailureBudget.Record();
AutoFailureBudget.Forget();
Check(AutoFailureBudget.Count == 5, "A new process would otherwise reload the saved cap");
AutoFailureBudget.ResetOnStart();
Check(AutoFailureBudget.Count == 0 && !AutoFailureBudget.Blocked, "Software restart clears the retry cap");
Directory.Delete(budgetDir, true);
AutoFailureBudget.Forget();
Check(Adapters.LooksLikeAlternative("Remote NDIS based Internet Sharing Device", "以太网 2",
    System.Net.NetworkInformation.NetworkInterfaceType.Ethernet), "USB RNDIS is an alternative path");
Check(CampusRoute.YieldMetricFor([]) == 9000, "Campus yield metric is above Windows automatic metrics");
Check(CampusRoute.YieldMetricFor([75, 9500]) == 9550, "A higher foreign metric still loses to the phone");
Check(DhcpRenew.IphlpapiName("343573cf-c61d-4c30-9309-955ae4f581c8") ==
    @"\DEVICE\TCPIP_{343573CF-C61D-4C30-9309-955AE4F581C8}", "DHCP release uses the TCPIP device name");
Check(DhcpRenew.IphlpapiName("{343573CF-C61D-4C30-9309-955AE4F581C8}") ==
    @"\DEVICE\TCPIP_{343573CF-C61D-4C30-9309-955AE4F581C8}", "Braced adapter ids keep a single pair of braces");
Check(Adapters.IsPhoneTether("Remote NDIS based Internet Sharing Device", "以太网 2"), "Phone RNDIS is unbound from capture");
Check(Adapters.IsPhoneTether("Apple Mobile Device Ethernet", "以太网 3"), "iPhone tether is unbound from capture");
Check(Adapters.IsPhoneTether("USB Ethernet/RNDIS Gadget", "以太网 5"), "Linux gadget tether is recognized");
Check(Adapters.IsPhoneTether("HUAWEI Mobile Connect - Network Card", "以太网 6"), "Huawei mobile connect is recognized");
Check(Adapters.IsPhoneTether("远程 NDIS 兼容设备", "以太网 7"), "Localized Remote NDIS is recognized");
int seen = 0;
foreach (var nic in System.Net.NetworkInformation.NetworkInterface.GetAllNetworkInterfaces())
{
    int index = 0;
    try { index = nic.GetIPProperties().GetIPv4Properties()?.Index ?? 0; } catch { }
    if (index <= 0) continue;
    string reported = DhcpRenew.AdapterName(index, nic.Id);
    Check(reported.Contains("TCPIP", StringComparison.OrdinalIgnoreCase) || reported.StartsWith(@"\DEVICE\", StringComparison.OrdinalIgnoreCase),
        "Live GetInterfaceInfo name is a device path, not this PC's alias");
    seen++;
    break;
}
Check(seen == 1, "This Windows install exposes at least one IPv4 interface to GetInterfaceInfo");
Check(!Adapters.IsPhoneTether("Realtek USB GbE Family Controller", "以太网"), "A USB Ethernet dongle keeps the capture driver");
Check(!Adapters.IsCampusPort("Remote NDIS based Internet Sharing Device", "以太网 2",
    System.Net.NetworkInformation.NetworkInterfaceType.Ethernet), "Phone USB tether is not offered as the campus port");
Check(Adapters.IsCampusPort("Realtek USB GbE Family Controller", "以太网",
    System.Net.NetworkInformation.NetworkInterfaceType.Ethernet), "A USB Ethernet dongle can still be the campus port");
Check(Adapters.LooksLikeAlternative("Apple Mobile Device Ethernet", "以太网 3",
    System.Net.NetworkInformation.NetworkInterfaceType.Ethernet), "iPhone USB tether is an alternative path");
Check(TrialSafety.BlockReason(identity, snapshot with { LinkUp = false, AlternativePath = true }) == "AlternativeNetworkPath",
    "Another network stops link-down retries");
var recoveryFile = Path.Combine(Path.GetTempPath(), "recovery-events-" + Guid.NewGuid().ToString("N") + ".json");
RecoveryLog.UseStore(recoveryFile);
RecoveryLog.Observe(0, "TwoCampusRoundsPassed");
Check(RecoveryLog.Recent().Length == 0, "The first login is not listed as an automatic reconnect");
RecoveryLog.BeginCampaign("campaign-a");
RecoveryLog.Observe(1, "AuthenticationGenerationStarted");
RecoveryLog.Observe(0, "TwoCampusRoundsPassed");
RecoveryLog.Observe(0, "TwoCampusRoundsPassed");
Check(RecoveryLog.Recent().Length == 1, "A later health check is not another reconnect");
RecoveryLog.EndCampaign();
RecoveryLog.BeginCampaign("campaign-b");
RecoveryLog.Observe(2, "AuthenticationGenerationStarted");
RecoveryLog.Finish(RecoveryLog.Short("LinkUnavailable"));
RecoveryLog.EndCampaign();
RecoveryLog.BeginCampaign("campaign-c");
RecoveryLog.Observe(3, "AuthenticationGenerationStarted");
RecoveryLog.Observe(3, "ReconnectAttemptsExhausted");
RecoveryLog.EndCampaign();
RecoveryLog.BeginCampaign("campaign-d");
var shown = RecoveryLog.Recent();
Check(shown.Length == 4, "Recovery history retains up to 100 campaigns");
Check(shown[0]["result"]!.GetValue<string>() == "成功", "A generation-zero success is recorded in an explicit campaign");
Check(shown[1]["result"]!.GetValue<string>() == "断线", "A dropped link is recorded as the result");
Check(shown[2]["result"]!.GetValue<string>() == "失败", "Exhausted reconnect is recorded as failure");
Check(shown[3]["result"]!.GetValue<string>() == "重连中", "An in-progress reconnect stays open");
Check(shown[0]["at"]!.GetValue<string>().Length > 0 && shown[0]["time"]!.GetValue<string>().Length > 0,
    "Each reconnect row has a date and a time");
RecoveryLog.UseStore(recoveryFile);
Check(RecoveryLog.Recent().Length == 4, "Reconnect history reloads from disk");
File.Delete(recoveryFile);
Check(!Adapters.LooksLikeAlternative("Hyper-V Virtual Ethernet Adapter", "vEthernet (Default Switch)",
    System.Net.NetworkInformation.NetworkInterfaceType.Ethernet), "virtual NICs are not alternative paths");
Check(!Adapters.LooksLikeAlternative("Intel Wi-Fi 6 AX201", "Wi-Fi",
    System.Net.NetworkInformation.NetworkInterfaceType.Wireless80211), "ordinary Wi-Fi is not treated as USB tethering");
using (var protocol = New())
{
    protocol.Receive(Eap(1, 1, [1]));
    Check(protocol.Receive(Eap(4, 6, [])).Event == "IgnoredStaleFailure" && protocol.State == Phase.WaitingMd5,
        "Unmatched leftover EAP Failure before MD5 is not a password reject");
    Check(protocol.Receive(Eap(4, 1, [])).Event == "AuthenticationRejected", "Identity-id Failure remains a real reject");
}
using (var protocol = New())
{
    protocol.Receive(Eap(1, 1, [1]));
    protocol.Receive(Eap(1, 2, new byte[] { 4, 16 }.Concat(new byte[16]).ToArray()));
    Check(protocol.Receive(Eap(3, 2, [])).Event == "EapSuccessNotConnectivityVerified", "MD5 success reaches authenticated");
    var again = protocol.Receive(Eap(4, 9, []));
    Check(again.Event == "PeriodicReauthentication" && protocol.State == Phase.WaitingIdentity,
        "EAP Failure after success starts in-place reauthentication");
    Check(protocol.AddressBound, "Periodic reauthentication retains the bound campus address");
    Check(protocol.Receive(Eap(4, 9, [])).Event == "IgnoredStaleFailure" && protocol.State == Phase.WaitingIdentity,
        "Retransmitted Failure during reauthentication is ignored");
    Check(protocol.Receive(Eap(1, 3, [1])).Event == "IdentityResponsePrepared" && protocol.State == Phase.WaitingMd5,
        "Reauthentication answers the next identity request");
    protocol.Receive(Eap(1, 4, new byte[] { 4, 16 }.Concat(new byte[16]).ToArray()));
    protocol.Receive(Eap(3, 4, []));
    Check(protocol.State == Phase.Authenticated && protocol.AddressBound &&
        Encoding.ASCII.GetString(protocol.PeriodicHeartbeat().Response!).Contains("192.0.2.1", StringComparison.Ordinal),
        "Successful reauthentication resumes heartbeats on the original address");
}

using (var cancel = new CancellationTokenSource())
using (var wire = new Wire())
{
    var clock = new Clock();
    clock.OnPause = () => { if (clock.Elapsed > TimeSpan.FromSeconds(1)) cancel.Cancel(); };
    var result = new ManagedSession(wire, clock, New, () => null, _ => {}, _ => true,
        _ => null, new Budget(), _ => {}).Run(Timeout.InfiniteTimeSpan, cancel.Token);
    Check(result.Session.Reason == "Cancelled", "Continuous session cancels");
    Check(wire.Starts == 1 && wire.Logoffs == 1 && result.LogoffSent, "Disconnect sends one normal Logoff");
}
using (var cancel = new CancellationTokenSource())
using (var wire = new Wire())
{
    var clock = new Clock();
    clock.OnPause = () => { if (clock.Elapsed > TimeSpan.FromSeconds(1)) cancel.Cancel(); };
    var result = new ManagedSession(wire, clock, New, () => cancel.IsCancellationRequested ? "OriginalClientRunning" : null,
        _ => {}, _ => true, _ => null, new Budget(), _ => {}).Run(Timeout.InfiniteTimeSpan, cancel.Token);
    Check(!result.LogoffSent && wire.Logoffs == 0, "Ownership loss forbids cleanup packet");
}
var reauthLog = new List<string>();
int reauthGenerations = 0;
using (var cancel = new CancellationTokenSource())
using (var wire = new ReauthWire())
{
    var clock = new Clock();
    clock.OnPause = () => { if (wire.Starts >= 2 && clock.Elapsed > TimeSpan.FromSeconds(35)) cancel.Cancel(); };
    var result = new ManagedSession(wire, clock, New, () => null, reauthLog.Add, _ => true,
        _ => new ReadyMonitor(), new Budget(), _ => reauthGenerations++).Run(Timeout.InfiniteTimeSpan, cancel.Token);
    Check(result.Session.Reason == "Cancelled", "In-place reauthentication does not end the session");
    Check(reauthGenerations == 1, "Periodic EAP Failure does not start another generation");
    Check(wire.Starts == 2, "The switch Failure is answered with one new EAPOL-Start");
    Check(reauthLog.Contains("PeriodicReauthentication"), "The Failure is logged as periodic reauthentication");
    Check(!reauthLog.Contains("ProtocolFailed") && !reauthLog.Contains("SessionEnded"), "A periodic Failure is not a protocol failure");
    Check(result.LogoffSent && wire.Logoffs == 1, "The session still logs off once when cancelled");
}
using (var cancel = new CancellationTokenSource())
using (var wire = new ReauthWire(answerReauthentication: false))
{
    using var protocol = New();
    var clock = new Clock();
    clock.OnPause = () => { if (clock.Elapsed > TimeSpan.FromSeconds(45)) cancel.Cancel(); };
    var log = new List<string>();
    var result = new SessionRunner(wire, clock, () => null, log.Add, _ => true,
        _ => null, () => true).Run(protocol, Timeout.InfiniteTimeSpan, cancel.Token);
    Check(result.Reason == "ConnectionAttemptTimeout" && log.Contains("PeriodicReauthentication"),
        "An unanswered periodic reauthentication keeps the normal retryable timeout cause");
    Check(clock.Elapsed >= TimeSpan.FromSeconds(36) && clock.Elapsed < TimeSpan.FromSeconds(37),
        "Periodic reauthentication is bounded by the existing six-second attempt budget");
}
bool enabled = false;
using (var monitor = new RecoveryMonitor(new Sampler(), new Probe(), "192.0.2.1", _ => {}, recoveryEnabled: () => enabled))
{
    Check(monitor.Tick(TimeSpan.Zero) == null, "Starts async health check");
    Check(monitor.Tick(TimeSpan.FromMilliseconds(20)) == null, "Disabled auto-recovery does not reconnect");
    enabled = true;
    monitor.Tick(TimeSpan.FromSeconds(61));
    Check(monitor.Tick(TimeSpan.FromSeconds(61.02)) == "RecoveryRequested", "Changed setting applies to active monitor");
}
HandoffChecks.Run(Check);
ObserverLeaseChecks.Run(Check);
RetryChecks.Run(Check);
AcceptanceChecks.Run(Check);
HandoffBudgetChecks.Run(Check);
AcceptanceRecoveryChecks.Run(Check);
var healthy = new ProbeRound([ProbeOutcome.Reachable, ProbeOutcome.Reachable], [ProbeOutcome.Reachable, ProbeOutcome.Reachable]);
Check(BoundRecoveryProbe.Classify([healthy, healthy]).Verified, "Two complete probe rounds verify connectivity");
var partial = healthy with { Https = [ProbeOutcome.Reachable, ProbeOutcome.TlsFailure] };
var partialEvidence = BoundRecoveryProbe.Classify([partial, partial]);
Check(!partialEvidence.Verified && !partialEvidence.Unavailable && partialEvidence.Reason == "CampusPartlyReachable", "Partial reachability neither claims success nor triggers outage recovery");
var dnsRound = healthy with { Https = [ProbeOutcome.DnsFailure, ProbeOutcome.DnsFailure] };
var dnsEvidence = BoundRecoveryProbe.Classify([dnsRound, dnsRound]);
Check(!dnsEvidence.Verified && !dnsEvidence.Unavailable && dnsEvidence.Reason == "CampusDnsFailure", "DNS failure is diagnosed without blind reauthentication");
var unavailable = new ProbeRound([ProbeOutcome.TransportFailure, ProbeOutcome.TransportFailure], [ProbeOutcome.TransportFailure, ProbeOutcome.TransportFailure]);
Check(BoundRecoveryProbe.Classify([unavailable, unavailable]).Unavailable, "Only consistent transport failure confirms outage");
var noDns = unavailable with { Https = [ProbeOutcome.DnsFailure, ProbeOutcome.DnsFailure] };
Check(BoundRecoveryProbe.Classify([noDns, noDns]).Unavailable, "Uncached DNS failure does not mask a complete bound TCP outage");
Check(!BoundRecoveryProbe.Classify([noDns, healthy]).Unavailable, "An inconsistent outage never triggers reauthentication");
using (var monitor = new RecoveryMonitor(new Sampler(), new PartialProbe(), "192.0.2.1", _ => {}))
{
    monitor.Tick(TimeSpan.Zero);
    Check(monitor.Tick(TimeSpan.FromSeconds(.1)) == null && monitor.Held && !monitor.Verified,
        "DNS/partial keeps the authenticated session without claiming online");
    monitor.Tick(TimeSpan.FromSeconds(181));
    Check(monitor.Tick(TimeSpan.FromSeconds(181.1)) == null && monitor.Held,
        "DNS failure does not reauthenticate after three minutes");
}
var logFolder = Path.Combine(Path.GetTempPath(), "campus-journal-test-" + Guid.NewGuid().ToString("N"));
try
{
    var journal = new RuntimeJournal(logFolder);
    journal.Write("PeriodicHeartbeatSent", new { generation = 1 });
    journal.Heartbeat(new { version = "test", phase = "online" });
    Check(Directory.GetFiles(logFolder, "events-*.jsonl").Length == 1, "Protocol telemetry persists");
    Check(System.Text.Json.JsonDocument.Parse(File.ReadAllText(Path.Combine(logFolder, "heartbeat.json")))
        .RootElement.GetProperty("status").GetProperty("phase").GetString() == "online", "Fresh backend status persists independently of GUI");
}
finally { Directory.Delete(logFolder, true); }
{
    const System.Reflection.BindingFlags flags = System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.NonPublic;
    var phaseField = typeof(GuiHost).GetField("phase", flags)!;
    var note = typeof(GuiHost).GetMethod("Note", flags)!;
    var originalPhase = phaseField.GetValue(null);
    try
    {
        phaseField.SetValue(null, "online");
        note.Invoke(null, ["EapSuccessNotConnectivityVerified"]);
        Check((string?)phaseField.GetValue(null) == "online", "Reauthentication success keeps the host online");
        note.Invoke(null, ["AuthenticatedAddressBound"]);
        Check((string?)phaseField.GetValue(null) == "online", "Address confirmation keeps the host online");
        phaseField.SetValue(null, "connecting");
        note.Invoke(null, ["EapSuccessNotConnectivityVerified"]);
        Check((string?)phaseField.GetValue(null) == "verifying", "First authentication still requires connectivity verification");
    }
    finally { phaseField.SetValue(null, originalPhase); }
}
LoggingChecks.Run(Check);
Console.WriteLine($"PASS: {checks} backend checks; only simulated authentication frames.");

static Protocol New() => new([2,0,0,0,0,1], "test-student", Encoding.ASCII.GetBytes("test-only"), [192,0,2,1], 42, new H3cCrypto());
static byte[] Eap(byte code, byte id, byte[] payload)
{
    var frame = new byte[22 + payload.Length];
    new byte[] {2,0,0,0,0,1,2,0,0,0,0,2,0x88,0x8e,1,0}.CopyTo(frame, 0);
    BinaryPrimitives.WriteUInt16BigEndian(frame.AsSpan(16), (ushort)(4 + payload.Length));
    frame[18] = code; frame[19] = id;
    BinaryPrimitives.WriteUInt16BigEndian(frame.AsSpan(20), (ushort)(4 + payload.Length));
    payload.CopyTo(frame, 22);
    return frame;
}

sealed class Clock : ISessionClock
{
    public TimeSpan Elapsed { get; private set; }
    public Action? OnPause;
    public void Pause(TimeSpan duration) { Elapsed += duration; OnPause?.Invoke(); }
}
sealed class Budget : IRecoveryBudget
{
    public string? Reserve() => null;
    public void Trip() => throw new InvalidOperationException("Unexpected circuit trip");
}
sealed class Sampler : ITrafficSampler
{
    public TrafficSample Read(TimeSpan now) => new(now, 0, 0);
}
sealed class Probe : IRecoveryProbe
{
    public Task<RecoveryEvidence> CheckAsync(string address, CancellationToken cancel) => Task.FromResult(new RecoveryEvidence(true, false, "Unavailable"));
}
sealed class PartialProbe : IRecoveryProbe
{
    public Task<RecoveryEvidence> CheckAsync(string address, CancellationToken cancel) => Task.FromResult(new RecoveryEvidence(false, false, "CampusDnsFailure"));
}
sealed class Wire : IFrameTransport
{
    readonly Queue<byte[]> frames = new();
    public int Starts, Logoffs;
    public byte[]? Poll() => frames.TryDequeue(out var value) ? value : null;
    public void Dispose() { }
    public void Send(byte[] frame)
    {
        if (frame[15] == 2) Logoffs++;
        if (frame[15] != 1) return;
        Starts++;
        frames.Enqueue(Frame(1,1,[1]));
        frames.Enqueue(Frame(1,2,new byte[]{4,16}.Concat(new byte[16]).ToArray()));
        frames.Enqueue(Frame(3,2,[]));
    }
    static byte[] Frame(byte code, byte id, byte[] payload)
    {
        var frame = new byte[22+payload.Length];
        new byte[]{2,0,0,0,0,1,2,0,0,0,0,2,0x88,0x8e,1,0}.CopyTo(frame,0);
        BinaryPrimitives.WriteUInt16BigEndian(frame.AsSpan(16), (ushort)(4+payload.Length));
        frame[18]=code; frame[19]=id;
        BinaryPrimitives.WriteUInt16BigEndian(frame.AsSpan(20), (ushort)(4+payload.Length));
        payload.CopyTo(frame,22);
        return frame;
    }
}
sealed class ReadyMonitor : ISessionMonitor
{
    public bool Verified => true;
    public bool Held => false;
    public string? Tick(TimeSpan now) => null;
    public void Dispose() { }
}
sealed class ReauthWire(bool answerReauthentication = true) : IFrameTransport
{
    readonly Queue<byte[]> frames = new();
    int dataSends;
    bool injected;
    public int Starts, Logoffs;
    public byte[]? Poll() => frames.TryDequeue(out var value) ? value : null;
    public void Dispose() { }
    public void Send(byte[] frame)
    {
        if (frame[15] == 2) { Logoffs++; return; }
        if (frame[15] == 1)
        {
            Starts++;
            if (Starts > 1 && !answerReauthentication) return;
            frames.Enqueue(Frame(1, 1, [1]));
            frames.Enqueue(Frame(1, 2, new byte[] { 4, 16 }.Concat(new byte[16]).ToArray()));
            frames.Enqueue(Frame(3, 2, []));
            return;
        }
        if (frame[15] != 0) return;
        if (++dataSends == 3 && !injected)
        {
            injected = true;
            frames.Enqueue(Frame(4, 7, []));
        }
    }
    static byte[] Frame(byte code, byte id, byte[] payload)
    {
        var frame = new byte[22 + payload.Length];
        new byte[] { 2, 0, 0, 0, 0, 1, 2, 0, 0, 0, 0, 2, 0x88, 0x8e, 1, 0 }.CopyTo(frame, 0);
        BinaryPrimitives.WriteUInt16BigEndian(frame.AsSpan(16), (ushort)(4 + payload.Length));
        frame[18] = code; frame[19] = id;
        BinaryPrimitives.WriteUInt16BigEndian(frame.AsSpan(20), (ushort)(4 + payload.Length));
        payload.CopyTo(frame, 22);
        return frame;
    }
}
