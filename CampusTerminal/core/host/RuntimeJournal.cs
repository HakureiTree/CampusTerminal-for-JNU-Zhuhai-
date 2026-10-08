// SPDX-License-Identifier: GPL-3.0-or-later
using System.Text.Json;

namespace CampusAuth;

// Accepts protocol stage names and status summaries, never IPC requests or frames.
internal sealed class RuntimeJournal
{
    private readonly object gate = new();
    private readonly string directory;
    private readonly string run = Guid.NewGuid().ToString("N");
    internal string? Error { get; private set; }
    internal string DirectoryPath => directory;

    internal RuntimeJournal(string directory)
    {
        this.directory = directory;
        try
        {
            Directory.CreateDirectory(directory);
            foreach (var old in new DirectoryInfo(directory).GetFiles("events-*")
                .OrderByDescending(f => f.LastWriteTimeUtc).Skip(31)) old.Delete();
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        { Error = "RuntimeLogUnavailable"; }
    }

    internal void Write(string stage, object? detail = null)
    {
        lock (gate)
        {
            try
            {
                string path = Path.Combine(directory, "events-" + DateTime.UtcNow.ToString("yyyyMMdd") + ".jsonl");
                if (File.Exists(path) && new FileInfo(path).Length > 8 * 1024 * 1024)
                    File.Move(path, path + ".previous", overwrite: true);
                File.AppendAllText(path, JsonSerializer.Serialize(new { at = DateTimeOffset.UtcNow,
                    run, pid = Environment.ProcessId, stage, detail }) + Environment.NewLine);
                Error = null;
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            { Error = "RuntimeLogUnavailable"; }
        }
    }

    internal object[] RecentRecoveryEvents(int take)
    {
        lock (gate)
        {
            if (Error != null || take <= 0) return [];
            var rows = new List<object>();
            foreach (var file in new DirectoryInfo(directory).GetFiles("events-*.jsonl").OrderByDescending(f => f.Name))
            {
                string[] lines;
                try { lines = File.ReadAllLines(file.FullName); }
                catch (IOException) { continue; }
                for (int i = lines.Length - 1; i >= 0; i--)
                {
                    try
                    {
                        using var doc = JsonDocument.Parse(lines[i]);
                        if (doc.RootElement.GetProperty("stage").GetString() != "TwoCampusRoundsPassed") continue;
                        var at = doc.RootElement.GetProperty("at").GetDateTimeOffset().ToLocalTime();
                        rows.Add(new { at = at.ToString("M.d"), time = at.ToString("HH:mm:ss") });
                        if (rows.Count >= take) return rows.ToArray();
                    }
                    catch (Exception ex) when (ex is JsonException or KeyNotFoundException or FormatException or InvalidOperationException) { }
                }
            }
            return rows.ToArray();
        }
    }

    internal void Heartbeat(object status)
    {
        lock (gate)
        {
            try
            {
                string path = Path.Combine(directory, "heartbeat.json");
                File.WriteAllText(path + ".tmp", JsonSerializer.Serialize(new { at = DateTimeOffset.UtcNow,
                    run, pid = Environment.ProcessId, status }, IpcServer.Json));
                File.Move(path + ".tmp", path, overwrite: true);
            }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            { Error = "RuntimeLogUnavailable"; }
        }
    }
}
