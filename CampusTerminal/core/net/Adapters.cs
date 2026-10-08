// SPDX-License-Identifier: GPL-3.0-or-later
using System.Net.NetworkInformation;
using System.Net.Sockets;

namespace CampusAuth;

internal sealed record AdapterInfo(Guid Id, string Name, string Description, string Mac, bool Up, string Ipv4);

internal static class Adapters
{
    private static bool _Skip(string description)
    {
        var text = description.ToLowerInvariant();
        return text.Contains("loopback") || text.Contains("virtual") || text.Contains("hyper-v")
            || text.Contains("wan miniport") || text.Contains("bluetooth") || text.Contains("vpn");
    }

    internal static bool LooksLikeAlternative(string description, string name, NetworkInterfaceType type)
    {
        var text = (description + " " + name).ToLowerInvariant();
        if (_Skip(text) || text.Contains("teredo") || text.Contains("isatap") || text.Contains("tap-windows")
            || text.Contains("wintun") || text.Contains("clash"))
            return false;
        if (text.Contains("rndis") || text.Contains("remote ndis") || text.Contains("usb")
            || text.Contains("iphone") || text.Contains("tether") || text.Contains("android")
            || text.Contains("apple mobile") || text.Contains("mobile device")
            || text.Contains("personal hotspot") || text.Contains("internet sharing"))
            return true;
        return false;
    }

    internal static bool IsPhoneTether(string description, string name)
    {
        var text = (description + " " + name).ToLowerInvariant();
        if (_Skip(text) || text.Contains("teredo") || text.Contains("isatap") || text.Contains("tap-windows")
            || text.Contains("wintun") || text.Contains("clash"))
            return false;
        // "usb" alone is a USB Ethernet dongle, which may be the campus port. Phone
        // tethering identifies itself as RNDIS / Apple Mobile / hotspot.
        return text.Contains("rndis") || text.Contains("remote ndis") || text.Contains("gadget")
            || text.Contains("iphone") || text.Contains("tether") || text.Contains("android")
            || text.Contains("apple mobile") || text.Contains("mobile device")
            || text.Contains("personal hotspot") || text.Contains("internet sharing")
            || text.Contains("mobile connect") || text.Contains("cdc ncm") || text.Contains("usb ncm")
            || text.Contains("网络共享") || text.Contains("手机共享")
            || (text.Contains("远程") && text.Contains("ndis"));
    }

    internal static bool IsCampusPort(string description, string name, NetworkInterfaceType type) =>
        type == NetworkInterfaceType.Ethernet && !_Skip(description) && !_Skip(name)
        && !IsPhoneTether(description, name);

    internal readonly record struct PathCensus(bool Present, string Fingerprint, object Detail);

    public static PathCensus Census(Guid campus)
    {
        var rows = new List<object>();
        bool present = false;
        foreach (var nic in NetworkInterface.GetAllNetworkInterfaces())
        {
            Guid.TryParse(nic.Id.Trim('{', '}'), out var id);
            var info = Describe(nic);
            string gateway = string.Join(",", nic.GetIPProperties().GatewayAddresses
                .Select(g => g.Address)
                .Where(a => a.AddressFamily == AddressFamily.InterNetwork)
                .Select(a => a.ToString()));
            bool skipped = _Skip(nic.Description) || _Skip(nic.Name);
            bool alt = !skipped && id != campus && LooksLikeAlternative(nic.Description, nic.Name, nic.NetworkInterfaceType);
            bool usable = nic.OperationalStatus == OperationalStatus.Up && (info.Ipv4.Length > 0 || gateway.Length > 0);
            if (alt && usable) present = true;
            rows.Add(new
            {
                id = info.Id, name = nic.Name, description = nic.Description,
                type = nic.NetworkInterfaceType.ToString(), status = nic.OperationalStatus.ToString(),
                mac = info.Mac, ipv4 = info.Ipv4, gateway, alternative = alt && usable, skipped,
                campus = id == campus
            });
        }
        string fingerprint = string.Join(";", rows.Select(r =>
        {
            var node = System.Text.Json.JsonSerializer.Serialize(r);
            return node;
        }));
        return new(present, fingerprint, new { present, inodeService = INodeServiceState(), rows });
    }

