// SPDX-License-Identifier: GPL-3.0-or-later
using System.Text.Json.Nodes;
using CampusAuth;

internal static class ObserverLeaseChecks
{
    internal static void Run(Action<bool, string> check)
    {
        var now = DateTimeOffset.UtcNow;
        JsonObject Status() => new() { ["TimestampUtc"] = now.ToString("O"), ["RunId"] = "test-run",
            ["ProcessId"] = 42, ["Recovery"] = new JsonObject { ["Decision"] = "Paused" } };
        var latest = Status();
        var heartbeat = Status();
        bool Ready() => ObserverLease.PauseAcknowledged(latest, heartbeat, now.AddSeconds(-1), now);
        check(Ready(), "Fresh matching pause acknowledgement");
        heartbeat["Activity"] = "RecoveryExecutor";
        check(!Ready(), "In-flight recovery cannot acknowledge pause");
        heartbeat.Remove("Activity");
        heartbeat["RunId"] = "another-run";
        check(!Ready(), "Run mismatch rejected");
        heartbeat["RunId"] = "test-run";
        latest["TimestampUtc"] = now.AddSeconds(-30).ToString("O");
        check(!Ready(), "Old pause status rejected");
        latest["TimestampUtc"] = now.AddSeconds(10).ToString("O");
        check(!Ready(), "Future timestamp rejected");
        latest["TimestampUtc"] = now.ToString("O");
        latest["Recovery"]!["Decision"] = "NoSustainedCampusFailure";
        check(!Ready(), "Healthy network is not pause acknowledgement");

        string folder = Path.Combine(Path.GetTempPath(), "CampusTerminal-lease-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(folder);
        string path = Path.Combine(folder, "pause-recovery.signal");
        try
        {
            using (var lease = new ObserverLease(folder))
            {
                check(lease.IsOwned && File.ReadAllText(path) == lease.Marker, "Own marker published");
                bool blocked = false;
                try { using var duplicate = new ObserverLease(folder); }
                catch (InvalidOperationException) { blocked = true; }
                check(blocked && lease.IsOwned, "Second owner cannot overwrite marker");
                using var cancel = new CancellationTokenSource();
                cancel.Cancel();
                bool cancelled = false;
                try { lease.WaitForPause(cancel.Token); }
                catch (OperationCanceledException) { cancelled = true; }
                check(cancelled, "Pause wait responds to disconnect");
            }
            using (var lease = new ObserverLease(folder))
            {
                var waited = System.Diagnostics.Stopwatch.StartNew();
                lease.WaitForPause(CancellationToken.None);
                check(waited.Elapsed < TimeSpan.FromSeconds(6), "No observer on this log folder does not block authentication");
            }
            check(!File.Exists(path), "Normal cleanup releases own pause");
            using (var lease = new ObserverLease(folder))
            {
                File.WriteAllText(path, "foreign-owner");
                check(!lease.IsOwned, "Ownership loss detected");
            }
            check(File.ReadAllText(path) == "foreign-owner", "Foreign pause preserved");
            File.Delete(path);
            using (var lease = new ObserverLease(folder)) { lease.Preserve = true; }
            check(File.Exists(path), "Failed handoff may retain pause");
            using (var again = new ObserverLease(folder))
                check(again.IsOwned && File.ReadAllText(path) == again.Marker, "Same process reclaims own preserved pause");
            check(!File.Exists(path), "Reclaimed session still releases on dispose");
            File.WriteAllText(path, "CampusTerminal-stale");
            using (var lease = new ObserverLease(folder))
                check(lease.IsOwned && File.ReadAllText(path) == lease.Marker, "Stale CampusTerminal pause is reclaimed");
        }
        finally { Directory.Delete(folder, true); }
    }
}
