// SPDX-License-Identifier: GPL-3.0-or-later
using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace CampusAuth;

internal sealed class WindowsOriginalHandoff : IOriginalHandoffOperations
{
    private readonly ObserverLease lease;
    private readonly Func<bool> replacementStopped;
    private readonly Func<TimeSpan>? remaining;
    private readonly string script, contextPath;
    private readonly bool recovering;
    internal string ReportDirectory { get; }

    internal WindowsOriginalHandoff(string root, AdapterInfo adapter, ObserverLease lease, Func<bool> replacementStopped,
        Func<TimeSpan>? remaining = null, string? existingReport = null)
    {
        this.lease = lease;
        this.replacementStopped = replacementStopped;
        this.remaining = remaining;
        string exeDir = Path.GetDirectoryName(Environment.ProcessPath) ?? "";
        script = GuiHost.FirstExistingFile(
            Path.Combine(exeDir, "handoff", "Invoke-OriginalHandoffStage.ps1"),
            Path.Combine(root, "handoff", "Invoke-OriginalHandoffStage.ps1"),
            Path.Combine(root, "CampusTerminal", "core", "handoff", "Invoke-OriginalHandoffStage.ps1"),
            Path.Combine(root, "core", "handoff", "Invoke-OriginalHandoffStage.ps1"),
            Path.Combine(exeDir, "core", "handoff", "Invoke-OriginalHandoffStage.ps1"),
            Path.Combine(exeDir, "CampusTerminal", "core", "handoff", "Invoke-OriginalHandoffStage.ps1"));
        recovering = existingReport != null;
        ReportDirectory = existingReport ?? Path.Combine(root, "logs", "campus-terminal", Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(ReportDirectory);
        contextPath = Path.Combine(ReportDirectory, "context.json");
        if (recovering)
        {
            var context = JsonNode.Parse(File.ReadAllText(contextPath))!;
            if (!string.Equals(Path.GetFullPath(context["Root"]!.GetValue<string>()), Path.GetFullPath(root), StringComparison.OrdinalIgnoreCase) ||
                Guid.Parse(context["Adapter"]!.GetValue<string>()) != adapter.Id ||
                context["Mac"]!.GetValue<string>() != adapter.Mac || context["Marker"]!.GetValue<string>() != lease.Marker)
                throw new InvalidOperationException("RecoveryContextMismatch");
            return;
        }
        File.WriteAllText(contextPath, JsonSerializer.Serialize(new
        {
            Root = root, Adapter = adapter.Id, adapter.Mac, Marker = lease.Marker
        }));
    }

    public void Preflight()
    {
        if (!LiveGate.Elevated()) throw new InvalidOperationException("ElevationRequired");
        if (!File.Exists(script)) throw new InvalidOperationException("HandoffExecutorMissing");
        Invoke(recovering ? "RecoveryPreflight" : "Preflight");
    }

    public void ConfirmReplacementStopped()
    {
        if (!replacementStopped()) throw new InvalidOperationException("ReplacementStillRunning");
    }

    public void ConfirmPauseOwned()
    {
        if (!lease.IsOwned) throw new InvalidOperationException("MaintenanceOwnershipLost");
    }

    public void RestoreOriginalService() => Invoke("RestoreService");
    internal void StopOriginalNormally() => Invoke("StopOriginal");
    internal void StopOriginalService() => Invoke("StopOriginalService");
    public bool CorrectOriginalInstanceExists() => Invoke("ClientExists");
    public void StartOriginalNormally() => Invoke("StartClient");
    public bool WaitForOriginalStart() => Invoke("WaitClient");
    public void VerifyOriginalAuthentication() => Invoke("Authentication");
    public void VerifyTwoCampusRoundsAndDefaultPath() => Invoke("Network");
    public void ResumeAndVerifyOriginalMonitor() => Invoke("ResumeMonitor");

    private bool Invoke(string stage)
    {
        ConfirmReplacementStopped();
        ConfirmPauseOwned();
        if (remaining != null && remaining() <= TimeSpan.Zero)
            throw new InvalidOperationException("HandoffBudgetExhausted");
        string executable = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows),
            "System32", "WindowsPowerShell", "v1.0", "powershell.exe");
        var start = new ProcessStartInfo(executable) { UseShellExecute = false, CreateNoWindow = true };
        using var parent = Process.GetCurrentProcess();
        foreach (string argument in new[] { "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", script,
            "-Stage", stage, "-ContextPath", contextPath, "-CallerProcessId", parent.Id.ToString(),
            "-CallerStartedUtc", parent.StartTime.ToUniversalTime().ToString("O") }) start.ArgumentList.Add(argument);
        string reportPath = Path.Combine(ReportDirectory, stage + ".json");
        if (File.Exists(reportPath)) File.Delete(reportPath);
        using var process = Process.Start(start) ?? throw new InvalidOperationException("HandoffExecutorUnavailable");
        var helper = new { Stage = stage, ProcessId = process.Id,
            StartedUtc = process.StartTime.ToUniversalTime().ToString("O"), Executable = executable };
        File.WriteAllText(Path.Combine(ReportDirectory, "helper-process.json"), JsonSerializer.Serialize(helper));
        int wait = (int)Math.Clamp((remaining?.Invoke() ?? TimeSpan.FromSeconds(180)).TotalMilliseconds, 0, 180_000);
        if (!process.WaitForExit(wait))
        {
            // Do not kill a helper midway through service restoration or release its pause.
            lease.Preserve = true;
            throw new InvalidOperationException("HandoffExecutorStillRunning");
        }
        if (!File.Exists(reportPath)) throw new InvalidOperationException("HandoffStageReportMissing");
        var report = JsonNode.Parse(File.ReadAllText(reportPath));
        if (report?["Stage"]?.GetValue<string>() != stage || process.ExitCode != 0 || report["Ok"]?.GetValue<bool>() != true)
            throw new InvalidOperationException(report?["Error"]?.GetValue<string>() ?? "HandoffStageFailed");
        return report["Value"]?.GetValue<bool>() ?? false;
    }
}
