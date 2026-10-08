// SPDX-License-Identifier: GPL-3.0-or-later
using System.Text.Json.Nodes;

namespace CampusAuth;

// Counts failures for this process only. A computer or software restart calls
// ResetOnStart so the next launch can auto-connect again.
internal static class AutoFailureBudget
{
    internal const int Max = 5;
    private static readonly object Gate = new();
    private static int count = -1;
    private static string? storePath;
    internal static void UseStore(string? path) => storePath = path;

    private static string FilePath => storePath ?? Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData),
        "CampusTerminal", "auto-failures.json");

    internal static int Count
    {
        get { lock (Gate) { Load(); return count; } }
    }

    internal static bool Blocked => Count >= Max;

    internal static void Record()
    {
        lock (Gate)
        {
            Load();
            if (count < 1000) count++;
            Save();
        }
    }

    internal static void Reset()
    {
        lock (Gate)
        {
            count = 0;
            Save();
        }
    }

    internal static void ResetOnStart() => Reset();

    internal static void Forget()
    {
        lock (Gate) count = -1;
    }

    private static void Load()
    {
        if (count >= 0) return;
        try
        {
            var node = JsonNode.Parse(File.ReadAllText(FilePath));
            count = Math.Max(0, node?["count"]?.GetValue<int>() ?? 0);
        }
        catch (Exception) { count = 0; }
    }

    private static void Save()
    {
        try
        {
            var path = FilePath;
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            var tmp = path + ".tmp";
            File.WriteAllText(tmp, "{\"count\":" + count + "}");
            File.Move(tmp, path, true);
        }
        catch (Exception) { }
    }
}