    private static string INodeServiceState()
    {
        try
        {
            var start = new System.Diagnostics.ProcessStartInfo("sc.exe", "query INODE_SVR_SERVICE")
            { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true };
            using var process = System.Diagnostics.Process.Start(start);
            if (process == null) return "QueryFailed";
            string output = process.StandardOutput.ReadToEnd();
            process.WaitForExit(1500);
            if (output.Contains("RUNNING", StringComparison.OrdinalIgnoreCase)) return "Running";
            if (output.Contains("STOPPED", StringComparison.OrdinalIgnoreCase)) return "Stopped";
            if (output.Contains("1060")) return "Missing";
            return "Other";
        }
        catch (Exception) { return "QueryFailed"; }
    }

    public static bool PhonePath(Guid campus) => OtherPath(campus, phoneOnly: true);

    public static bool AlternativePath(Guid campus) => OtherPath(campus, phoneOnly: false);

    private static bool OtherPath(Guid campus, bool phoneOnly)
    {
        foreach (var nic in NetworkInterface.GetAllNetworkInterfaces())
        {
            if (!Guid.TryParse(nic.Id.Trim('{', '}'), out var id) || id == campus) continue;
            if (nic.OperationalStatus != OperationalStatus.Up) continue;
            bool match = phoneOnly
                ? IsPhoneTether(nic.Description, nic.Name)
                : LooksLikeAlternative(nic.Description, nic.Name, nic.NetworkInterfaceType);
            if (!match) continue;
            var info = Describe(nic);
            var gateway = nic.GetIPProperties().GatewayAddresses
                .Any(g => g.Address.AddressFamily == AddressFamily.InterNetwork);
            if (info.Ipv4.Length > 0 || gateway) return true;
        }
        return false;
    }

    public static AdapterInfo[] List() => NetworkInterface.GetAllNetworkInterfaces()
        .Where(n => IsCampusPort(n.Description, n.Name, n.NetworkInterfaceType))
        .Select(Describe)
        .Where(a => a.Id != Guid.Empty)
        .OrderByDescending(a => a.Up)
        .ThenBy(a => a.Description)
        .ToArray();

    public static AdapterInfo? Resolve(string text)
    {
        var all = List();
        if (Guid.TryParse(text.Trim('{', '}'), out var id))
            return all.FirstOrDefault(a => a.Id == id);
        return all.FirstOrDefault(a =>
            a.Description.Equals(text, StringComparison.OrdinalIgnoreCase) ||
            a.Name.Equals(text, StringComparison.OrdinalIgnoreCase) ||
            ($"以太网:{a.Description}").Equals(text, StringComparison.OrdinalIgnoreCase) ||
            ($"以太网:{a.Name}").Equals(text, StringComparison.OrdinalIgnoreCase));
    }

    public static AdapterInfo Describe(NetworkInterface nic)
    {
        Guid.TryParse(nic.Id.Trim('{', '}'), out var id);
        var mac = nic.GetPhysicalAddress().ToString();
        var ipv4 = nic.GetIPProperties().UnicastAddresses
            .Select(a => a.Address)
            .FirstOrDefault(a => a.AddressFamily == AddressFamily.InterNetwork && TrialAddressGate.UsableIpv4(a.ToString()))
            ?.ToString() ?? "";
        return new(id, nic.Name, nic.Description, mac, nic.OperationalStatus == OperationalStatus.Up, ipv4);
    }

    public static string RouteKey(NetworkInterface nic, string ipv4)
    {
        var gateways = string.Join(",", nic.GetIPProperties().GatewayAddresses
            .Select(g => g.Address)
            .Where(a => a.AddressFamily == AddressFamily.InterNetwork)
            .Select(a => a.ToString())
            .OrderBy(s => s));
        return $"{nic.Id.Trim('{', '}').ToLowerInvariant()}|{ipv4}|{gateways}";
    }
}
