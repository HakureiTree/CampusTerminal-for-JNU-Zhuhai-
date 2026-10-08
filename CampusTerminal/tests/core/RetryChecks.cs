// SPDX-License-Identifier: GPL-3.0-or-later
using System.Buffers.Binary;
using System.Text;
using CampusAuth;

internal static class RetryChecks
{
    internal static void Run(Action<bool, string> check)
    {
        var silent = new Scenario();
        var result = silent.Run();
        check(result.Session.Reason == "ReconnectAttemptsExhausted", "Three silent timeouts stop the campaign");
        check(silent.Generations.Count == 3 && silent.Clock.Elapsed == TimeSpan.FromSeconds(18), "Three attempts consume exactly six seconds each in simulated time");
        check(silent.Generations.SequenceEqual(new[] { TimeSpan.Zero, TimeSpan.FromSeconds(6), TimeSpan.FromSeconds(12) }), "No fourth attempt or legacy 600-second gap inside campaign");
        check(silent.Budget.Reservations == 1 && silent.Budget.Trips == 1, "A campaign is reserved once and exhaustion is durable");
        check(silent.Log.Count(x => x == "ReconnectAttemptsExhausted") == 1, "Exhaustion has a single durable event");

        var eapOnly = new Scenario { Authenticate = _ => true };
        result = eapOnly.Run();
        check(result.Session.Reason == "ReconnectAttemptsExhausted" && eapOnly.Generations.Count == 3, "EAP success alone never bypasses the deadline");
        check(eapOnly.Disposed == 3 && eapOnly.Wire.Logoffs == 3, "Each old probe scope is disposed and session logged off before retry");

        var pending = new PendingProbe();
        var joined = new Scenario { Authenticate = _ => true,
            MonitorFactory = _ => new RecoveryMonitor(new EmptySampler(), pending, "192.0.2.1", _ => {}, requireVerification: true) };
        result = joined.Run();
        check(result.Session.Reason == "ReconnectAttemptsExhausted" && pending.Started == 3 && pending.Cancelled == 3,
            "Actual recovery monitors cancel and join all pending probes at verification boundaries");

        var late = new Scenario { Authenticate = _ => true };
        late.MonitorFactory = _ => new LateMonitor(late.Clock);
        result = late.Run();
        check(result.Session.Reason == "ReconnectAttemptsExhausted" && late.Generations.Count == 3 && !result.RecoveryVerified,
            "A verification result beyond the deadline neither resets attempts nor reports success");

        var third = new Scenario { Authenticate = n => n == 2, Verified = n => n == 2, CancelAt = 55 };
        result = third.Run();
        check(result.Session.Reason == "Cancelled" && result.Session.ConnectivityVerified, "Third attempt success remains connected beyond six seconds");
        check(third.Generations.Count == 3 && third.Budget.Trips == 0, "Successful third attempt neither trips circuit nor retries");
        var outage = new Scenario { Authenticate = n => n == 0, Verified = n => n == 0, OutageAt = 2 };
        result = outage.Run();
        check(result.Session.Reason == "ReconnectAttemptsExhausted" && outage.Generations.Count == 4, "An established session gets three new recovery attempts");
        check(outage.Log.Count(x => x == "ConnectionAttemptStarted:1") == 2, "Recovery numbering starts at one after a verified connection");

        var disabled = new Scenario { Enabled = false };
        result = disabled.Run();
        check(result.Session.Reason == "AutomaticReconnectDisabled" && disabled.Generations.Count == 1, "Disabled automatic recovery does not send another attempt");
        check(disabled.Log.Count(x => x == "LastConnectionFailure:ConnectionAttemptTimeout") == 1,
            "Disabled retry preserves the terminal timeout cause exactly once");
        var cancel = new Scenario { CancelAt = 8 };
        result = cancel.Run();
        check(result.Session.Reason == "Cancelled" && cancel.Generations.Count == 2 && cancel.Budget.Trips == 0, "Manual cancellation interrupts the second attempt without fallback retries");
        var identity = new Scenario { BlockAt = 2 };
        result = identity.Run();
        check(result.Session.Reason == "InterfaceIdentityChanged" && identity.Generations.Count == 1, "Identity change is never retried blindly");

        var rejected = new Scenario { Authenticate = _ => true, Reject = true };
        result = rejected.Run();
        check(result.Session.Reason == "ProtocolFailed" && rejected.Generations.Count == 1, "Explicit authentication rejection is not retried as a timeout");
        check(OriginalHandoff.Required(true, HandoffTrigger.RuntimeFailure, true) &&
            !OriginalHandoff.Required(false, HandoffTrigger.RuntimeFailure, true), "Only enabled fallback hands exhausted sessions back");

        var dhcp = new Scenario { Authenticate = _ => true, Verified = _ => true, AddressReadyAfter = 10, CancelAt = 15 };
        result = dhcp.Run();
        check(result.Session.Reason == "Cancelled" && result.Session.ConnectivityVerified && dhcp.Generations.Count == 1,
            "DHCP wait is outside the six-second EAP/probe budget");
        var slowDhcp = new Scenario { Authenticate = _ => true, Verified = _ => true, AddressReadyAfter = 1000 };
        result = slowDhcp.Run();
        check(result.Session.Reason == "ReconnectAttemptsExhausted" && slowDhcp.Generations.Count == 3 &&
            slowDhcp.Clock.Elapsed >= TimeSpan.FromSeconds(ConnectionRetryPolicy.AddressWaitTimeout.TotalSeconds * 3),
            "Address wait is retried three times");
    }

