// SPDX-License-Identifier: GPL-3.0-or-later
using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace CampusAuth;

internal static class AcceptanceRecovery
{
    internal static void Publish(AcceptanceRequest? request, string root, ObserverLease lease, string directory)
    {
        if (request?.RunId == null) return;
        using var process = Process.GetCurrentProcess();
        string folder = Path.Combine(root, "logs", "bounded-validation", request.RunId);
        if (!Directory.Exists(folder)) throw new InvalidOperationException("AcceptanceReportDirectoryMissing");
        Write(Path.Combine(folder, "ownership.json"), new { Root = root, BackendPid = process.Id,
            BackendStartedUtc = process.StartTime.ToUniversalTime().ToString("O"),
            ReportDirectory = directory, Marker = lease.Marker });
    }

    internal static bool SameProcessAlive(int pid, string started)
    {
        try
        {
            using var process = Process.GetProcessById(pid);
            _ = process.Handle;
            return !process.HasExited && process.StartTime.ToUniversalTime().Ticks == DateTimeOffset.Parse(started).UtcTicks;
        }
        catch (ArgumentException) { return false; }
    }

    internal static void AssertStopped(JsonNode owner, int expectedPid, IEnumerable<JsonNode> helpers,
        Func<int, string, bool> alive)
    {
        if (expectedPid <= 0 || owner["BackendPid"]!.GetValue<int>() != expectedPid)
            throw new InvalidOperationException("RecoveryBackendIdentityMismatch");
        if (alive(expectedPid, owner["BackendStartedUtc"]!.GetValue<string>()))
            throw new InvalidOperationException("RecoveryBackendStillRunning");
        foreach (var helper in helpers)
            if (alive(helper["ProcessId"]!.GetValue<int>(), helper["StartedUtc"]!.GetValue<string>()))
                throw new InvalidOperationException("RecoveryHelperStillRunning");
    }

    internal static int Run(string runId, int expectedPid, int seconds)
    {
        if (!Guid.TryParseExact(runId, "N", out _) || seconds is < 1 or > 60)
            throw new InvalidOperationException("InvalidRecoveryRequest");
        if (!LiveGate.Elevated()) throw new InvalidOperationException("ElevationRequired");
        string root = GuiHost.FindRepositoryRoot(AppContext.BaseDirectory);
        string folder = Path.Combine(root, "logs", "bounded-validation", runId);
        var clock = Stopwatch.StartNew();
        HandoffResult result;
        try
        {
            var owner = JsonNode.Parse(File.ReadAllText(Path.Combine(folder, "ownership.json")))!;
            string directory = Path.GetFullPath(owner["ReportDirectory"]!.GetValue<string>());
            string allowed = Path.Combine(root, "logs", "campus-terminal") + Path.DirectorySeparatorChar;
            if (!directory.StartsWith(allowed, StringComparison.OrdinalIgnoreCase) ||
                !string.Equals(Path.GetFullPath(owner["Root"]!.GetValue<string>()), root, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("RecoveryReportPathMismatch");
            var context = JsonNode.Parse(File.ReadAllText(Path.Combine(directory, "context.json")))!;
            var adapter = Adapters.Resolve(context["Adapter"]!.GetValue<string>()) ??
                throw new InvalidOperationException("RecoveryAdapterMissing");
            using var mutex = new Mutex(false, "Local\\CampusAuth-" + adapter.Id);
            bool acquired;
            try { acquired = mutex.WaitOne(0); }
            catch (AbandonedMutexException) { acquired = true; }
            if (!acquired) throw new InvalidOperationException("RecoverySenderStillOwnsAdapter");
            try
            {
                var helpers = Directory.GetFiles(directory, "helper-*.json")
                    .Select(path => JsonNode.Parse(File.ReadAllText(path))!).ToArray();
                AssertStopped(owner, expectedPid, helpers, SameProcessAlive);
                using var lease = new ObserverLease(Path.Combine(root, "logs"), owner["Marker"]!.GetValue<string>());
                var operations = new WindowsOriginalHandoff(root, adapter, lease,
                    () => !SameProcessAlive(expectedPid, owner["BackendStartedUtc"]!.GetValue<string>()),
                    () => TimeSpan.FromSeconds(seconds) - clock.Elapsed, directory);
                // A second recovery process must never repeat platform operations.
                using (var receipt = new FileStream(Path.Combine(folder, "recovery-attempt.json"), FileMode.CreateNew))
                    JsonSerializer.Serialize(receipt, new { ProcessId = Environment.ProcessId, StartedUtc = DateTimeOffset.UtcNow });
                result = new OriginalHandoff(operations, stage => Write(Path.Combine(folder, "recovery-stage.json"),
                    new { Stage = stage, ElapsedSeconds = clock.Elapsed.TotalSeconds })).Run();
            }
            finally { mutex.ReleaseMutex(); }
        }
        catch (Exception ex)
        {
            result = new(false, "RecoveryBlocked", ex is InvalidOperationException ? ex.Message : ex.GetType().Name);
        }
        Write(Path.Combine(folder, "crash-recovery.json"), result);
        return result.Succeeded ? 0 : 1;
    }

    private static void Write(string path, object value)
    {
        string temp = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        File.WriteAllText(temp, JsonSerializer.Serialize(value));
        File.Move(temp, path, true);
    }
}
