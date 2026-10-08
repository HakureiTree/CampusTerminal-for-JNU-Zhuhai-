// SPDX-License-Identifier: GPL-3.0-or-later
using System.Diagnostics;
using System.Net.NetworkInformation;
using System.Text.Json;

namespace CampusAuth;

// While another real path is up, the campus NIC must not keep the default route.
// Nothing here is tied to one machine's adapter name, address, or metric: the NIC
// is the selected campus GUID, and 9000 sits above Windows' automatic metric table
// (link speed maps to roughly 5–50). Both IP families are moved, then put back.
internal static class CampusRoute
{
    internal const int BaseMetric = 9000;
    private static readonly object Gate = new();
    private static readonly Dictionary<Guid, Applied> Held = new();

    private sealed class Applied
    {
        public int V4;
        public int V6;
        public DateTime At;
    }

    internal static int YieldMetricFor(IEnumerable<int> otherMetrics)
    {
        int metric = BaseMetric;
        foreach (int other in otherMetrics)
            if (other >= metric) metric = other + 50;
        return metric;
    }

    public static bool Deprefer(Guid adapter)
    {
        if (!OperatingSystem.IsWindows() || !LiveGate.Elevated()) return false;
        if (LiveGate.OriginalSuiteRunning() || LiveGate.OriginalGuiRunning()) return false;
        var nic = Find(adapter);
        if (nic == null) return false;
        int v4 = FamilyIndex(nic, ipv6: false);
        int v6 = FamilyIndex(nic, ipv6: true);
        var now = DateTime.UtcNow;
        lock (Gate)
        {
            if (Held.TryGetValue(adapter, out var prior) && prior.V4 == v4 && prior.V6 == v6
                && now - prior.At < TimeSpan.FromSeconds(30))
                return true;
        }
        if (v4 <= 0 && v6 <= 0) return false;
        int metric = YieldMetricFor([]);
        if (v4 > 0 && !SetFamily("ipv4", v4, metric.ToString())) return false;
        if (v6 > 0 && !SetFamily("ipv6", v6, metric.ToString())) return false;
        lock (Gate) Held[adapter] = new Applied { V4 = v4, V6 = v6, At = now };
        Remember(adapter);
        return true;
    }

    public static void Restore(Guid adapter)
    {
        lock (Gate) if (!Held.ContainsKey(adapter) && !Load().Contains(adapter)) return;
        var nic = Find(adapter);
        if (nic == null)
        {
            Forget(adapter);
            return;
        }
        int v4 = FamilyIndex(nic, ipv6: false);
        int v6 = FamilyIndex(nic, ipv6: true);
        bool ok4 = v4 <= 0 || SetFamily("ipv4", v4, "auto");
        bool ok6 = v6 <= 0 || SetFamily("ipv6", v6, "auto");
        if (!ok4 || !ok6) return;
        lock (Gate) Held.Remove(adapter);
        Forget(adapter);
        DhcpRenew.Request(adapter);
    }

    public static void RestoreAll()
    {
        Guid[] ids;
        lock (Gate) ids = Held.Keys.Concat(Load()).Distinct().ToArray();
        foreach (var id in ids) Restore(id);
    }

    public static void RecoverStale(Func<Guid, bool> stillNeeded)
    {
        foreach (var id in Load().ToArray())
        {
            if (stillNeeded(id)) Deprefer(id);
            else Restore(id);
        }
    }

    private static NetworkInterface? Find(Guid adapter) => NetworkInterface.GetAllNetworkInterfaces()
        .FirstOrDefault(n => Guid.TryParse(n.Id.Trim('{', '}'), out var found) && found == adapter);

    private static int FamilyIndex(NetworkInterface nic, bool ipv6)
    {
        try
        {
            var props = nic.GetIPProperties();
            return ipv6 ? props.GetIPv6Properties()?.Index ?? 0 : props.GetIPv4Properties()?.Index ?? 0;
        }
        catch (NetworkInformationException) { return 0; }
    }

    private static bool SetFamily(string family, int index, string metric)
    {
        string netsh = Path.Combine(Environment.SystemDirectory, "netsh.exe");
        var start = new ProcessStartInfo(netsh,
            "interface " + family + " set interface interface=" + index + " metric=" + metric + " store=active")
        {
            UseShellExecute = false,
            CreateNoWindow = true
        };
        try
        {
            using var process = Process.Start(start);
            if (process == null || !process.WaitForExit(4000)) return false;
            return process.ExitCode == 0;
        }
        catch (Exception) { return false; }
    }

    private static string MarkerPath() => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "CampusTerminal", "route-yield.json");

    private static HashSet<Guid> Load()
    {
        var ids = new HashSet<Guid>();
        try
        {
            if (!File.Exists(MarkerPath())) return ids;
            var parsed = JsonSerializer.Deserialize<string[]>(File.ReadAllText(MarkerPath()));
            if (parsed == null) return ids;
            foreach (var text in parsed)
                if (Guid.TryParse(text, out var id)) ids.Add(id);
        }
        catch (Exception ex) when (ex is IOException or JsonException or UnauthorizedAccessException) { }
        return ids;
    }

    private static void Remember(Guid adapter)
    {
        var ids = Load();
        if (!ids.Add(adapter)) return;
        Write(ids);
    }

    private static void Forget(Guid adapter)
    {
        var ids = Load();
        if (!ids.Remove(adapter)) return;
        Write(ids);
    }

    private static void Write(HashSet<Guid> ids)
    {
        try
        {
            string path = MarkerPath();
            Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            File.WriteAllText(path, JsonSerializer.Serialize(ids.Select(id => id.ToString("D")).ToArray()));
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { }
    }
}
