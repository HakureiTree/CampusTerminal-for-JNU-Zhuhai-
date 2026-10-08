// SPDX-License-Identifier: GPL-3.0-or-later
namespace CampusAuth;

internal sealed record ManagedResult(SessionResult Session, int Generation, bool RecoveryVerified, bool LogoffSent);

internal sealed class ManagedSession(IFrameTransport transport, ISessionClock clock,
    Func<Protocol> newProtocol, Func<string?> blockReason, Action<string> log,
    Func<Protocol, bool> prepareAddress, Func<int, ISessionMonitor?> newMonitor,
    IRecoveryBudget budget, Action<int> beginGeneration, Func<bool>? recoveryEnabled = null, Action? progress = null)
{
    public ManagedResult Run(TimeSpan duration, CancellationToken cancellation)
    {
        bool unbounded = duration == Timeout.InfiniteTimeSpan || duration == TimeSpan.MaxValue;
        var deadline = unbounded ? TimeSpan.MaxValue : clock.Elapsed + duration;
        int generation = 0;
        int attempt = 1;
        bool campaignReserved = false;
        while (true)
        {
            beginGeneration(generation);
            log("ConnectionAttemptStarted:" + attempt);
            using var protocol = newProtocol();
            ISessionMonitor? monitor = null;
            SessionResult result;
            bool verified;
            try
            {
                string? Tick(TimeSpan now)
                {
                    monitor ??= newMonitor(generation);
                    return monitor?.Tick(now);
                }
                var remaining = unbounded ? Timeout.InfiniteTimeSpan : deadline - clock.Elapsed;
                result = new SessionRunner(transport, clock, blockReason, log, prepareAddress, Tick,
                    () => monitor?.Verified == true || monitor?.Held == true, progress)
                    .Run(protocol, remaining, cancellation);
                verified = result.ConnectivityVerified && (monitor?.Verified ?? false);
            }
            finally { monitor?.Dispose(); }

            string? blocked = cancellation.IsCancellationRequested ? "Cancelled" : blockReason();
            if (result.ConnectivityVerified) { attempt = 0; campaignReserved = false; }
            bool retry = ConnectionRetryPolicy.Retryable(result.Reason) && blocked == null;
            if (retry && !(recoveryEnabled?.Invoke() ?? true)) blocked = "AutomaticReconnectDisabled";
            if (retry && blocked == null && attempt >= ConnectionRetryPolicy.MaxAttempts)
            {
                blocked = "ReconnectAttemptsExhausted";
                log(blocked);
            }
            if (retry && blocked == null && !unbounded && deadline - clock.Elapsed < ConnectionRetryPolicy.AttemptTimeout)
                blocked = "InsufficientRecoveryTime";
            // Cooldown/daily limits apply to a campaign, not between its three attempts.
            if (retry && blocked == null && !campaignReserved)
            {
                blocked = budget.Reserve();
                campaignReserved = blocked == null;
            }
            // Recheck after durable I/O, immediately before the first side effect.
            if (retry && blocked == null) blocked = cancellation.IsCancellationRequested ? "Cancelled" : blockReason();
            retry &= blocked == null;
            if (ConnectionRetryPolicy.Retryable(result.Reason) && blocked != null)
            {
                log("LastConnectionFailure:" + result.Reason);
                result = result with { Reason = blocked };
            }
            bool logoffSent = false;
            // Cancellation stops the loop, but an explicitly requested normal
            // disconnect still logs off if interface ownership remains safe.
            // Yielding to USB/tether must also log off, or the campus port stays
            // authorized and its default route keeps beating the phone.
            string? held = blockReason();
            if ((held == null || held == "AlternativeNetworkPath") && protocol.CloseSession() is { } logoff)
            {
                transport.Send(logoff); logoffSent = true;
                log(retry ? "RecoveryLogoffSent" : "FinalLogoffSent");
            }
            if (!retry)
            {
                if (result.Reason == "ReconnectAttemptsExhausted") budget.Trip();
                return new(result, generation, generation > 0 && verified, logoffSent);
            }
            protocol.Dispose();
            log("RecoveryReauthenticating");
            // Retire queued traffic from the old session, bounded even under flood.
            for (int i = 0; i < 64; i++)
            {
                if (transport.Poll() == null) break;
                if (i == 63)
                {
                    budget.Trip();
                    return new(result with {Reason="RecoveryReceiveQueueBusy"}, generation, false, logoffSent);
                }
            }
            generation++;
            attempt++;
        }
    }
}
