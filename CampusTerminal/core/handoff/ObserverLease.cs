// SPDX-License-Identifier: GPL-3.0-or-later
using System.Diagnostics;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace CampusAuth;

internal sealed class ObserverLease : IDisposable
{
    private readonly string markerPath, ownerPath;
    private readonly string marker = "CampusTerminal-" + Guid.NewGuid().ToString("N");
    private readonly string directory;
    private readonly DateTimeOffset acquiredAt;
    private static int live;
    private bool counted, released;
    internal bool Preserve { get; set; }
    internal string Marker => marker;
    internal string MarkerPath => markerPath;

    internal ObserverLease(string logDirectory)
    {
        directory = logDirectory;
        Directory.CreateDirectory(directory);
        markerPath = Path.Combine(directory, "pause-recovery.signal");
        ownerPath = markerPath + ".owner";
        string temporary = markerPath + "." + Guid.NewGuid().ToString("N") + ".tmp";
        acquiredAt = DateTimeOffset.UtcNow;
        try
        {
            File.WriteAllText(temporary, marker, new UTF8Encoding(false));
            try { File.Move(temporary, markerPath, overwrite: false); }
            catch (IOException)
            {
                if (!CanReplaceStale()) throw new InvalidOperationException("MaintenanceAlreadyOwned");
                File.Move(temporary, markerPath, overwrite: true);
            }
            WriteOwner();
            NoteHeld();
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }

    internal bool IsOwned
    {
        get
        {
            try { return !released && File.ReadAllText(markerPath) == marker; }
            catch (IOException) { return false; }
            catch (UnauthorizedAccessException) { return false; }
        }
    }

    internal ObserverLease(string logDirectory, string existingMarker)
    {
        directory = logDirectory;
        markerPath = Path.Combine(directory, "pause-recovery.signal");
        ownerPath = markerPath + ".owner";
        marker = existingMarker;
        acquiredAt = DateTimeOffset.UtcNow;
        Preserve = true;
        if (!marker.StartsWith("CampusTerminal-", StringComparison.Ordinal) || !IsOwned)
            throw new InvalidOperationException("MaintenanceOwnershipLost");
        NoteHeld();
    }

    internal void WaitForPause(CancellationToken cancel)
    {
        var deadline = Stopwatch.StartNew();
        while (deadline.Elapsed < TimeSpan.FromSeconds(45))
        {
            cancel.ThrowIfCancellationRequested();
            if (!IsOwned) throw new InvalidOperationException("MaintenanceOwnershipLost");
            if (TryReadPause(out var latest, out var heartbeat))
            {
                if (PauseAcknowledged(latest, heartbeat, acquiredAt, DateTimeOffset.UtcNow))
                {
                    try
                    {
                        using var process = Process.GetProcessById(latest["ProcessId"]!.GetValue<int>());
                        if (!process.HasExited && process.StartTime.ToUniversalTime() <= acquiredAt.UtcDateTime)
                            return;
                    }
                    catch (Exception ex) when (ex is ArgumentException or InvalidOperationException or
                        System.ComponentModel.Win32Exception) { }
                }
            }
            else if (deadline.Elapsed >= TimeSpan.FromSeconds(2))
                return;
            if (cancel.WaitHandle.WaitOne(250)) cancel.ThrowIfCancellationRequested();
        }
        if (!TryReadPause(out _, out _)) return;
        throw new InvalidOperationException("ObserverPauseNotAcknowledged");
    }

    bool TryReadPause(out JsonNode latest, out JsonNode heartbeat)
    {
        latest = heartbeat = null!;
        try
        {
            latest = JsonNode.Parse(File.ReadAllText(Path.Combine(directory, "latest.json")))!;
            heartbeat = JsonNode.Parse(File.ReadAllText(Path.Combine(directory, "heartbeat.json")))!;
            if (!DateTimeOffset.TryParse(heartbeat["TimestampUtc"]?.GetValue<string>(), out var at))
                return false;
            var now = DateTimeOffset.UtcNow;
            return at <= now.AddSeconds(2) && now - at <= TimeSpan.FromSeconds(20);
        }
        catch (Exception ex) when (ex is IOException or JsonException or ArgumentException)
        { return false; }
    }

    internal static bool PauseAcknowledged(JsonNode latest, JsonNode heartbeat, DateTimeOffset acquired,
        DateTimeOffset now)
    {
        static bool Fresh(JsonNode node, DateTimeOffset since, DateTimeOffset current) =>
            DateTimeOffset.TryParse(node["TimestampUtc"]?.GetValue<string>(), out var timestamp) &&
            timestamp >= since && timestamp <= current.AddSeconds(2) && current - timestamp <= TimeSpan.FromSeconds(15);
        string? run = latest["RunId"]?.GetValue<string>();
        int? pid = latest["ProcessId"]?.GetValue<int>();
        return Fresh(latest, acquired, now) && Fresh(heartbeat, acquired, now) &&
            !string.IsNullOrWhiteSpace(run) && run == heartbeat["RunId"]?.GetValue<string>() &&
            pid > 0 && pid == heartbeat["ProcessId"]?.GetValue<int>() &&
            latest["Recovery"]?["Decision"]?.GetValue<string>() == "Paused" &&
            heartbeat["Activity"]?.GetValue<string>() != "RecoveryExecutor";
    }

    internal void Release()
    {
        if (released) return;
        if (!IsOwned) throw new InvalidOperationException("MaintenanceOwnershipLost");
        File.Delete(markerPath);
        try { File.Delete(ownerPath); } catch (IOException) { }
        released = true;
    }

    public void Dispose()
    {
        if (!Preserve && IsOwned) Release();
        NoteDropped();
    }

    private void NoteHeld()
    {
        if (counted) return;
        Interlocked.Increment(ref live);
        counted = true;
    }

    private void NoteDropped()
    {
        if (!counted) return;
        Interlocked.Decrement(ref live);
        counted = false;
    }

    private void WriteOwner()
    {
        using var process = Process.GetCurrentProcess();
        File.WriteAllText(ownerPath, JsonSerializer.Serialize(new
        {
            process.Id,
            StartedUtc = process.StartTime.ToUniversalTime().ToString("O")
        }));
    }

    private bool CanReplaceStale()
    {
        string existing;
        try { existing = File.ReadAllText(markerPath); }
        catch (IOException) { return false; }
        if (!existing.StartsWith("CampusTerminal-", StringComparison.Ordinal)) return false;
        if (!File.Exists(ownerPath)) return true;
        try
        {
            var node = JsonNode.Parse(File.ReadAllText(ownerPath));
            int pid = node?["Id"]?.GetValue<int>() ?? 0;
            if (pid <= 0 || !DateTimeOffset.TryParse(node?["StartedUtc"]?.GetValue<string>(), out var started))
                return true;
            using var process = Process.GetProcessById(pid);
            if (pid == Environment.ProcessId && Volatile.Read(ref live) == 0) return true;
            return process.HasExited ||
                Math.Abs((process.StartTime.ToUniversalTime() - started.UtcDateTime).TotalSeconds) > 2;
        }
        catch (Exception ex) when (ex is IOException or JsonException or ArgumentException
            or InvalidOperationException or System.ComponentModel.Win32Exception)
        { return true; }
    }
}
