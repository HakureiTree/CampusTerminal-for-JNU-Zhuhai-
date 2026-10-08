// SPDX-License-Identifier: GPL-3.0-or-later
using System.Diagnostics;
using System.Text.Json.Nodes;
using CampusAuth;

internal static class AcceptanceChecks
{
    internal static void Run(Action<bool, string> check)
    {
        check(AcceptanceRequest.Parse(null) == null, "Normal sessions have no acceptance deadline");
        foreach (int seconds in new[] { 0, 9, 121 })
        {
            bool rejected = false;
            try { AcceptanceRequest.Parse(new JsonObject { ["supervisorPid"] = 1,
                ["runId"] = Guid.NewGuid().ToString("N"),
                ["supervisorStartedUtc"] = DateTimeOffset.UtcNow.ToString("O"), ["seconds"] = seconds }); }
            catch (InvalidOperationException) { rejected = true; }
            check(rejected, "Out-of-range acceptance duration rejected");
        }
        TimeSpan now = TimeSpan.Zero;
        bool alive = true;
        var reasons = new List<string>();
        using (var guard = new AcceptanceWatchdog(() => now, () => alive, TimeSpan.FromSeconds(120), reasons.Add))
        {
            guard.Tick();
            now = TimeSpan.FromSeconds(119.999);
            guard.Tick();
            check(reasons.Count == 0, "Deadline does not cancel early");
            now = TimeSpan.FromSeconds(120);
            guard.Tick();
            alive = false;
            guard.Tick();
            check(reasons.SequenceEqual(new[] { "AcceptanceDeadlineExceeded" }), "Deadline fires once without retry");
        }
        reasons.Clear();
        using (var guard = new AcceptanceWatchdog(() => TimeSpan.Zero, () => false, TimeSpan.FromSeconds(120), reasons.Add))
            guard.Tick();
        check(reasons.SequenceEqual(new[] { "AcceptanceSupervisorExited" }), "Supervisor loss cancels immediately");
        reasons.Clear();
        using (var guard = new AcceptanceWatchdog(() => TimeSpan.Zero, () => throw new IOException(),
            TimeSpan.FromSeconds(120), reasons.Add)) guard.Tick();
        check(reasons.SequenceEqual(new[] { "AcceptanceSupervisorUnverifiable" }), "Uncertain owner never renews trial");
        // Live Process.Start/OpenProcess coverage is environment-specific; identity
        // mismatch and exit are already enforced in AcceptanceWatchdog.Start.
    }
}