    private sealed class Scenario
    {
        internal readonly SimClock Clock = new();
        internal readonly CountingBudget Budget = new();
        internal readonly List<TimeSpan> Generations = new();
        internal readonly List<string> Log = new();
        internal readonly SimWire Wire = new();
        internal Func<int, bool> Authenticate = _ => false, Verified = _ => false;
        internal bool Enabled = true, Reject;
        internal double CancelAt = double.PositiveInfinity, BlockAt = double.PositiveInfinity, OutageAt = double.PositiveInfinity,
            AddressReadyAfter = -1;
        internal int Disposed;
        internal Func<int, ISessionMonitor>? MonitorFactory;
        internal ManagedResult Run()
        {
            using var cancel = new CancellationTokenSource();
            Clock.Paused = () => { if (Clock.Elapsed.TotalSeconds >= CancelAt) cancel.Cancel(); };
            Protocol New() => new([2,0,0,0,0,1], "test-only", Encoding.ASCII.GetBytes("fake-password"), [192,0,2,1], 42, new H3cCrypto(),
                requireAddressBinding: AddressReadyAfter >= 0);
            string? Block() => Clock.Elapsed.TotalSeconds >= BlockAt ? "InterfaceIdentityChanged" : null;
            bool Prepare(Protocol protocol)
            {
                if (AddressReadyAfter < 0) return true;
                if (Clock.Elapsed.TotalSeconds < AddressReadyAfter) return false;
                if (!protocol.AddressBound) protocol.BindAddress([192, 0, 2, 1]);
                return true;
            }
            ISessionMonitor Monitor(int n) => MonitorFactory?.Invoke(n) ?? new SimMonitor(() => Verified(n),
                now => n == 0 && now.TotalSeconds >= OutageAt ? "RecoveryRequested" : null, () => Disposed++);
            return new ManagedSession(Wire, Clock, New, Block, Log.Add, Prepare, Monitor, Budget,
                n => { Generations.Add(Clock.Elapsed); Wire.Authenticate = Authenticate(n); Wire.Reject = Reject; }, () => Enabled)
                .Run(Timeout.InfiniteTimeSpan, cancel.Token);
        }
    }

    private sealed class SimClock : ISessionClock
    {
        public TimeSpan Elapsed { get; private set; }
        internal Action? Paused;
        public void Pause(TimeSpan duration) { Elapsed += duration; Paused?.Invoke(); }
    }
    private sealed class PendingProbe : IRecoveryProbe
    {
        internal int Started, Cancelled;
        public Task<RecoveryEvidence> CheckAsync(string local, CancellationToken cancellation)
        {
            Started++;
            var source = new TaskCompletionSource<RecoveryEvidence>();
            cancellation.Register(() => { Cancelled++; source.TrySetCanceled(cancellation); });
            return source.Task;
        }
    }
    private sealed class EmptySampler : ITrafficSampler
    {
        public TrafficSample Read(TimeSpan now) => new(now, 0, 0);
    }
    private sealed class LateMonitor(SimClock clock) : ISessionMonitor
    {
        public bool Verified { get; private set; }
        public bool Held => Verified;
        public string? Tick(TimeSpan now) { clock.Pause(ConnectionRetryPolicy.VerificationTimeout); Verified = true; return null; }
        public void Dispose() { }
    }
    private sealed class CountingBudget : IRecoveryBudget
    {
        internal int Reservations, Trips;
        public string? Reserve() { Reservations++; return null; }
        public void Trip() => Trips++;
    }
    private sealed class SimMonitor(Func<bool> verified, Func<TimeSpan, string?> tick, Action disposed) : ISessionMonitor
    {
        public bool Verified { get; private set; }
        public bool Held => Verified;
        public string? Tick(TimeSpan now)
        {
            var result = tick(now);
            Verified = result == null && verified();
            return result;
        }
        public void Dispose() => disposed();
    }
    private sealed class SimWire : IFrameTransport
    {
        private readonly Queue<byte[]> frames = new();
        internal bool Authenticate, Reject;
        internal int Logoffs;
        public byte[]? Poll() => frames.TryDequeue(out var frame) ? frame : null;
        public void Dispose() { }
        public void Send(byte[] packet)
        {
            if (packet[15] == 2) Logoffs++;
            if (packet[15] != 1 || !Authenticate) return;
            frames.Enqueue(Frame(1, 1, [1]));
            frames.Enqueue(Frame(1, 2, new byte[] {4,16}.Concat(new byte[16]).ToArray()));
            frames.Enqueue(Frame(Reject ? (byte)4 : (byte)3, 2, []));
        }
        private static byte[] Frame(byte code, byte id, byte[] payload)
        {
            var frame = new byte[22 + payload.Length];
            new byte[] {2,0,0,0,0,1,2,0,0,0,0,2,0x88,0x8e,1,0}.CopyTo(frame, 0);
            BinaryPrimitives.WriteUInt16BigEndian(frame.AsSpan(16), (ushort)(4 + payload.Length));
            frame[18] = code; frame[19] = id;
            BinaryPrimitives.WriteUInt16BigEndian(frame.AsSpan(20), (ushort)(4 + payload.Length));
            payload.CopyTo(frame, 22);
            return frame;
        }
    }
}
