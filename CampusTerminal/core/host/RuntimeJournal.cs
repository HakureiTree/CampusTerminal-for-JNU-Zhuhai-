// SPDX-License-Identifier: GPL-3.0-or-later
using System.Text.Json;

namespace CampusAuth;

// Stores protocol stage names and bounded status summaries, never IPC requests or frames.
internal sealed class RuntimeJournal
{
    private readonly object gate = new();
    private readonly string directory;
    private readonly string run = Guid.NewGuid().ToString("N");
    private readonly long segmentLimit;
    private readonly Func<DateTime> utcNow;
    private long sequence;
    private string? eventError;
    private string? heartbeatError;
    internal string? EventError => Volatile.Read(ref eventError);
    internal string? HeartbeatError => Volatile.Read(ref heartbeatError);
    internal string? Error => EventError ?? HeartbeatError;
    internal string DirectoryPath => directory;
    internal string RunId => run;

    internal RuntimeJournal(string directory, long segmentLimit = 8 * 1024 * 1024, Func<DateTime>? utcNow = null)
    {
        this.directory = directory;
        this.segmentLimit = segmentLimit;
        this.utcNow = utcNow ?? (() => DateTime.UtcNow);
        try { Directory.CreateDirectory(directory); Prune(); }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { Volatile.Write(ref eventError, "RuntimeLogUnavailable"); }
    }

    internal void Write(string stage, object? detail = null)
    {
        lock (gate)
        {
            try
            {
                var now = utcNow();
                Prune(now);
                string path = ActivePath(now);
                var row = JsonSerializer.Serialize(new { at = new DateTimeOffset(now, TimeSpan.Zero), run, pid = Environment.ProcessId,
                    sequence = ++sequence, stage, detail });
                File.AppendAllText(path, row + Environment.NewLine);
                Volatile.Write(ref eventError, null);
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException or ArgumentException)
            { Volatile.Write(ref eventError, "RuntimeLogUnavailable"); }
        }
    }

    private string ActivePath(DateTime now)
    {
        string prefix = "events-" + now.ToString("yyyyMMdd");
        string active = Path.Combine(directory, prefix + ".jsonl");
        if (!File.Exists(active) || new FileInfo(active).Length < segmentLimit) return active;
        int segment = 1;
        string path;
        do { path = Path.Combine(directory, prefix + "-" + segment++.ToString("D4") + ".jsonl"); }
        while (File.Exists(path));
        File.Move(active, path); // Segments are immutable after rollover.
        return active;
    }

    private void Prune(DateTime? now = null)
    {
        if (!System.IO.Directory.Exists(directory)) return;
        var today = (now ?? utcNow()).Date;
        var cutoff = today.AddDays(-30); // Keep 31 UTC calendar dates including today.
        foreach (var file in new DirectoryInfo(directory).GetFiles("events-*").ToArray())
        {
            string name = file.Name;
            if (name.Length < 16 || !DateTime.TryParseExact(name.Substring(7, 8), "yyyyMMdd",
                    System.Globalization.CultureInfo.InvariantCulture, System.Globalization.DateTimeStyles.None, out var day)) continue;
            if (day.Date < cutoff) file.Delete();
        }
    }

    internal object[] RecentRecoveryEvents(int take)
    {
        lock (gate)
        {
            if (eventError != null || take <= 0) return [];
            var rows = new List<(DateTimeOffset At, object Row)>();
            if (!Directory.Exists(directory)) return [];
            foreach (var file in new DirectoryInfo(directory).GetFiles("events-*"))
            {
                string[] lines;
                try { lines = File.ReadAllLines(file.FullName); }
                catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { continue; }
                for (int i = lines.Length - 1; i >= 0; i--)
                {
                    try
                    {
                        using var doc = JsonDocument.Parse(lines[i]);
                        if (doc.RootElement.GetProperty("stage").GetString() != "TwoCampusRoundsPassed") continue;
                        var at = doc.RootElement.GetProperty("at").GetDateTimeOffset();
                        rows.Add((at, new { at = at.ToLocalTime().ToString("M.d"), time = at.ToLocalTime().ToString("HH:mm:ss") }));
                    }
                    catch (Exception ex) when (ex is JsonException or KeyNotFoundException or FormatException or InvalidOperationException) { }
                }
            }
            return rows.OrderByDescending(x => x.At).Take(take).Select(x => x.Row).ToArray();
        }
    }

    internal void Heartbeat(object status)
    {
        lock (gate)
        {
            try
            {
                string path = Path.Combine(directory, "heartbeat.json");
                File.WriteAllText(path + ".tmp", JsonSerializer.Serialize(new { at = DateTimeOffset.UtcNow, run,
                    pid = Environment.ProcessId, status }, IpcServer.Json));
                File.Move(path + ".tmp", path, overwrite: true);
                Volatile.Write(ref heartbeatError, null);
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException or JsonException)
            { Volatile.Write(ref heartbeatError, "HeartbeatLogUnavailable"); }
        }
    }
}
