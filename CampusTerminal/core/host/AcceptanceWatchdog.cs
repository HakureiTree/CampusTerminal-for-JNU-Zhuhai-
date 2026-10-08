// SPDX-License-Identifier: GPL-3.0-or-later
using System.Diagnostics;
using System.Text.Json.Nodes;

namespace CampusAuth;

internal sealed record AcceptanceRequest(int SupervisorPid, DateTimeOffset SupervisorStartedUtc, int Seconds, string? RunId = null)
{
    internal static AcceptanceRequest? Parse(JsonNode? node)
    {
        if (node == null) return null;
        int pid = node["supervisorPid"]?.GetValue<int>() ?? 0;
        int seconds = node["seconds"]?.GetValue<int>() ?? 0;
        string? runId = node["runId"]?.GetValue<string>();
        if (pid <= 0 || pid == Environment.ProcessId || seconds is < 10 or > 120 ||
            !Guid.TryParseExact(runId, "N", out _) ||
            !DateTimeOffset.TryParse(node["supervisorStartedUtc"]?.GetValue<string>(), out var started))
            throw new InvalidOperationException("InvalidAcceptanceSupervisor");
        return new(pid, started, seconds, runId);
    }
}

// Independent of the GUI and IPC loop. Cancellation uses the normal session
// cleanup/handoff path; it never kills the original client or deletes a lease.
internal sealed class AcceptanceWatchdog : IDisposable
{
    private readonly Func<TimeSpan> elapsed;
    private readonly Func<bool> alive;
    private readonly Action<string> cancel;
    private readonly TimeSpan limit;
    private readonly IDisposable? owner;
    private Timer? timer;
    private int fired;

    internal AcceptanceWatchdog(Func<TimeSpan> elapsed, Func<bool> alive, TimeSpan limit,
        Action<string> cancel, IDisposable? owner = null)
    {
        this.elapsed = elapsed;
        this.alive = alive;
        this.limit = limit;
        this.cancel = cancel;
        this.owner = owner;
    }

    internal static AcceptanceWatchdog Start(AcceptanceRequest request, Action<string> cancel)
    {
        var process = Process.GetProcessById(request.SupervisorPid);
        try
        {
            // A held process handle prevents a recycled PID from renewing ownership.
            _ = process.Handle;
            if (process.HasExited || Math.Abs((process.StartTime.ToUniversalTime() -
                    request.SupervisorStartedUtc.UtcDateTime).TotalMilliseconds) > 1)
                throw new InvalidOperationException("AcceptanceSupervisorIdentityChanged");
            var clock = Stopwatch.StartNew();
            var guard = new AcceptanceWatchdog(() => clock.Elapsed, () => !process.HasExited,
                TimeSpan.FromSeconds(request.Seconds), cancel, process);
            guard.timer = new Timer(_ => guard.Tick(), null, 250, 250);
            return guard;
        }
        catch { process.Dispose(); throw; }
    }

    internal void Tick()
    {
        if (Volatile.Read(ref fired) != 0) return;
        string? reason;
        try { reason = !alive() ? "AcceptanceSupervisorExited" :
            elapsed() >= limit ? "AcceptanceDeadlineExceeded" : null; }
        catch { reason = "AcceptanceSupervisorUnverifiable"; }
        if (reason != null && Interlocked.Exchange(ref fired, 1) == 0) cancel(reason);
    }

    public void Dispose()
    {
        Interlocked.Exchange(ref fired, 1);
        if (timer != null)
        {
            using var finished = new ManualResetEvent(false);
            if (timer.Dispose(finished)) finished.WaitOne();
        }
        owner?.Dispose();
    }
}
