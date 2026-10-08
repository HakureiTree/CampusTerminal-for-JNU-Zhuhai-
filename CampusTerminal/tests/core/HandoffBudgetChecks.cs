// SPDX-License-Identifier: GPL-3.0-or-later
using System.Diagnostics;
using System.Text.Json.Nodes;
using CampusAuth;

internal static class HandoffBudgetChecks
{
    internal static void Run(Action<bool, string> check)
    {
        string root = Path.Combine(Path.GetTempPath(), "campus-handoff-budget-" + Guid.NewGuid().ToString("N"));
        string scripts = Path.Combine(root, "CampusTerminal", "core", "handoff");
        Directory.CreateDirectory(scripts);
        File.WriteAllText(Path.Combine(scripts, "Invoke-OriginalHandoffStage.ps1"), "Start-Sleep -Seconds 30");
        Process? sleeper = null;
        try
        {
            using var lease = new ObserverLease(Path.Combine(root, "logs"));
            var adapter = new AdapterInfo(Guid.NewGuid(), "fake", "fake", "020000000001", true, "192.0.2.1");
            var exhausted = new WindowsOriginalHandoff(root, adapter, lease, () => true, () => TimeSpan.Zero);
            string? error = null;
            try { exhausted.CorrectOriginalInstanceExists(); }
            catch (InvalidOperationException ex) { error = ex.Message; }
            check(error == "HandoffBudgetExhausted" && !File.Exists(Path.Combine(exhausted.ReportDirectory, "helper-process.json")),
                "Expired total budget forbids launching another helper");

            var clock = Stopwatch.StartNew();
            var pending = new WindowsOriginalHandoff(root, adapter, lease, () => true,
                () => TimeSpan.FromSeconds(1) - clock.Elapsed);
            error = null;
            try { pending.CorrectOriginalInstanceExists(); }
            catch (InvalidOperationException ex) { error = ex.Message; }
            var identity = JsonNode.Parse(File.ReadAllText(Path.Combine(pending.ReportDirectory, "helper-process.json")))!;
            sleeper = Process.GetProcessById(identity["ProcessId"]!.GetValue<int>());
            check(sleeper.StartTime.ToUniversalTime().ToString("O") == identity["StartedUtc"]!.GetValue<string>(),
                "Pending helper report identifies the exact live process");
            check(error == "HandoffExecutorStillRunning" && !sleeper.HasExited && lease.Preserve && clock.Elapsed.TotalSeconds < 5,
                "One shared deadline reports pending helper without killing it or releasing pause");
            // Only this fixture's sleeping helper is terminated, never a handoff worker.
            sleeper.Kill();
            check(sleeper.WaitForExit(3000), "Owned test sleeper is reaped");
            lease.Release();
        }
        finally
        {
            if (sleeper != null) { if (!sleeper.HasExited) { sleeper.Kill(); sleeper.WaitForExit(3000); } sleeper.Dispose(); }
            Directory.Delete(root, true);
        }
    }
}
