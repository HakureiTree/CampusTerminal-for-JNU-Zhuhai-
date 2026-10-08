// SPDX-License-Identifier: GPL-3.0-or-later
using System.Diagnostics;

namespace CampusAuth;

internal interface ISessionClock
{
    TimeSpan Elapsed { get; }
    void Pause(TimeSpan duration);
}

internal sealed class SessionClock : ISessionClock
{
    private readonly Stopwatch watch = Stopwatch.StartNew();
    public TimeSpan Elapsed => watch.Elapsed;
    public void Pause(TimeSpan duration) => Thread.Sleep(duration);
}

internal sealed record SessionResult(string Reason, bool EapAuthenticated, int SentPackets, int Heartbeats,
    bool ConnectivityVerified = false);

// No process/UI/network configuration changes. Environment and transport are
// supplied by the host, and every packet send rechecks the host's safety gate.
internal sealed class SessionRunner(IFrameTransport transport, ISessionClock clock,
    Func<string?> blockReason, Action<string> log, Func<Protocol, bool>? prepareAddress=null,
    Func<TimeSpan, string?>? monitor=null, Func<bool>? connectivityVerified=null)
{
    public SessionResult Run(Protocol protocol, TimeSpan duration, CancellationToken cancellation)
    {
        bool unbounded = duration == Timeout.InfiniteTimeSpan || duration == TimeSpan.MaxValue;
        if (!unbounded && (duration < TimeSpan.FromSeconds(1) || duration > TimeSpan.FromMinutes(5)))
            throw new ArgumentOutOfRangeException(nameof(duration));
        int sent = 0, heartbeats = 0, starts = 0, windowSends = 0;
        var startTime = clock.Elapsed;
        var deadline = unbounded ? TimeSpan.MaxValue : startTime + duration;
        var nextStart = startTime;
        var nextHeartbeat = TimeSpan.MaxValue;
        var windowStart = startTime;
        TimeSpan? authenticatedAt = null, boundAt = null;
        bool authenticated = false, established = false, addressWaitingLogged = false;
        SessionResult Finish(string reason) { log(reason); return new(reason, authenticated, sent, heartbeats, established); }
        string? DeadlineReason()
        {
            var now = clock.Elapsed;
            if (!authenticated)
                return now - startTime >= ConnectionRetryPolicy.AttemptTimeout ? "ConnectionAttemptTimeout" : null;
            authenticatedAt ??= now;
            if (!protocol.AddressBound)
            {
                if (prepareAddress != null) prepareAddress(protocol);
                if (!protocol.AddressBound)
                    return now - authenticatedAt >= ConnectionRetryPolicy.AddressWaitTimeout
                        ? "AuthenticatedAddressTimeout" : null;
            }
            boundAt ??= now;
            return !established && now - boundAt >= ConnectionRetryPolicy.VerificationTimeout
                ? "ConnectionAttemptTimeout" : null;
        }
        string? Send(byte[] packet)
        {
            var blocked = blockReason();
            if (blocked != null) return blocked;
            if (!authenticated && clock.Elapsed - startTime >= ConnectionRetryPolicy.AttemptTimeout)
                return "ConnectionAttemptTimeout";
            if (clock.Elapsed - windowStart >= TimeSpan.FromSeconds(1)) { windowStart = clock.Elapsed; windowSends = 0; }
            if (++windowSends > 20) return "TransmitRateLimit";
            transport.Send(packet); sent++; return null;
        }
        while (clock.Elapsed < deadline)
        {
            if (cancellation.IsCancellationRequested) return Finish("Cancelled");
            var blocked = blockReason();
            if (blocked != null) return Finish(blocked);
            var expired = DeadlineReason();
            if (expired != null) return Finish(expired);
            if (authenticated && !protocol.AddressBound)
            {
                if (!addressWaitingLogged) { log("WaitingForAuthenticatedIpv4"); addressWaitingLogged = true; }
            }
            else if (protocol.State == Phase.WaitingIdentity && starts < 3 && clock.Elapsed >= nextStart)
            {
                blocked = Send(protocol.Start()); if (blocked != null) return Finish(blocked);
                starts++; nextStart = clock.Elapsed + TimeSpan.FromSeconds(3); log("StartSent");
            }
            var frame = transport.Poll();
            if (frame != null)
            {
                var step = protocol.Receive(frame);
                if (!step.Event.StartsWith("Ignored", StringComparison.Ordinal)) log(step.Event);
                if (protocol.State == Phase.Failed) return Finish("ProtocolFailed");
                if (step.Response != null)
                {
                    blocked = Send(step.Response); if (blocked != null) return Finish(blocked);
                }
                if (!authenticated && protocol.State == Phase.Authenticated)
                {
                    authenticated = true;
                    nextHeartbeat = clock.Elapsed + TimeSpan.FromSeconds(30);
                }
            }
            if (authenticated && protocol.AddressBound) boundAt ??= clock.Elapsed;
            if (authenticated && protocol.AddressBound && clock.Elapsed >= nextHeartbeat)
            {
                var step = protocol.PeriodicHeartbeat();
                if (step.Response == null) return Finish("HeartbeatUnavailable");
                blocked = Send(step.Response); if (blocked != null) return Finish(blocked);
                heartbeats++; log("PeriodicHeartbeatSent");
                nextHeartbeat = clock.Elapsed + TimeSpan.FromSeconds(30);
            }
            if (authenticated && protocol.AddressBound && monitor != null)
            {
                var decision = monitor(clock.Elapsed);
                if (decision != null) return Finish(decision);
                if (!established && boundAt is { } bound &&
                    clock.Elapsed - bound < ConnectionRetryPolicy.VerificationTimeout &&
                    connectivityVerified?.Invoke() == true)
                    established = true;
            }
            clock.Pause(TimeSpan.FromMilliseconds(20));
        }
        return Finish(authenticated ? "TrialElapsedNotConnectivityVerified" : "TrialElapsedUnauthenticated");
    }
}
